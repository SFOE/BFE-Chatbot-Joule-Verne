"""AgentCore Runtime interaction — invoke and stream responses."""

import json
import logging
from collections.abc import Generator

from ..config import settings
from .clients import agentcore_client
from ..models.chat import TokenEvent, TraceEvent, CitationEvent

# Parse KB display names from config
# Format: "id1:DE_Name|FR_Name|IT_Name|EN_Name, id2:DE|FR|IT|EN"
# Or simple (German-only): "id1:Name1,id2:Name2"
_kb_names: dict[str, dict[str, str]] = {}
for pair in settings.KB_DISPLAY_NAMES.split(","):
    pair = pair.strip()
    if ":" in pair:
        kb_id, names_str = pair.split(":", 1)
        parts = names_str.strip().split("|")
        if len(parts) == 4:
            _kb_names[kb_id.strip()] = {
                "de": parts[0].strip(),
                "fr": parts[1].strip(),
                "it": parts[2].strip(),
                "en": parts[3].strip(),
            }
        else:
            # Single name — use for all locales
            name = names_str.strip()
            _kb_names[kb_id.strip()] = {"de": name, "fr": name, "it": name, "en": name}


def _kb_display_name(kb_id: str, locale: str = "de") -> str:
    """Return a human-friendly name for a knowledge base ID."""
    if kb_id in _kb_names:
        return _kb_names[kb_id].get(locale, _kb_names[kb_id].get("de", kb_id))
    # Fallback name per locale
    _fallback_names = {
        "de": "BFE-Wissensdatenbank",
        "fr": "Base de connaissances OFEN",
        "it": "Base di conoscenze UFE",
        "en": "SFOE knowledge base",
    }
    return _fallback_names.get(locale, _fallback_names["de"])


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
    "results_found": {
        "de": "{kb_name}: {count} Ergebnis(se) gefunden",
        "fr": "{kb_name}: {count} résultat(s) trouvé(s)",
        "it": "{kb_name}: {count} risultato/i trovato/i",
        "en": "{kb_name}: {count} result(s) found",
    },
    "results_found_generic": {
        "de": "{count} Ergebnis(se) gefunden",
        "fr": "{count} résultat(s) trouvé(s)",
        "it": "{count} risultato/i trovato/i",
        "en": "{count} result(s) found",
    },
    "result_received": {
        "de": "{kb_name}: Ergebnis erhalten",
        "fr": "{kb_name}: Résultat reçu",
        "it": "{kb_name}: Risultato ricevuto",
        "en": "{kb_name}: Result received",
    },
    "result_received_generic": {
        "de": "Ergebnis erhalten",
        "fr": "Résultat reçu",
        "it": "Risultato ricevuto",
        "en": "Result received",
    },
    "tool_kb_search": {
        "de": "Wissensdatenbank wird durchsucht...",
        "fr": "Recherche dans la base de connaissances...",
        "it": "Ricerca nella base di conoscenze...",
        "en": "Searching knowledge base...",
    },
    "tool_aramis_search": {
        "de": "ARAMIS wird durchsucht...",
        "fr": "Recherche dans ARAMIS...",
        "it": "Ricerca in ARAMIS...",
        "en": "Searching ARAMIS...",
    },
    "tool_aramis_details": {
        "de": "Projektdetails werden geladen...",
        "fr": "Chargement des détails du projet...",
        "it": "Caricamento dei dettagli del progetto...",
        "en": "Loading project details...",
    },
    "tool_web_search": {
        "de": "Websuche wird durchgeführt...",
        "fr": "Recherche web en cours...",
        "it": "Ricerca web in corso...",
        "en": "Performing web search...",
    },
    "tool_code_interpreter": {
        "de": "Code wird ausgeführt...",
        "fr": "Exécution du code...",
        "it": "Esecuzione del codice...",
        "en": "Executing code...",
    },
}


def _t(key: str, locale: str, **kwargs: str) -> str:
    """Get a translated trace label, with optional format parameters."""
    translations = _TRACE_LABELS.get(key, {})
    template = translations.get(locale, translations.get("de", key))
    return template.format(**kwargs) if kwargs else template

logger = logging.getLogger(__name__)

# Map tool names to translation keys for user-facing status labels
TOOL_LABEL_MAP: dict[str, str] = {
    "filtered_kb_search": "tool_kb_search",
    "aramis_search": "tool_aramis_search",
    "aramis_project_details": "tool_aramis_details",
    "web_search": "tool_web_search",
    "code_interpreter": "tool_code_interpreter",
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
    locale: str = "de",
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
        # AgentCore returns a StreamingBody in response["response"]
        stream = response.get("response")
        if stream is None:
            logger.error("No 'response' key in AgentCore response: %s", list(response.keys()))
            yield "error", '{"detail": "Invalid agent response format"}'
            return

        # The AgentCore runtime wraps output in SSE format: "data: <json>\n\n"
        # We need to parse SSE lines, stripping the "data: " prefix.
        buffer = ""
        for chunk in stream.iter_chunks():
            buffer += chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk

            # Process complete lines
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)

                # Strip SSE "data: " prefix if present
                if line.startswith("data: "):
                    text = line[6:]
                elif line.startswith("data:"):
                    text = line[5:]
                else:
                    text = line.strip()

                if not text:
                    continue

                # Try to parse as structured JSON event
                try:
                    data = json.loads(text)

                    # If it's a plain string (JSON-encoded text delta), yield as token
                    if isinstance(data, str):
                        evt = TokenEvent(text=data)
                        yield "token", evt.model_dump_json()
                        continue

                    if isinstance(data, dict):
                        if data.get("type") == "trace":
                            yield from _parse_agentcore_trace(data, locale)
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

                except (json.JSONDecodeError, TypeError, KeyError, AttributeError):
                    pass

                # Plain text (not valid JSON) — yield as token
                if text:
                    evt = TokenEvent(text=text)
                    yield "token", evt.model_dump_json()

        # Process any remaining buffer content
        remaining = buffer.strip()
        if remaining:
            # Strip SSE prefix from remaining buffer too
            if remaining.startswith("data: "):
                remaining = remaining[6:]
            elif remaining.startswith("data:"):
                remaining = remaining[5:]

            if remaining:
                try:
                    data = json.loads(remaining)
                    if isinstance(data, str):
                        evt = TokenEvent(text=data)
                        yield "token", evt.model_dump_json()
                    elif isinstance(data, dict):
                        if data.get("type") == "trace":
                            yield from _parse_agentcore_trace(data, locale)
                        elif data.get("type") == "citations":
                            for citation in data.get("citations", []):
                                url = citation.get("url", "")
                                source_type = citation.get("source_type", "")
                                title = citation.get("title", "")
                                if url:
                                    evt = CitationEvent(source=url, text=title, source_type=source_type)
                                    yield "citation", evt.model_dump_json()
                        else:
                            evt = TokenEvent(text=remaining)
                            yield "token", evt.model_dump_json()
                    else:
                        evt = TokenEvent(text=remaining)
                        yield "token", evt.model_dump_json()
                except (json.JSONDecodeError, TypeError, KeyError, AttributeError):
                    evt = TokenEvent(text=remaining)
                    yield "token", evt.model_dump_json()

    except Exception as e:
        logger.error("Error during agent stream: %s", e)
        yield "error", '{"detail": "Stream interrupted"}'
        return

    yield "done", "{}"


def _parse_agentcore_trace(data: dict, locale: str = "de") -> Generator[tuple[str, str], None, None]:
    """Parse an AgentCore trace event and yield (event_type, json_data) tuples.

    Trace events from AgentCore:
    - tool_start: agent is calling a tool (with tool name + input)
    - tool_result: tool returned its result (with full output)
    - error: an error occurred during processing
    """
    event_name = data.get("event", "")

    if event_name == "tool_start":
        tool_name = data.get("tool", "unknown")
        tool_input = data.get("input", {})
        label_key = TOOL_LABEL_MAP.get(tool_name)
        label = _t(label_key, locale) if label_key else _t("calling", locale, name=tool_name)
        detail = json.dumps(tool_input, ensure_ascii=False, indent=2) if tool_input else None
        evt = TraceEvent(label=label, detail=detail, tool=tool_name)
        yield "trace", evt.model_dump_json()

    elif event_name == "tool_result":
        result = data.get("result", {})
        result_count = result.get("result_count", result.get("total_matches", ""))

        # Use KB display name for filtered_kb_search results
        tool_name = data.get("tool", "")
        if tool_name == "filtered_kb_search":
            kb_id = data.get("input", {}).get("knowledge_base_id", "")
            kb_name = _kb_display_name(kb_id, locale)
            if result_count:
                evt = TraceEvent(
                    label=_t("results_found", locale, kb_name=kb_name, count=str(result_count)),
                    detail=json.dumps(result, ensure_ascii=False)[:500],
                )
            else:
                evt = TraceEvent(
                    label=_t("result_received", locale, kb_name=kb_name),
                    detail=json.dumps(result, ensure_ascii=False)[:500],
                )
        elif result_count:
            evt = TraceEvent(
                label=_t("results_found_generic", locale, count=str(result_count)),
                detail=json.dumps(result, ensure_ascii=False)[:500],
            )
        else:
            evt = TraceEvent(
                label=_t("result_received_generic", locale),
                detail=json.dumps(result, ensure_ascii=False)[:500],
            )
        yield "trace", evt.model_dump_json()

    elif event_name == "error":
        reason = data.get("message", data.get("detail", _t("unknown_error", locale)))
        evt = TraceEvent(label=_t("error", locale), detail=reason)
        yield "trace", evt.model_dump_json()
