from typing import Any

from pydantic import BaseModel


class CodeInterpreterFile(BaseModel):
    """A file to send to Bedrock Code Interpreter."""

    name: str
    media_type: str
    data: str  # base64-encoded


class Capabilities(BaseModel):
    """Explicit capability grant for "own choice" mode.

    When present, the agent is composed from exactly these capabilities:
    - static: capability keys (e.g. "kb_search", "aramis", "web_search",
      "code_interpreter") matching the agent's CAPABILITY_REGISTRY.
    - kb_ids: specific Knowledge Base IDs to attach (validated agent-side).
    """

    static: list[str] = []
    kb_ids: list[str] = []


class ChatRequest(BaseModel):
    """Incoming chat message from the frontend."""

    message: str
    session_id: str
    web_search: bool = False
    locale: str = "de"
    session_attributes: dict[str, str] | None = None
    files: list[CodeInterpreterFile] | None = None
    agent_type: str = "default"
    specific_kb_id: str | None = None
    capabilities: Capabilities | None = None


class TokenEvent(BaseModel):
    """A streamed text chunk from the agent."""

    text: str


class TraceEvent(BaseModel):
    """A reasoning/trace step from the agent."""

    label: str
    detail: str | None = None
    tool: str | None = None


class CitationEvent(BaseModel):
    """A source citation returned by the agent."""

    source: str
    text: str
    source_type: str = ""
