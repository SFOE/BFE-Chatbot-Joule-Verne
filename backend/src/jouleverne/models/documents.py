"""Document upload response models."""

from pydantic import BaseModel


class TextDocResult(BaseModel):
    """A successfully processed text document."""

    name: str
    page_count: int
    context: str
    context_mode: str
    file_id: str | None = None  # set when the original was stored server-side


class CodeInterpreterDocResult(BaseModel):
    """A document routed to Code Interpreter.

    With the reference approach, ``data`` may be omitted once the original is
    stored server-side; the agent loads it from S3 by ``file_id`` on demand.
    """

    name: str
    media_type: str
    data: str = ""  # base64 bytes (legacy/inline path); empty when referenced
    file_id: str | None = None


class IndexedDocResult(BaseModel):
    """A large text document indexed server-side (RAG).

    Only a reference is returned; the full text is NOT sent back to the client.
    The agent searches it on demand via the per-session document index.
    """

    name: str
    doc_id: str
    chunk_count: int
    file_id: str | None = None


class SessionFileResult(BaseModel):
    """A stored uploaded file of a session (for restoring the UI on load).

    ``routing`` is "inline", "index", or "ci". ``doc_id`` is set for indexed
    files. Never carries the file bytes.
    """

    file_id: str
    name: str
    media_type: str = ""
    routing: str
    doc_id: str | None = None


class DocumentError(BaseModel):
    """A document that failed processing."""

    name: str
    error: str
    sensitivity_blocked: bool = False


class DocumentUploadResponse(BaseModel):
    """Response from the document upload endpoint."""

    text_docs: list[TextDocResult]
    code_interpreter_docs: list[CodeInterpreterDocResult]
    indexed_docs: list[IndexedDocResult] = []
    errors: list[DocumentError]
    # Agent-facing metadata block describing the indexed ("teilweise") documents
    # whose text is not inlined. Echoed back by the frontend in the chat
    # request's session_attributes so the agent knows they exist. Empty when no
    # document was indexed.
    document_summary: str = ""
