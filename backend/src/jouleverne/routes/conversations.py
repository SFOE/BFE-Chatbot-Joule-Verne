"""Conversation history endpoints — per-user persistent chats.

All endpoints are scoped to the authenticated user's `sub` (via
`require_user_sub`); a client can never read or change another user's data.

This module currently exposes the save opt-in preference (Baustein 6). List /
load / rename / delete of conversations are added in later increments.
"""

from fastapi import APIRouter, Request, Depends

from ..models.conversations import SavePreference
from ..services.security import limiter, verify_cognito_auth, require_user_sub
from ..services import conversations as convo
from ..config import settings

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.get("/preference", response_model=SavePreference)
@limiter.limit(settings.RATE_LIMIT)
async def get_preference(
    request: Request,
    _auth: None = Depends(verify_cognito_auth),
    sub: str = Depends(require_user_sub),
):
    """Return whether the user has opted in to saving chats (default: off)."""
    return SavePreference(save_enabled=convo.get_save_enabled(sub))


@router.put("/preference", response_model=SavePreference)
@limiter.limit(settings.RATE_LIMIT)
async def set_preference(
    request: Request,
    body: SavePreference,
    _auth: None = Depends(verify_cognito_auth),
    sub: str = Depends(require_user_sub),
):
    """Set the save opt-in flag.

    Turning it off stops new chats from being persisted but keeps existing
    conversations intact (they remain listable and deletable).
    """
    stored = convo.set_save_enabled(sub, body.save_enabled)
    return SavePreference(save_enabled=stored)
