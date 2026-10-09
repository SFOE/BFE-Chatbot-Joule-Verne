"""Conversation history request/response models."""

from typing import Any

from pydantic import BaseModel


class SavePreference(BaseModel):
    """The user's opt-in flag for persisting chats."""

    save_enabled: bool


class SaveConversationRequest(BaseModel):
    """Upsert a conversation's transcript + index entry.

    `messages` is the frontend chat message array (role/content plus optional
    traceSteps/citations/feedback keys); it is stored verbatim so the UI can
    re-render the conversation exactly on load. `mode_config` captures the
    tool/mode selection for continuation.
    """

    session_id: str
    messages: list[dict[str, Any]]
    mode_config: dict[str, Any] | None = None


class ConversationSummary(BaseModel):
    """One entry in the user's chat list (no transcript)."""

    session_id: str
    title: str
    updated_at: str


class ConversationDetail(BaseModel):
    """A full conversation: index metadata plus the stored transcript."""

    session_id: str
    title: str
    updated_at: str
    mode_config: dict[str, Any] | None = None
    messages: list[dict[str, Any]] = []


class RenameConversationRequest(BaseModel):
    """Rename a conversation."""

    title: str
