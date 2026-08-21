"""Diagnostic test to understand the actual stream format from AgentCore.

Run this test with:
    cd backend
    uv run pytest tests/test_stream_debug.py -v -s

The -s flag shows print output so you can see exactly what's being parsed.
"""

import json
from unittest.mock import patch

from jouleverne.services.agent import stream_agent_response


# ─── Helpers ─────────────────────────────────────────────────────────────────

class RawStream:
    """Simulate a raw streaming body that yields bytes exactly as provided."""

    def __init__(self, raw_bytes: bytes):
        self._data = raw_bytes

    def iter_chunks(self):
        # Yield in realistic small chunks (like HTTP chunked transfer)
        chunk_size = 64
        for i in range(0, len(self._data), chunk_size):
            yield self._data[i:i + chunk_size]


def _make_response(raw_bytes: bytes) -> dict:
    return {"response": RawStream(raw_bytes)}


# ─── Test: Raw lines (no SSE wrapping) ──────────────────────────────────────

class TestRawNewlineDelimited:
    """If boto3 gives us raw newline-delimited JSON (no 'data:' prefix)."""

    @patch("jouleverne.services.agent.agentcore_client")
    def test_text_tokens(self, mock_client):
        # Simulates what AgentCore might return WITHOUT SSE wrapping
        raw = b'"Ich"\n" bin"\n" der"\n" Chatbot"\n'

        mock_client.invoke_agent_runtime.return_value = _make_response(raw)

        events = list(stream_agent_response("hi", "s1"))
        print("\n--- RAW NEWLINE-DELIMITED TEXT TOKENS ---")
        for event_type, data in events:
            print(f"  {event_type}: {data}")

        token_events = [(t, d) for t, d in events if t == "token"]
        texts = [json.loads(d)["text"] for _, d in token_events]
        assert texts == ["Ich", " bin", " der", " Chatbot"]

    @patch("jouleverne.services.agent.agentcore_client")
    def test_trace_and_text(self, mock_client):
        lines = [
            json.dumps({"type": "trace", "event": "tool_start", "tool": "filtered_kb_search", "input": {}}),
            json.dumps({"type": "trace", "event": "tool_result", "tool_use_id": "t1", "result": {"query": "test", "result_count": 2, "results": []}}),
            '"Die Antwort"',
            '" lautet"',
            '" 42."',
            json.dumps({"type": "citations", "citations": [{"url": "s3://bucket/doc.txt", "title": "Doc", "source_type": "kb_document"}]}),
        ]
        raw = ("\n".join(lines) + "\n").encode()

        mock_client.invoke_agent_runtime.return_value = _make_response(raw)

        events = list(stream_agent_response("question", "s1"))
        print("\n--- RAW: TRACE + TEXT + CITATIONS ---")
        for event_type, data in events:
            print(f"  {event_type}: {data[:120]}")

        types = [t for t, _ in events]
        assert types == ["trace", "trace", "token", "token", "token", "citation", "done"]


# ─── Test: SSE format (with 'data:' prefix) ─────────────────────────────────

class TestSSEFormat:
    """If boto3 gives us SSE-formatted data (with 'data:' prefix and double newlines)."""

    @patch("jouleverne.services.agent.agentcore_client")
    def test_text_tokens_sse(self, mock_client):
        # Simulates AgentCore SSE format: "data: <json>\n\n"
        raw = b'data: "Ich"\n\ndata: " bin"\n\ndata: " der"\n\ndata: " Chatbot"\n\n'

        mock_client.invoke_agent_runtime.return_value = _make_response(raw)

        events = list(stream_agent_response("hi", "s1"))
        print("\n--- SSE FORMAT TEXT TOKENS ---")
        for event_type, data in events:
            print(f"  {event_type}: {data}")

        token_events = [(t, d) for t, d in events if t == "token"]
        texts = [json.loads(d)["text"] for _, d in token_events]
        assert texts == ["Ich", " bin", " der", " Chatbot"]

    @patch("jouleverne.services.agent.agentcore_client")
    def test_trace_sse(self, mock_client):
        trace = json.dumps({"type": "trace", "event": "tool_start", "tool": "web_search", "input": {}})
        raw = f'data: {trace}\n\ndata: "Answer"\n\n'.encode()

        mock_client.invoke_agent_runtime.return_value = _make_response(raw)

        events = list(stream_agent_response("hi", "s1"))
        print("\n--- SSE FORMAT TRACE + TEXT ---")
        for event_type, data in events:
            print(f"  {event_type}: {data[:120]}")

        types = [t for t, _ in events]
        assert types == ["trace", "token", "done"]


# ─── Test: Duplicated tool_start (the bug you observed) ─────────────────────

class TestDuplicatedToolStart:
    """Reproduce the bug: if tool_start events stream progressively."""

    @patch("jouleverne.services.agent.agentcore_client")
    def test_progressive_tool_input_not_duplicated(self, mock_client):
        """The OLD bug: tool_start fired on every delta of tool input.
        With the fix in main.py, only one tool_start should be emitted.
        This test validates the BFE backend handles the FIXED output correctly.
        """
        # After the fix, agent only emits ONE tool_start with empty input
        lines = [
            json.dumps({"type": "trace", "event": "tool_start", "tool": "filtered_kb_search", "input": {}}),
            json.dumps({"type": "trace", "event": "tool_result", "tool_use_id": "t1", "result": {"query": "Energiestrategie", "result_count": 3, "results": []}}),
            '"Die Antwort."',
        ]
        raw = ("\n".join(lines) + "\n").encode()

        mock_client.invoke_agent_runtime.return_value = _make_response(raw)

        events = list(stream_agent_response("Energiestrategie", "s1"))
        print("\n--- FIXED: SINGLE TOOL_START ---")
        for event_type, data in events:
            print(f"  {event_type}: {data[:120]}")

        trace_events = [(t, d) for t, d in events if t == "trace"]
        assert len(trace_events) == 2  # one tool_start, one tool_result

    @patch("jouleverne.services.agent.agentcore_client")
    def test_old_duplicated_format_handled(self, mock_client):
        """If the agent STILL sends duplicated tool_start events (before agent fix),
        verify the backend handles them (it will emit multiple trace events).
        """
        lines = [
            json.dumps({"type": "trace", "event": "tool_start", "tool": "filtered_kb_search", "input": ""}),
            json.dumps({"type": "trace", "event": "tool_start", "tool": "filtered_kb_search", "input": '{"'}),
            json.dumps({"type": "trace", "event": "tool_start", "tool": "filtered_kb_search", "input": '{"query": "test"'}),
            json.dumps({"type": "trace", "event": "tool_start", "tool": "filtered_kb_search", "input": '{"query": "test"}'}),
            json.dumps({"type": "trace", "event": "tool_result", "tool_use_id": "t1", "result": {"query": "test", "result_count": 1, "results": []}}),
            '"Answer"',
        ]
        raw = ("\n".join(lines) + "\n").encode()

        mock_client.invoke_agent_runtime.return_value = _make_response(raw)

        events = list(stream_agent_response("test", "s1"))
        print("\n--- OLD BUG: DUPLICATED TOOL_START (no fix in agent) ---")
        for event_type, data in events:
            print(f"  {event_type}: {data[:120]}")

        # Backend currently emits all of them (4 tool_starts + 1 tool_result)
        trace_events = [(t, d) for t, d in events if t == "trace"]
        print(f"\n  Total trace events: {len(trace_events)}")
        # This shows the problem — without the agent fix you'd get many trace events
