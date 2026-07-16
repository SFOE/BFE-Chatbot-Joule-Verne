"""Bedrock Agent interaction — invoke and stream responses."""

import logging
from collections.abc import Generator
from typing import Any

from ..config import settings
from .clients import bedrock_client
from ..models.chat import TokenEvent, TraceEvent, CitationEvent

logger = logging.getLogger(__name__)


def invoke_agent(
    message: str,
    session_id: str,
    *,
    web_search: bool = False,
    session_attributes: dict[str, str] | None = None,
    files: list[dict] | None = None,
) -> dict:
    """Call Bedrock invoke_agent and return the raw response.

    Selects the appropriate agent based on the web_search flag.
    """
    if web_search:
        agent_id = settings.AGENT_SEARCH_ID
        alias_id = settings.AGENT_SEARCH_ALIAS_ID
    else:
        agent_id = settings.AGENT_ID
        alias_id = settings.AGENT_ALIAS_ID

    kwargs: dict[str, Any] = {
        "agentAliasId": alias_id,
        "agentId": agent_id,
        "enableTrace": True,
        "sessionId": session_id,
        "inputText": message,
    }

    session_state: dict[str, Any] = {}
    if session_attributes:
        session_state["promptSessionAttributes"] = session_attributes
    if files:
        session_state["files"] = files
    if session_state:
        kwargs["sessionState"] = session_state

    return bedrock_client.invoke_agent(**kwargs)


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
        yield "error", f'{{"detail": "Failed to invoke agent"}}'
        return

    try:
        for event in response.get("completion", []):
            # --- Text chunks ---
            if "chunk" in event:
                chunk = event["chunk"]

                # Citations
                if chunk.get("attribution"):
                    for citation in chunk["attribution"].get("citations", []):
                        for ref in citation.get("retrievedReferences", []):
                            chunk_text = ref.get("content", {}).get("text", "")
                            location = ref.get("location", {})
                            loc_type = location.get("type", "")

                            if loc_type == "S3":
                                source = location.get("s3Location", {}).get("uri", "")
                            elif loc_type == "WEB":
                                source = location.get("webLocation", {}).get("url", "")
                            else:
                                source = ""

                            if source and chunk_text:
                                evt = CitationEvent(source=source, text=chunk_text[:200])
                                yield "citation", evt.model_dump_json()

                # Token text
                text = chunk.get("bytes", b"").decode()
                if text:
                    evt = TokenEvent(text=text)
                    yield "token", evt.model_dump_json()

            # --- Trace events ---
            if "trace" in event:
                trace_data = event["trace"].get("trace", {})
                yield from _parse_trace(trace_data)

    except Exception as e:
        logger.error("Error during agent stream: %s", e)
        yield "error", f'{{"detail": "Stream interrupted"}}'
        return

    yield "done", "{}"


def _parse_trace(trace: dict) -> Generator[tuple[str, str], None, None]:
    """Parse a Bedrock trace dict and yield trace events."""

    for key, value in trace.items():
        if key == "preProcessingTrace":
            evt = TraceEvent(label="🧠 Analysiere Frage...")
            yield "trace", evt.model_dump_json()

        elif key == "orchestrationTrace" and isinstance(value, dict):
            if "rationale" in value:
                detail = value["rationale"].get("text", "")
                evt = TraceEvent(label="💭 Überlegung", detail=detail or None)
                yield "trace", evt.model_dump_json()

            elif "invocationInput" in value:
                inv = value["invocationInput"]

                if "knowledgeBaseLookupInput" in inv:
                    kb_input = inv["knowledgeBaseLookupInput"]
                    kb_id = kb_input.get("knowledgeBaseId", "")
                    query_text = kb_input.get("text", "")
                    evt = TraceEvent(
                        label="📚 Wissensdatenbank-Abfrage",
                        detail=f"Wissensdatenbank: {kb_id}\nAbfrage: {query_text}",
                    )
                    yield "trace", evt.model_dump_json()

                elif "actionGroupInvocationInput" in inv:
                    ag_input = inv["actionGroupInvocationInput"]
                    ag_name = ag_input.get("actionGroupName", "unbekannt")
                    api_path = ag_input.get("apiPath", ag_input.get("function", ""))
                    detail = f"Aktion: {ag_name}\nAPI-Pfad: {api_path}" if api_path else f"Aktion: {ag_name}"
                    evt = TraceEvent(label=f"⚙️ Aufruf: {ag_name}", detail=detail)
                    yield "trace", evt.model_dump_json()

            elif "observation" in value:
                obs = value["observation"]

                if "knowledgeBaseLookupOutput" in obs:
                    refs = obs["knowledgeBaseLookupOutput"].get("retrievedReferences", [])
                    previews = []
                    for i, ref in enumerate(refs[:5]):
                        text = ref.get("content", {}).get("text", "")
                        loc = ref.get("location", {})
                        source = ""
                        if loc.get("type") == "S3":
                            source = loc.get("s3Location", {}).get("uri", "")
                        elif loc.get("type") == "WEB":
                            source = loc.get("webLocation", {}).get("url", "")
                        preview = text[:150] + "..." if len(text) > 150 else text
                        previews.append(f"[{i+1}] {preview}\n    Quelle: {source}")
                    detail = "\n".join(previews) if previews else None
                    evt = TraceEvent(label=f"📚 {len(refs)} Ergebnis(se) gefunden", detail=detail)
                    yield "trace", evt.model_dump_json()

                elif "actionGroupInvocationOutput" in obs:
                    output_text = obs["actionGroupInvocationOutput"].get("text", "")
                    detail = output_text[:500] if output_text else None
                    evt = TraceEvent(label="⚙️ Aktionsergebnis", detail=detail)
                    yield "trace", evt.model_dump_json()

                elif "codeInterpreterInvocationOutput" in obs:
                    ci_output = obs["codeInterpreterInvocationOutput"]
                    exec_output = ci_output.get("executionOutput", "")
                    exec_error = ci_output.get("executionError", "")
                    if exec_error:
                        evt = TraceEvent(label="🖥️ Code Interpreter Fehler", detail=exec_error[:500])
                    elif exec_output:
                        evt = TraceEvent(label="🖥️ Code Interpreter", detail=exec_output[:500])
                    else:
                        evt = TraceEvent(label="🖥️ Code ausgeführt")
                    yield "trace", evt.model_dump_json()

            elif "modelInvocationInput" in value:
                evt = TraceEvent(label="🤖 Denke nach...")
                yield "trace", evt.model_dump_json()

        elif key == "postProcessingTrace":
            evt = TraceEvent(label="✍️ Antwort wird formuliert...")
            yield "trace", evt.model_dump_json()

        elif key == "failureTrace":
            reason = value.get("failureReason", "Unbekannter Fehler") if isinstance(value, dict) else "Unbekannter Fehler"
            evt = TraceEvent(label="⚠️ Fehler", detail=reason)
            yield "trace", evt.model_dump_json()
