import base64
import json
import logging

from fastapi import Request, HTTPException, status
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from ..config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)


async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded",
    )


# ---------------------------------------------------------------------------
# Cognito Group Authorization
# ---------------------------------------------------------------------------

# Parse allowed groups once at startup
_allowed_groups: set[str] = {
    g.strip()
    for g in settings.ALLOWED_COGNITO_GROUPS.split(",")
    if g.strip()
}


def _extract_cognito_groups(request: Request) -> set[str]:
    """Decode cognito:groups from the ALB-injected access token.

    The ALB (authenticate-oidc) has already verified the JWT signature.
    We only decode the payload to read the groups claim.
    """
    access_token = request.headers.get("x-amzn-oidc-accesstoken", "")
    if not access_token:
        return set()

    try:
        payload_b64 = access_token.split(".")[1]
        # Add padding for base64
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return set(payload.get("cognito:groups", []))
    except Exception:
        logger.warning("Failed to decode Cognito access token")
        return set()


def _decode_oidc_data(request: Request) -> dict:
    """Decode the ALB-injected OIDC data token payload.

    The x-amzn-oidc-data header contains a JWT whose payload includes user
    claims (email, sub, etc.). The ALB (authenticate-oidc) has already verified
    the signature, so we only decode the payload. Returns {} on any failure.
    """
    oidc_data = request.headers.get("x-amzn-oidc-data", "")
    if not oidc_data:
        return {}

    try:
        payload_b64 = oidc_data.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        logger.warning("Failed to decode OIDC data token")
        return {}


def extract_user_email(request: Request) -> str | None:
    """Extract the user's email from the ALB-injected OIDC data token.

    Returns the email address or None if unavailable.
    """
    return _decode_oidc_data(request).get("email")


def extract_user_sub(request: Request) -> str | None:
    """Extract the user's stable pseudonymous id (`sub`) from the OIDC token.

    `sub` is the Cognito/EIAM subject identifier: stable per person and free of
    plaintext PII, so it is the key we use to scope stored conversations. Never
    log or persist the e-mail/name alongside it.

    Returns the sub or None if unavailable.
    """
    return _decode_oidc_data(request).get("sub")


def require_user_sub(request: Request) -> str:
    """FastAPI dependency that returns the authenticated user's `sub`.

    Raises 401 when no sub is present. In local dev (no ALB headers) this means
    conversation endpoints are unavailable unless an OIDC data header is faked —
    acceptable because persistence is inherently user-scoped.
    """
    sub = extract_user_sub(request)
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: no user identity in request",
        )
    return sub


async def verify_cognito_auth(request: Request) -> None:
    """FastAPI dependency that checks Cognito group membership.

    If ALLOWED_COGNITO_GROUPS is empty, auth is skipped (open access).
    This allows local development without ALB headers.
    """
    if not _allowed_groups:
        return

    user_groups = _extract_cognito_groups(request)

    if not (user_groups & _allowed_groups):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: insufficient group membership",
        )


# ---------------------------------------------------------------------------
# Per-KB write authorization (upload + delete)
# ---------------------------------------------------------------------------

def _parse_kb_write_allowlist(raw: str) -> dict[str, set[str]]:
    """Parse UPLOAD_ALLOWED_EMAILS_BY_KB into {kb_id: {email, ...}}.

    Format: "kb_id:email1|email2, kb_id2:email3"
    E-mails are lowercased. A KB absent from the map has no write restriction;
    a KB present with an empty set blocks all writes.
    """
    mapping: dict[str, set[str]] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        kb_id, sep, emails_str = entry.partition(":")
        if not sep:
            logger.warning("Ignoring malformed KB write-allowlist entry (no ':'): %r", entry)
            continue
        kb_id = kb_id.strip()
        if not kb_id:
            continue
        emails = {
            e.strip().lower()
            for e in emails_str.split("|")
            if e.strip()
        }
        mapping[kb_id] = emails
    return mapping


# Parse the per-KB write allowlist once at startup.
_kb_write_allowlist: dict[str, set[str]] = _parse_kb_write_allowlist(
    settings.UPLOAD_ALLOWED_EMAILS_BY_KB
)


def verify_kb_write_permission(kb_id: str, request: Request) -> None:
    """Authorize a write (upload/delete) against the per-KB e-mail allowlist.

    - If the KB is not listed in UPLOAD_ALLOWED_EMAILS_BY_KB, writes are open
      (any authenticated user) — preserving the previous behaviour.
    - If the KB is listed, only the allowlisted e-mails may write.

    Raises HTTPException(403) when the current user is not permitted.
    """
    allowed = _kb_write_allowlist.get(kb_id)
    if allowed is None:
        # KB not restricted.
        return

    email = (extract_user_email(request) or "").strip().lower()
    if email not in allowed:
        logger.info("Write denied for %r on KB %s", email or "<unknown>", kb_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: not allowed to modify this knowledge base",
        )
