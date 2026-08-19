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

        # The AgentCore runtime wraps each yielded value as:
        #   data: <json_value>
        # Messages MAY be separated by newlines, but newlines can also
        # appear INSIDE JSON string values (e.g. data: "\n\n---").
        # We use a JSON-aware parser: find "data:" prefix, then extract
        # the complete JSON value by tracking balanced delimiters.
        buffer = ""
        chunk_count = 0
        for chunk in stream.iter_chunks():
            raw = chunk if isinstance(chunk, bytes) else chunk.encode()
            chunk_count += 1
            # Log first 5 chunks at WARNING level so they always show
            if chunk_count <= 5:
                logger.warning("STREAM CHUNK #%d (%d bytes): %r", chunk_count, len(raw), raw[:500])
            buffer += chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk

            # Extract and process all complete messages from the buffer
            buffer = yield from _process_buffer(buffer, locale)

        # Process any remaining buffer after stream ends
        if buffer.strip():
            logger.warning("REMAINING BUFFER (%d chars): %r", len(buffer), buffer[:500])
            yield from _process_buffer(buffer, locale, final=True)

    except Exception as e:
        logger.error("Error during agent stream: %s", e)
        yield "error", '{"detail": "Stream interrupted"}'
        return

    yield "done", "{}"


# ---------------------------------------------------------------------------
# JSON-aware SSE stream parsing helpers
# ---------------------------------------------------------------------------

def _extract_json_value(payload: str) -> tuple[object | None, str]:
    """Extract one complete JSON value from the start of a string.

    Returns (parsed_value, remaining_string) or (None, "") if incomplete.

    Handles: strings ("..."), objects ({...}), arrays ([...]), numbers,
    booleans, and null.
    """
    # Skip any leading whitespace
    i = 0
    while i < len(payload) and payload[i] in " \t\r\n":
        i += 1

    if i >= len(payload):
        return None, ""

    ch = payload[i]

    if ch == '"':
        # JSON string — find the closing quote, respecting escapes
        j = i + 1
        while j < len(payload):
            if payload[j] == '\\':
                j += 2  # skip escaped character
                continue
            if payload[j] == '"':
                # Found closing quote — extract the complete string
                raw = payload[i:j + 1]
                try:
                    value = json.loads(raw)
                    return value, payload[j + 1:]
                except json.JSONDecodeError:
                    return None, ""
            j += 1
        # No closing quote found — incomplete
        return None, ""

    elif ch == '{':
        # JSON object — find matching closing brace
        end = _find_balanced(payload, i, '{', '}')
        if end == -1:
            return None, ""
        raw = payload[i:end + 1]
        try:
            value = json.loads(raw)
            return value, payload[end + 1:]
        except json.JSONDecodeError:
            return None, ""

    elif ch == '[':
        # JSON array — find matching closing bracket
        end = _find_balanced(payload, i, '[', ']')
        if end == -1:
            return None, ""
        raw = payload[i:end + 1]
        try:
            value = json.loads(raw)
            return value, payload[end + 1:]
        except json.JSONDecodeError:
            return None, ""

    else:
        # Number, boolean, or null — read until we hit something that
        # can't be part of a primitive value
        j = i
        while j < len(payload) and payload[j] not in ' \t\r\n,}]':
            j += 1
        if j == i:
            return None, ""
        raw = payload[i:j]
        try:
            value = json.loads(raw)
            return value, payload[j:]
        except json.JSONDecodeError:
            return None, ""


def _find_balanced(s: str, start: int, open_ch: str, close_ch: str) -> int:
    """Find the index of the closing bracket/brace that balances s[start].

    Respects JSON string quoting (skips content inside double quotes).
    Returns -1 if not found (incomplete).
    """
    depth = 0
    i = start
    in_string = False
    while i < len(s):
        ch = s[i]
        if in_string:
            if ch == '\\':
                i += 2
                continue
            if ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def _process_buffer(
    buffer: str, locale: str, final: bool = False
) -> Generator[tuple[str, str], None, str]:
    """Extract and yield all complete SSE messages from the buffer.

    Returns the remaining (unprocessed) buffer content via generator return.
    Usage: buffer = yield from _process_buffer(buffer, locale)

    When final=True, any remaining unparseable content is yielded as a token
    instead of being held in the buffer.

    Handles two formats:
    - SSE wrapped: data: <json_value>
    - Raw: <json_value> (newline-separated, no prefix)
    """
    while buffer:
        # Skip leading whitespace/newlines between messages
        stripped = buffer.lstrip(" \t\r\n")
        if not stripped:
            return ""

        # Determine if this message has an SSE "data:" prefix
        if stripped.startswith("data: "):
            payload = stripped[6:]
        elif stripped.startswith("data:"):
            payload = stripped[5:]
        else:
            # No "data:" prefix — try to parse as raw JSON value directly.
            # If that fails, it could be plain text up to the next newline.
            payload = stripped

        # Extract one complete JSON value
        json_value, remainder = _extract_json_value(payload)
        if json_value is None:
            # Could not parse JSON — check if there's a newline-delimited
            # plain text line we can yield as a token
            newline_idx = stripped.find("\n")
            if newline_idx != -1:
                # Yield the line up to the newline as plain text
                line = stripped[:newline_idx].strip()
                # Strip data: prefix from the line if present
                if line.startswith("data: "):
                    line = line[6:]
                elif line.startswith("data:"):
                    line = line[5:]
                if line:
                    logger.warning("FALLBACK TEXT LINE: %r", line[:200])
                    evt = TokenEvent(text=line)
                    yield "token", evt.model_dump_json()
                buffer = stripped[newline_idx + 1:]
                continue
            elif final:
                # No more data coming — yield whatever is left as text
                text = stripped.strip()
                # Strip data: prefix if present
                if text.startswith("data: "):
                    text = text[6:]
                elif text.startswith("data:"):
                    text = text[5:]
                if text:
                    logger.warning("FALLBACK FINAL TEXT: %r", text[:200])
                    evt = TokenEvent(text=text)
                    yield "token", evt.model_dump_json()
                return ""
            else:
                # Incomplete — wait for more data
                return stripped

        buffer = remainder

        # Route the parsed value to the appropriate event type
        yield from _route_parsed_value(json_value, locale)

    return ""


def _route_parsed_value(
    value: object, locale: str
) -> Generator[tuple[str, str], None, None]:
    """Route a parsed JSON value to the correct event type and yield it."""
    if isinstance(value, str):
        # Text delta from the model
        evt = TokenEvent(text=value)
        yield "token", evt.model_dump_json()

    elif isinstance(value, dict):
        if value.get("type") == "trace":
            yield from _parse_agentcore_trace(value, locale)
        elif value.get("type") == "citations":
            for citation in value.get("citations", []):
                url = citation.get("url", "")
                source_type = citation.get("source_type", "")
                title = citation.get("title", "")
                if url:
                    evt = CitationEvent(source=url, text=title, source_type=source_type)
                    yield "citation", evt.model_dump_json()
        else:
            # Unknown dict — yield as token for safety
            evt = TokenEvent(text=json.dumps(value, ensure_ascii=False))
            yield "token", evt.model_dump_json()

    # Other types (numbers, arrays, etc.) — unlikely but handle gracefully
    elif value is not None:
        evt = TokenEvent(text=str(value))
        yield "token", evt.model_dump_json()


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
