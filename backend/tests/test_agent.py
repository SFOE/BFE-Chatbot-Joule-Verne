"""Tests for the agent service (mocked AgentCore calls)."""

import json
import pytest
from unittest.mock import patch, MagicMock

from jouleverne.services.agent import invoke_agent, stream_agent_response


class MockStreamingBody:
    """Mock for botocore StreamingBody that supports iter_chunks()."""

    def __init__(self, lines: list[str]):
        """Each line becomes a chunk (newline-separated in the stream)."""
        self._data = "\n".join(lines) + "\n" if lines else ""

    def iter_chunks(self):
        """Yield the full content as a single chunk (simulates streaming)."""
        if self._data:
            yield self._data.encode("utf-8")


class MockStreamingBodyChunked:
    """Mock that yields data in small chunks to test buffering."""

    def __init__(self, lines: list[str]):
        self._data = "\n".join(lines) + "\n" if lines else ""

    def iter_chunks(self, chunk_size: int = 10):
        """Yield data in small pieces to test the buffer logic."""
        data = self._data.encode("utf-8")
        for i in range(0, len(data), chunk_size):
            yield data[i:i + chunk_size]


def _make_response(lines: list[str]) -> dict:
    """Create a mock AgentCore response with a StreamingBody."""
    return {"response": MockStreamingBody(lines)}


def _make_response_chunked(lines: list[str]) -> dict:
    """Create a mock AgentCore response with small chunks (tests buffering)."""
    return {"response": MockStreamingBodyChunked(lines)}


class TestInvokeAgent:
    @patch("jouleverne.services.agent.agentcore_client")
    def test_builds_correct_payload(self, mock_client):
        mock_client.invoke_agent_runtime.return_value = _make_response([])

        invoke_agent("hello", "session-1", web_search=False)

        call_kwargs = mock_client.invoke_agent_runtime.call_args[1]
        payload = json.loads(call_kwargs["payload"])
        assert payload["prompt"] == "hello"
        assert payload["session_id"] == "session-1"
        assert payload["enable_web_search"] is False

    @patch("jouleverne.services.agent.agentcore_client")
    def test_enables_web_search(self, mock_client):
        mock_client.invoke_agent_runtime.return_value = _make_response([])

        invoke_agent("search this", "session-2", web_search=True)

        call_kwargs = mock_client.invoke_agent_runtime.call_args[1]
        payload = json.loads(call_kwargs["payload"])
        assert payload["enable_web_search"] is True

    @patch("jouleverne.services.agent.agentcore_client")
    def test_includes_document_context(self, mock_client):
        mock_client.invoke_agent_runtime.return_value = _make_response([])

        invoke_agent(
            "summarize",
            "s1",
            session_attributes={
                "uploaded_document": "doc content",
                "document_name": "report.pdf",
                "context_mode": "full",
            },
        )

        call_kwargs = mock_client.invoke_agent_runtime.call_args[1]
        payload = json.loads(call_kwargs["payload"])
        assert payload["uploaded_document"] == "doc content"
        assert payload["document_name"] == "report.pdf"
        assert payload["context_mode"] == "full"

    @patch("jouleverne.services.agent.agentcore_client")
    def test_uses_runtime_arn(self, mock_client):
        mock_client.invoke_agent_runtime.return_value = _make_response([])

        invoke_agent("hi", "s1")

        call_kwargs = mock_client.invoke_agent_runtime.call_args[1]
        assert "agentRuntimeArn" in call_kwargs
        assert "test-runtime" in call_kwargs["agentRuntimeArn"]

    @patch("jouleverne.services.agent.agentcore_client")
    def test_forwards_capabilities(self, mock_client):
        """Explicit "own choice" capabilities are forwarded to the agent payload."""
        mock_client.invoke_agent_runtime.return_value = _make_response([])

        invoke_agent(
            "hi",
            "s1",
            capabilities={"static": ["kb_search", "web_search"], "kb_ids": ["kb-ABC"]},
        )

        call_kwargs = mock_client.invoke_agent_runtime.call_args[1]
        payload = json.loads(call_kwargs["payload"])
        assert payload["capabilities"] == {
            "static": ["kb_search", "web_search"],
            "kb_ids": ["kb-ABC"],
        }

    @patch("jouleverne.services.agent.agentcore_client")
    def test_no_capabilities_key_when_absent(self, mock_client):
        """When no capabilities are given, the payload omits the key entirely."""
        mock_client.invoke_agent_runtime.return_value = _make_response([])

        invoke_agent("hi", "s1")

        call_kwargs = mock_client.invoke_agent_runtime.call_args[1]
        payload = json.loads(call_kwargs["payload"])
        assert "capabilities" not in payload


class TestStreamAgentResponse:
    @patch("jouleverne.services.agent.agentcore_client")
    def test_yields_token_events(self, mock_client):
        mock_client.invoke_agent_runtime.return_value = _make_response([
            "Hello ",
            "world",
        ])

        events = list(stream_agent_response("hi", "s1"))
        token_events = [(t, d) for t, d in events if t == "token"]

        assert len(token_events) == 2
        assert "Hello" in token_events[0][1]
        assert "world" in token_events[1][1]

    @patch("jouleverne.services.agent.agentcore_client")
    def test_yields_done_at_end(self, mock_client):
        mock_client.invoke_agent_runtime.return_value = _make_response([])

        events = list(stream_agent_response("hi", "s1"))
        assert events[-1] == ("done", "{}")

    @patch("jouleverne.services.agent.agentcore_client")
    def test_yields_error_on_invocation_failure(self, mock_client):
        mock_client.invoke_agent_runtime.side_effect = Exception("Connection timeout")

        events = list(stream_agent_response("hi", "s1"))
        assert len(events) == 1
        assert events[0][0] == "error"
        assert "Failed to invoke agent" in events[0][1]

    @patch("jouleverne.services.agent.agentcore_client")
    def test_yields_error_when_response_key_missing(self, mock_client):
        """If the response dict doesn't have 'response' key, yield an error."""
        mock_client.invoke_agent_runtime.return_value = {"statusCode": 200}

        events = list(stream_agent_response("hi", "s1"))
        assert events[0][0] == "error"
        assert "Invalid agent response format" in events[0][1]

    @patch("jouleverne.services.agent.agentcore_client")
    def test_yields_citations(self, mock_client):
        citations_event = {
            "type": "citations",
            "citations": [
                {
                    "source_type": "kb_document",
                    "title": "Energy Report",
                    "url": "s3://bucket/file.pdf",
                    "pub_date": "2024-01-15",
                },
                {
                    "source_type": "web",
                    "title": "News Article",
                    "url": "https://example.com/article",
                    "pub_date": "2024-03-01",
                },
            ],
        }

        mock_client.invoke_agent_runtime.return_value = _make_response([
            "Answer text",
            json.dumps(citations_event),
        ])

        events = list(stream_agent_response("question", "s1"))
        citation_events = [(t, d) for t, d in events if t == "citation"]
        assert len(citation_events) == 2
        assert "s3://bucket/file.pdf" in citation_events[0][1]
        assert "https://example.com/article" in citation_events[1][1]

    @patch("jouleverne.services.agent.agentcore_client")
    def test_yields_trace_events_for_tool_start(self, mock_client):
        trace_event = {
            "type": "trace",
            "event": "tool_start",
            "tool": "filtered_kb_search",
            "input": {"query": "Energiestrategie"},
        }

        mock_client.invoke_agent_runtime.return_value = _make_response([
            json.dumps(trace_event),
            "Response text",
        ])

        events = list(stream_agent_response("hi", "s1"))
        trace_events = [(t, d) for t, d in events if t == "trace"]
        assert len(trace_events) == 1
        assert "filtered_kb_search" in trace_events[0][1]

    @patch("jouleverne.services.agent.agentcore_client")
    def test_yields_trace_events_for_tool_result(self, mock_client):
        trace_event = {
            "type": "trace",
            "event": "tool_result",
            "tool_use_id": "tooluse_123",
            "result": {"query": "test", "result_count": 3, "results": []},
        }

        mock_client.invoke_agent_runtime.return_value = _make_response([
            json.dumps(trace_event),
        ])

        events = list(stream_agent_response("hi", "s1"))
        trace_events = [(t, d) for t, d in events if t == "trace"]
        assert len(trace_events) == 1
        assert "3 Ergebnis(se) gefunden" in trace_events[0][1]

    @patch("jouleverne.services.agent.agentcore_client")
    def test_handles_stream_error_gracefully(self, mock_client):
        """If iteration over stream raises, we get an error event."""

        class FailingStream:
            def iter_chunks(self):
                yield b"start text\n"
                raise RuntimeError("stream died")

        mock_client.invoke_agent_runtime.return_value = {"response": FailingStream()}

        events = list(stream_agent_response("hi", "s1"))
        event_types = [t for t, _ in events]
        assert "token" in event_types
        assert "error" in event_types

    @patch("jouleverne.services.agent.agentcore_client")
    def test_handles_chunked_data_correctly(self, mock_client):
        """Data arriving in small chunks is buffered and split on newlines."""
        mock_client.invoke_agent_runtime.return_value = _make_response_chunked([
            "Hello world",
            json.dumps({"type": "trace", "event": "tool_start", "tool": "web_search", "input": {}}),
            "Final answer",
        ])

        events = list(stream_agent_response("hi", "s1"))
        token_events = [(t, d) for t, d in events if t == "token"]
        trace_events = [(t, d) for t, d in events if t == "trace"]

        assert len(token_events) == 2
        assert "Hello world" in token_events[0][1]
        assert "Final answer" in token_events[1][1]
        assert len(trace_events) == 1
        assert "web_search" in trace_events[0][1]

    @patch("jouleverne.services.agent.agentcore_client")
    def test_handles_remaining_buffer(self, mock_client):
        """Content without trailing newline is still processed."""

        class NoTrailingNewline:
            def iter_chunks(self):
                yield b"Last line without newline"

        mock_client.invoke_agent_runtime.return_value = {"response": NoTrailingNewline()}

        events = list(stream_agent_response("hi", "s1"))
        token_events = [(t, d) for t, d in events if t == "token"]
        assert len(token_events) == 1
        assert "Last line without newline" in token_events[0][1]

    @patch("jouleverne.services.agent.agentcore_client")
    def test_mixed_events_in_correct_order(self, mock_client):
        """Trace, text, and citation events arrive in the expected order."""
        mock_client.invoke_agent_runtime.return_value = _make_response([
            json.dumps({"type": "trace", "event": "tool_start", "tool": "aramis_search", "input": {"query": "solar"}}),
            json.dumps({"type": "trace", "event": "tool_result", "tool_use_id": "t1", "result": {"total_matches": 2, "projects": []}}),
            "Based on the search results...",
            json.dumps({"type": "citations", "citations": [{"url": "https://aramis.ch/p/123", "title": "Solar Project", "source_type": "aramis"}]}),
        ])

        events = list(stream_agent_response("solar projects", "s1"))
        event_types = [t for t, _ in events]

        # Trace events come first, then text, then citations, then done
        assert event_types == ["trace", "trace", "token", "citation", "done"]
