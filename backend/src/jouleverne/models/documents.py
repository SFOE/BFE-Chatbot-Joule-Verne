"""Document upload response models."""

from pydantic import BaseModel


class TextDocResult(BaseModel):
    """A successfully processed text document."""

    name: str
    page_count: int
    context: str
    context_mode: str


class CodeInterpreterDocResult(BaseModel):
    """A document routed to Code Interpreter."""

    name: str
    media_type: str


class DocumentError(BaseModel):
    """A document that failed processing."""

    name: str
    error: str


class DocumentUploadResponse(BaseModel):
    """Response from the document upload endpoint."""

    text_docs: list[TextDocResult]
    code_interpreter_docs: list[CodeInterpreterDocResult]
    errors: list[DocumentError]
