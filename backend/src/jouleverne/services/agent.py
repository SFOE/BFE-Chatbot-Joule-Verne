"""AgentCore Runtime interaction — invoke and stream responses."""

import json
import logging
from collections.abc import Generator

from ..config import settings
from .clients import agentcore_client
from ..models.chat import TokenEvent, TraceEvent, CitationEvent

# Parse KB display names from config: "id1:Name1,id2:Name2" → {id1: Name1, ...}
_kb_names: dict[str, str] = {}
for pair in settings.KB_DISPLAY_NAMES.split(","):
    pair = pair.strip()
    if ":" in pair:
        kb_id, name = pair.split(":", 1)
        _kb_names[kb_id.strip()] = name.strip()


def _kb_display_name(kb_id: str) -> str:
    """Return a human-friendly name for a knowledge base ID."""
    return _kb_names.get(kb_id, "BFE-Wissensdatenbank")

logger = logging.getLogger(__name__)

# Map tool names to user-facing status labels (German)
TOOL_LABEL_MAP = {
    "filtered_kb_search": "Wissensdatenbank wird durchsucht...",
    "aramis_search": "ARAMIS wird durchsucht...",
    "aramis_project_details": "Projektdetails werden geladen...",
    "web_search": "Websuche wird durchgeführt...",
    "code_interpreter": "Code wird ausgeführt...",
}


def invoke_agent(
    message: str,
    session_id: str,
    *,
    web_search: bool = False,
    session_attributes: dict[str, str] | None = None,
    files: list[dict] | None = None,
) -> dict:
    """Call AgentCore invoke_agent_runtime and return the raw streaming response.

    Args:
        message: User message text.
        session_id: Session identifier for conversation continuity.
        web_search: Whether to enable the web search tool.
        session_attributes: Dict with uploaded_document, document_name, context_mode.
        files: Code Interpreter files (not yet supported in AgentCore).

    Returns:
        AgentCore Runtime streaming response dict.
    """
    payload: dict = {
        "prompt": message,
        "session_id": session_id,
        "enable_web_search": web_search,
        "include_trace": True,
    }

    # Document context (replaces Classic's sessionState.promptSessionAttributes)
    if session_attributes:
        if "uploaded_document" in session_attributes:
            payload["uploaded_document"] = session_attributes["uploaded_document"]
        if "document_name" in session_attributes:
            payload["document_name"] = session_attributes["document_name"]
        if "context_mode" in session_attributes:
            payload["context_mode"] = session_attributes["context_mode"]

    # Code Interpreter file upload not yet supported in AgentCore
    if files:
        logger.warning(
            "Code Interpreter file upload not yet supported in AgentCore. "
            "Files ignored — use uploaded_document for text-based content."
        )

    return agentcore_client.invoke_agent_runtime(
        agentRuntimeArn=settings.AGENTCORE_RUNTIME_ARN,
        payload=json.dumps(payload).encode("utf-8"),
    )


def stream_agent_response(
    message: str,
    session_id: str,
    *,
    web_search: bool = False,
    session_attributes: dict[str, str] | None = None,
    files: list[dict] | None = None,
) -> Generator[tuple[str, str], None, None]:
    """Invoke the agent and yield (event_type, json_data) tuples.

    Event types: "token", "trace", "citation", "done", "error"

    The AgentCore runtime streams chunks that are either:
    - JSON objects with a "type" field (trace events, citations)
    - Plain text (response tokens to display)
    """
    try:
        response = invoke_agent(
            message,
            session_id,
            web_search=web_search,
            session_attributes=session_attributes,
            files=files,
        )
    except Exception as e:
        logger.error("Failed to invoke agent: %s", e)
        yield "error", '{"detail": "Failed to invoke agent"}'
        return

    try:
        for event in response.get("body", []):
            chunk = event.get("chunk", {})
            if "bytes" not in chunk:
                continue

            text = chunk["bytes"].decode("utf-8")

            # Try to parse as structured JSON event
            try:
                data = json.loads(text)

                if data.get("type") == "trace":
                    yield from _parse_agentcore_trace(data)
                    continue

                if data.get("type") == "citations":
                    for citation in data.get("citations", []):
                        url = citation.get("url", "")
                        source_type = citation.get("source_type", "")
                        title = citation.get("title", "")
                        if url:
                            evt = CitationEvent(source=url, text=title, source_type=source_type)
                            yield "citation", evt.model_dump_json()
                    continue

            except (json.JSONDecodeError, TypeError, KeyError):
                pass

            # Plain text — yield as token
            if text:
                evt = TokenEvent(text=text)
                yield "token", evt.model_dump_json()

    except Exception as e:
        logger.error("Error during agent stream: %s", e)
        yield "error", '{"detail": "Stream interrupted"}'
        return

    yield "done", "{}"


def _parse_agentcore_trace(data: dict) -> Generator[tuple[str, str], None, None]:
    """Parse an AgentCore trace event and yield (event_type, json_data) tuples.

    Trace events from AgentCore:
    - tool_start: agent is calling a tool (with tool name + input)
    - tool_result: tool returned its result (with full output)
    """
    event_name = data.get("event", "")

    if event_name == "tool_start":
        tool_name = data.get("tool", "unknown")
        tool_input = data.get("input", {})
        label = TOOL_LABEL_MAP.get(tool_name, f"{tool_name}...")
        detail = json.dumps(tool_input, ensure_ascii=False, indent=2) if tool_input else None
        evt = TraceEvent(label=f"Aufruf: {tool_name}", detail=detail, tool=tool_name)
        yield "trace", evt.model_dump_json()

    elif event_name == "tool_result":
        result = data.get("result", {})
        result_count = result.get("result_count", result.get("total_matches", ""))

        # Use KB display name for filtered_kb_search results
        tool_name = data.get("tool", "")
        if tool_name == "filtered_kb_search":
            kb_id = data.get("input", {}).get("knowledge_base_id", "")
            kb_name = _kb_display_name(kb_id)
            if result_count:
                evt = TraceEvent(
                    label=f"{kb_name}: {result_count} Ergebnis(se) gefunden",
                    detail=json.dumps(result, ensure_ascii=False)[:500],
                )
            else:
                evt = TraceEvent(
                    label=f"{kb_name}: Ergebnis erhalten",
                    detail=json.dumps(result, ensure_ascii=False)[:500],
                )
        elif result_count:
            evt = TraceEvent(
                label=f"{result_count} Ergebnis(se) gefunden",
                detail=json.dumps(result, ensure_ascii=False)[:500],
            )
        else:
            evt = TraceEvent(
                label="Ergebnis erhalten",
                detail=json.dumps(result, ensure_ascii=False)[:500],
            )
        yield "trace", evt.model_dump_json()
