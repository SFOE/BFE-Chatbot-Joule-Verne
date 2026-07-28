"""Bedrock Agent interaction — invoke and stream responses."""

import logging
from collections.abc import Generator
from typing import Any

from ..config import settings
from .clients import bedrock_client
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


# ---------------------------------------------------------------------------
# Trace label translations
# ---------------------------------------------------------------------------
_TRACE_LABELS: dict[str, dict[str, str]] = {
    "analyzing_question": {
        "de": "Analysiere Frage...",
        "fr": "Analyse de la question...",
        "it": "Analisi della domanda...",
        "en": "Analyzing question...",
    },
    "reasoning": {
        "de": "Überlegung",
        "fr": "Réflexion",
        "it": "Riflessione",
        "en": "Reasoning",
    },
    "searching_kb": {
        "de": "{kb_name} wird durchsucht",
        "fr": "Recherche dans {kb_name}",
        "it": "Ricerca in {kb_name}",
        "en": "Searching {kb_name}",
    },
    "query_prefix": {
        "de": "Abfrage: {text}",
        "fr": "Requête : {text}",
        "it": "Query: {text}",
        "en": "Query: {text}",
    },
    "calling": {
        "de": "Aufruf: {name}",
        "fr": "Appel : {name}",
        "it": "Chiamata: {name}",
        "en": "Calling: {name}",
    },
    "action_detail": {
        "de": "Aktion: {name}\nAPI-Pfad: {path}",
        "fr": "Action : {name}\nChemin API : {path}",
        "it": "Azione: {name}\nPercorso API: {path}",
        "en": "Action: {name}\nAPI path: {path}",
    },
    "action_detail_short": {
        "de": "Aktion: {name}",
        "fr": "Action : {name}",
        "it": "Azione: {name}",
        "en": "Action: {name}",
    },
    "code_interpreter_error": {
        "de": "Code Interpreter Fehler",
        "fr": "Erreur Code Interpreter",
        "it": "Errore Code Interpreter",
        "en": "Code Interpreter Error",
    },
    "code_interpreter": {
        "de": "Code Interpreter",
        "fr": "Code Interpreter",
        "it": "Code Interpreter",
        "en": "Code Interpreter",
    },
    "code_executed": {
        "de": "Code ausgeführt",
        "fr": "Code exécuté",
        "it": "Codice eseguito",
        "en": "Code executed",
    },
    "error": {
        "de": "Fehler",
        "fr": "Erreur",
        "it": "Errore",
        "en": "Error",
    },
    "unknown_error": {
        "de": "Unbekannter Fehler",
        "fr": "Erreur inconnue",
        "it": "Errore sconosciuto",
        "en": "Unknown error",
    },
}


def _t(key: str, locale: str, **kwargs: str) -> str:
    """Get a translated trace label, with optional format parameters."""
    translations = _TRACE_LABELS.get(key, {})
    template = translations.get(locale, translations.get("de", key))
    return template.format(**kwargs) if kwargs else template

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
    locale: str = "de",
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
                                evt = CitationEvent(source=source, text=chunk_text)
                                yield "citation", evt.model_dump_json()

                # Token text
                text = chunk.get("bytes", b"").decode()
                if text:
                    evt = TokenEvent(text=text)
                    yield "token", evt.model_dump_json()

            # --- Trace events ---
            if "trace" in event:
                trace_data = event["trace"].get("trace", {})
                yield from _parse_trace(trace_data, locale)

    except Exception as e:
        logger.error("Error during agent stream: %s", e)
        yield "error", f'{{"detail": "Stream interrupted"}}'
        return

    yield "done", "{}"


def _parse_trace(trace: dict, locale: str = "de") -> Generator[tuple[str, str], None, None]:
    """Parse a Bedrock trace dict and yield trace events."""

    for key, value in trace.items():
        if key == "preProcessingTrace":
            pass  # Suppressed

        elif key == "orchestrationTrace" and isinstance(value, dict):
            if "rationale" in value:
                detail = value["rationale"].get("text", "")
                evt = TraceEvent(label=_t("reasoning", locale), detail=detail or None)
                yield "trace", evt.model_dump_json()

            elif "invocationInput" in value:
                inv = value["invocationInput"]

                if "knowledgeBaseLookupInput" in inv:
                    kb_input = inv["knowledgeBaseLookupInput"]
                    kb_id = kb_input.get("knowledgeBaseId", "")
                    query_text = kb_input.get("text", "")
                    kb_name = _kb_display_name(kb_id)
                    detail = _t("query_prefix", locale, text=query_text) if query_text else None
                    evt = TraceEvent(
                        label=_t("searching_kb", locale, kb_name=kb_name),
                        detail=detail,
                    )
                    yield "trace", evt.model_dump_json()

                elif "actionGroupInvocationInput" in inv:
                    ag_input = inv["actionGroupInvocationInput"]
                    ag_name = ag_input.get("actionGroupName", "unbekannt")
                    api_path = ag_input.get("apiPath", ag_input.get("function", ""))
                    if api_path:
                        detail = _t("action_detail", locale, name=ag_name, path=api_path)
                    else:
                        detail = _t("action_detail_short", locale, name=ag_name)
                    evt = TraceEvent(label=_t("calling", locale, name=ag_name), detail=detail)
                    yield "trace", evt.model_dump_json()

            elif "observation" in value:
                obs = value["observation"]

                if "knowledgeBaseLookupOutput" in obs:
                    pass

                elif "actionGroupInvocationOutput" in obs:
                    pass

                elif "codeInterpreterInvocationOutput" in obs:
                    ci_output = obs["codeInterpreterInvocationOutput"]
                    exec_output = ci_output.get("executionOutput", "")
                    exec_error = ci_output.get("executionError", "")
                    if exec_error:
                        evt = TraceEvent(label=_t("code_interpreter_error", locale), detail=exec_error[:500])
                        yield "trace", evt.model_dump_json()
                    elif exec_output:
                        evt = TraceEvent(label=_t("code_interpreter", locale), detail=exec_output[:500])
                        yield "trace", evt.model_dump_json()
                    # else: suppress "Code ausgeführt" (no useful info)

            elif "modelInvocationInput" in value:
                pass

        elif key == "postProcessingTrace":
            pass

        elif key == "failureTrace":
            reason = value.get("failureReason", _t("unknown_error", locale)) if isinstance(value, dict) else _t("unknown_error", locale)
            evt = TraceEvent(label=_t("error", locale), detail=reason)
            yield "trace", evt.model_dump_json()
