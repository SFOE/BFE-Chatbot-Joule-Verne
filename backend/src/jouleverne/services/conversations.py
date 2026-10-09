"""Persistent per-user chat history.

Two storage layers, both keyed by the user's pseudonymous ``sub``:

- DynamoDB (``CONVERSATIONS_TABLE``): a lightweight index. One item per
  conversation holding title / updated_at / mode_config / s3_key, plus one
  item per user holding the "save chats" opt-in preference. Fast "list my
  chats" queries and a TTL backstop live here.
- S3 (``CONVERSATIONS_BUCKET`` under ``CONVERSATIONS_PREFIX``): the heavy chat
  transcript (the frontend ``messages`` array) as one JSON object per chat.

Everything is scoped to ``sub``. Callers MUST pass the ``sub`` taken from the
verified OIDC token; the service never trusts a client-supplied owner id.

When the table/bucket are unconfigured the service degrades to "persistence
disabled" so the app keeps working with ephemeral chats only.
"""

import logging
import time
from datetime import datetime, timezone

from ..config import settings
from .clients import dynamodb_resource

logger = logging.getLogger(__name__)

# Partition/sort key layout.
#   PK = person_id (the user's sub)
#   SK = "conv#<session_id>"  -> a conversation index item
#   SK = "pref"               -> the user's preference item
_SK_PREF = "pref"
_SK_CONV_PREFIX = "conv#"

# One year, in seconds, for the DynamoDB TTL backstop.
_ONE_YEAR_SECONDS = 365 * 24 * 60 * 60

# Default when a user has never toggled the setting. Opt-in: we do NOT persist
# chats until the user explicitly turns it on.
_DEFAULT_SAVE_ENABLED = False


def is_persistence_configured() -> bool:
    """True when both storage layers are configured."""
    return bool(settings.CONVERSATIONS_TABLE and settings.CONVERSATIONS_BUCKET)


def _table():
    return dynamodb_resource.Table(settings.CONVERSATIONS_TABLE)


def _ttl_from_now() -> int:
    return int(time.time()) + _ONE_YEAR_SECONDS


# ---------------------------------------------------------------------------
# User preference: "save my chats" opt-in
# ---------------------------------------------------------------------------

def get_save_enabled(sub: str) -> bool:
    """Return whether the user has opted in to saving chats.

    Defaults to False (opt-in) when unset or when persistence is unconfigured.
    """
    if not is_persistence_configured():
        return False

    try:
        resp = _table().get_item(Key={"person_id": sub, "sk": _SK_PREF})
    except Exception:
        logger.exception("Failed to read save preference")
        return _DEFAULT_SAVE_ENABLED

    item = resp.get("Item")
    if not item:
        return _DEFAULT_SAVE_ENABLED
    return bool(item.get("save_enabled", _DEFAULT_SAVE_ENABLED))


def set_save_enabled(sub: str, enabled: bool) -> bool:
    """Persist the user's save opt-in flag. Returns the stored value.

    Turning the flag off never deletes existing conversations; it only stops
    new ones from being written (existing chats stay listable and deletable).
    """
    if not is_persistence_configured():
        logger.warning("Conversation persistence not configured; preference not stored.")
        return False

    _table().put_item(
        Item={
            "person_id": sub,
            "sk": _SK_PREF,
            "save_enabled": bool(enabled),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return bool(enabled)
