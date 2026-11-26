"""Admin API for editing the agent's system prompts (restricted by e-mail)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..config import settings
from ..services import prompt_overrides as prompts
from ..services.security import (
    is_prompt_admin,
    limiter,
    verify_cognito_auth,
    verify_prompt_admin,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin/prompts", tags=["admin-prompts"])


class PromptBody(BaseModel):
    text: str


def _require_configured() -> None:
    if not prompts.is_configured():
        raise HTTPException(status_code=500, detail="Prompt storage is not configured.")


def _check_key(key: str) -> None:
    if not prompts.KEY_RE.match(key):
        raise HTTPException(status_code=400, detail="Invalid prompt key.")


@router.get("/access")
@limiter.limit(settings.RATE_LIMIT)
def prompt_admin_access(
    request: Request,
    _auth: None = Depends(verify_cognito_auth),
):
    """Tell the UI whether to show the admin link. Never raises 403."""
    return {"allowed": is_prompt_admin(request)}


@router.get("")
@limiter.limit(settings.RATE_LIMIT)
def list_prompts(
    request: Request,
    _auth: None = Depends(verify_cognito_auth),
    _admin: str = Depends(verify_prompt_admin),
):
    """All editable prompt parts with default text and current override (or null)."""
    _require_configured()
    defaults = prompts.get_defaults()
    overrides = prompts.get_overrides()
    known = {p["key"] for p in defaults}

    items = [
        {
            "key": p["key"],
            "label": p.get("label", p["key"]),
            "group": p.get("group", "capability"),
            "default": p.get("default", ""),
            "override": overrides.get(p["key"]),
        }
        for p in defaults
    ]
    # Overrides whose key the agent no longer knows stay visible so they can be reset.
    items.extend(
        {"key": k, "label": k, "group": "capability", "default": "", "override": v}
        for k, v in overrides.items()
        if k not in known
    )
    return {
        "prompts": items,
        "max_length": prompts.MAX_PROMPT_CHARS,
        "defaults_available": bool(defaults),
    }


@router.put("/{key}")
@limiter.limit(settings.RATE_LIMIT)
def save_prompt(
    key: str,
    body: PromptBody,
    request: Request,
    _auth: None = Depends(verify_cognito_auth),
    admin_email: str = Depends(verify_prompt_admin),
):
    """Save the override for a key. Blank text resets it to the default."""
    _require_configured()
    _check_key(key)
    if len(body.text) > prompts.MAX_PROMPT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Prompt is too long (max {prompts.MAX_PROMPT_CHARS} characters).",
        )
    try:
        version_id = prompts.put_override(key, body.text)
    except Exception as e:
        logger.error("Failed to save prompt override %s: %s", key, e)
        raise HTTPException(status_code=500, detail="Failed to save prompt.")
    logger.info("Prompt %r %s by an admin (version %s)", key, "reset" if not body.text.strip() else "updated", version_id)
    return {
        "key": key,
        "override": body.text if body.text.strip() else None,
        "version_id": version_id,
    }


@router.get("/{key}/versions")
@limiter.limit(settings.RATE_LIMIT)
def list_prompt_versions(
    key: str,
    request: Request,
    _auth: None = Depends(verify_cognito_auth),
    _admin: str = Depends(verify_prompt_admin),
):
    _require_configured()
    _check_key(key)
    try:
        return {"versions": prompts.list_versions(key)}
    except Exception as e:
        logger.error("Failed to list versions for prompt %s: %s", key, e)
        raise HTTPException(status_code=500, detail="Failed to list versions.")


@router.get("/{key}/versions/{version_id}")
@limiter.limit(settings.RATE_LIMIT)
def get_prompt_version(
    key: str,
    version_id: str,
    request: Request,
    _auth: None = Depends(verify_cognito_auth),
    _admin: str = Depends(verify_prompt_admin),
):
    """Text of one saved version. Empty text means that version was a reset to default."""
    _require_configured()
    _check_key(key)
    if not prompts.VERSION_RE.match(version_id):
        raise HTTPException(status_code=400, detail="Invalid version id.")
    try:
        text = prompts.get_version(key, version_id)
    except Exception as e:
        logger.error("Failed to load version %s of prompt %s: %s", version_id, key, e)
        raise HTTPException(status_code=500, detail="Failed to load version.")
    if text is None:
        raise HTTPException(status_code=404, detail="Version not found.")
    return {"key": key, "version_id": version_id, "text": text}
