"""Feedback request/response models."""

from pydantic import BaseModel


class FeedbackRequest(BaseModel):
    """Incoming feedback from the frontend."""

    session_id: str
    message_index: int
    rating: str | None = None
    user_query: str
    agent_response: str
    agent_variant: str = "default"
    comment: str | None = None
    retrieved_chunks: list[dict] | None = None
    tools_used: list[str] | None = None
    s3_key_override: str | None = None
    original_timestamp: str | None = None


class FeedbackResponse(BaseModel):
    """Response after saving feedback."""

    s3_key: str | None
    timestamp: str | None
