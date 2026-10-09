"""Conversation history request/response models."""

from pydantic import BaseModel


class SavePreference(BaseModel):
    """The user's opt-in flag for persisting chats."""

    save_enabled: bool
