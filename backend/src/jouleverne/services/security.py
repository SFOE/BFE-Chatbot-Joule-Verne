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
