"""Conversation history endpoints — per-user persistent chats.

All endpoints are scoped to the authenticated user's `sub` (via
`require_user_sub`); a client can never read or change another user's data.

Covered here:
- save opt-in preference (Baustein 6)
- list / save / load / rename conversations (Baustein 2)
Delete follows in Baustein 5.
"""

import asyncio

from fastapi import APIRouter, Request, Depends, HTTPException, status

from ..models.conversations import (
    SavePreference,
    SaveConversationRequest,
    ConversationSummary,
    ConversationDetail,
    RenameConversationRequest,
)
from ..services.security import limiter, verify_cognito_auth, require_user_sub
from ..services import conversations as convo
from ..services import doc_index, session_files
from ..config import settings

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


def _session_document_names(sub: str, session_id: str) -> list[str]:
    """Names of files uploaded in a session, for a fallback chat title.

    Used when a chat has no user message yet (uploads only). A saved chat's
    files live under the persistent prefix (save opt-in was on at upload).
    Best-effort — returns an empty list on any error.
    """
    try:
        prefix = doc_index.session_prefix(sub, session_id, save_history=True)
        metas = session_files.list_files(prefix)
        return [m["name"] for m in metas if m.get("name")]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Save opt-in preference
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Conversation index + transcript
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ConversationSummary])
@limiter.limit(settings.RATE_LIMIT)
async def list_conversations(
    request: Request,
    _auth: None = Depends(verify_cognito_auth),
    sub: str = Depends(require_user_sub),
):
    """List the user's conversations, most recently updated first."""
    return convo.list_conversations(sub)


@router.put("", response_model=ConversationSummary)
@limiter.limit(settings.RATE_LIMIT)
async def save_conversation(
    request: Request,
    body: SaveConversationRequest,
    _auth: None = Depends(verify_cognito_auth),
    sub: str = Depends(require_user_sub),
):
    """Upsert a conversation. Honours the user's save opt-in.

    Returns 403 when the user has not opted in, so the frontend never persists
    without consent even if it calls this endpoint.
    """
    if not convo.get_save_enabled(sub):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Saving chats is disabled for this user",
        )
    # A chat with no messages yet (only uploaded documents) still gets saved,
    # titled after its first document. Only look files up in that case to avoid
    # an S3 listing on every ordinary save.
    document_names = (
        await asyncio.to_thread(_session_document_names, sub, body.session_id)
        if not body.messages
        else None
    )
    stored = convo.save_conversation(
        sub=sub,
        session_id=body.session_id,
        messages=body.messages,
        mode_config=body.mode_config,
        document_names=document_names,
    )
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conversation persistence is not available",
        )
    loaded = convo.load_conversation(sub, body.session_id)
    return ConversationSummary(
        session_id=body.session_id,
        title=(loaded or {}).get("title", "Chat"),
        updated_at=(loaded or {}).get("updated_at", ""),
    )


@router.get("/{session_id}", response_model=ConversationDetail)
@limiter.limit(settings.RATE_LIMIT)
async def load_conversation(
    request: Request,
    session_id: str,
    _auth: None = Depends(verify_cognito_auth),
    sub: str = Depends(require_user_sub),
):
    """Load a single conversation (metadata + transcript)."""
    detail = convo.load_conversation(sub, session_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return detail


@router.patch("/{session_id}", response_model=ConversationSummary)
@limiter.limit(settings.RATE_LIMIT)
async def rename_conversation(
    request: Request,
    session_id: str,
    body: RenameConversationRequest,
    _auth: None = Depends(verify_cognito_auth),
    sub: str = Depends(require_user_sub),
):
    """Rename a conversation."""
    ok = convo.rename_conversation(sub, session_id, body.title)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or title invalid",
        )
    loaded = convo.load_conversation(sub, session_id)
    return ConversationSummary(
        session_id=session_id,
        title=(loaded or {}).get("title", "Chat"),
        updated_at=(loaded or {}).get("updated_at", ""),
    )


@router.delete("/{session_id}/ephemeral", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.RATE_LIMIT)
async def delete_ephemeral(
    request: Request,
    session_id: str,
    _auth: None = Depends(verify_cognito_auth),
    sub: str = Depends(require_user_sub),
):
    """Delete an opt-out session's short-lived agent transcript immediately.

    Called by the frontend when the user turns saving off or starts a new chat,
    so nothing lingers until the 1-day lifecycle backstop. Always 204 — a
    missing transcript is a no-op (idempotent), which also lets a best-effort
    unload beacon fire safely.
    """
    convo.delete_ephemeral_session(sub, session_id)
    return None


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.RATE_LIMIT)
async def delete_conversation(
    request: Request,
    session_id: str,
    _auth: None = Depends(verify_cognito_auth),
    sub: str = Depends(require_user_sub),
):
    """Delete a conversation and all associated data.

    Removes the index entry, the transcript, the agent's stored history, and
    the session's feedback objects. Available regardless of the save opt-in,
    so a user can always clean up previously saved chats.
    """
    ok = convo.delete_conversation(sub, session_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return None
