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

import json
import logging
import re
import time
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key

from ..config import settings
from .clients import dynamodb_resource, s3_client

logger = logging.getLogger(__name__)

# Partition/sort key layout.
#   PK = person_id (the user's sub)
#   SK = "conv#<session_id>"  -> a conversation index item
#   SK = "pref"               -> the user's preference item
_SK_PREF = "pref"
_SK_CONV_PREFIX = "conv#"

# Title generated from the first user message, truncated to this many chars.
_TITLE_MAX_LEN = 80

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


# ---------------------------------------------------------------------------
# Conversation index + transcript
# ---------------------------------------------------------------------------

def _sanitize_key_segment(value: str) -> str:
    """Collapse a value to a single safe S3/DynamoDB key segment.

    Mirrors the agent's prefix sanitisation: strip anything outside
    [A-Za-z0-9._-] so a malformed id can never introduce a path separator.
    """
    return re.sub(r"[^A-Za-z0-9._-]", "_", value or "")


def _transcript_key(sub: str, session_id: str) -> str:
    """S3 key for a conversation's transcript JSON: sessions/<sub>/<id>.json.

    Lives under the same per-user prefix as the agent's Strands transcript
    (sessions/<sub>/<session_id>/...), so one delete prefix removes both.
    """
    prefix = settings.CONVERSATIONS_PREFIX
    if not prefix.endswith("/"):
        prefix += "/"
    return f"{prefix}{_sanitize_key_segment(sub)}/{_sanitize_key_segment(session_id)}.json"


def _derive_title(messages: list[dict]) -> str:
    """Build a title from the first user message, truncated.

    Falls back to a generic label when no user text is present.
    """
    for msg in messages:
        if msg.get("role") == "user":
            text = (msg.get("content") or "").strip()
            if text:
                collapsed = " ".join(text.split())
                if len(collapsed) <= _TITLE_MAX_LEN:
                    return collapsed
                return collapsed[:_TITLE_MAX_LEN].rstrip() + "…"
    return "Chat"


def save_conversation(
    *,
    sub: str,
    session_id: str,
    messages: list[dict],
    mode_config: dict | None = None,
) -> bool:
    """Persist a conversation's transcript (S3) and index entry (DynamoDB).

    Called after each answer when the user has opted in. Upserts the index
    item (preserving the existing title if one was set) and overwrites the
    transcript. ``mode_config`` captures the chat's tool/mode selection so the
    same configuration can be restored on continuation. Returns True when
    stored, False when persistence is disabled.

    Caller MUST pass the authenticated `sub`; the stored data is owned by it.
    """
    if not is_persistence_configured():
        return False
    if not sub or not session_id or not messages:
        return False

    key = _transcript_key(sub, session_id)
    s3_client.put_object(
        Bucket=settings.CONVERSATIONS_BUCKET,
        Key=key,
        Body=json.dumps({"messages": messages}, ensure_ascii=False),
        ContentType="application/json",
    )

    now = datetime.now(timezone.utc).isoformat()

    # Keep a user-set title if one already exists; otherwise derive from the
    # first message. A single UpdateItem does the upsert and the conditional
    # title default via if_not_exists.
    update_expr = (
        "SET title = if_not_exists(title, :t), "
        "updated_at = :u, s3_key = :k, #ttl = :ttl"
    )
    values = {
        ":t": _derive_title(messages),
        ":u": now,
        ":k": key,
        ":ttl": _ttl_from_now(),
    }
    if mode_config is not None:
        update_expr += ", mode_config = :m"
        values[":m"] = mode_config

    _table().update_item(
        Key={"person_id": sub, "sk": f"{_SK_CONV_PREFIX}{session_id}"},
        UpdateExpression=update_expr,
        ExpressionAttributeNames={"#ttl": "ttl"},
        ExpressionAttributeValues=values,
    )
    return True


def list_conversations(sub: str) -> list[dict]:
    """Return the user's conversations, most recently updated first.

    Each item: {session_id, title, updated_at}. Never includes the transcript.
    """
    if not is_persistence_configured() or not sub:
        return []

    resp = _table().query(
        KeyConditionExpression=(
            Key("person_id").eq(sub) & Key("sk").begins_with(_SK_CONV_PREFIX)
        )
    )
    items = resp.get("Items", [])
    convos = [
        {
            "session_id": item["sk"][len(_SK_CONV_PREFIX):],
            "title": item.get("title", "Chat"),
            "updated_at": item.get("updated_at", ""),
        }
        for item in items
    ]
    convos.sort(key=lambda c: c["updated_at"], reverse=True)
    return convos


def load_conversation(sub: str, session_id: str) -> dict | None:
    """Load a conversation's index entry + transcript, or None if not found.

    Ownership is enforced structurally: the item is read under the caller's
    `sub` partition, so another user's chat is simply not found.

    Returns {session_id, title, updated_at, mode_config, messages}.
    """
    if not is_persistence_configured() or not sub or not session_id:
        return None

    resp = _table().get_item(
        Key={"person_id": sub, "sk": f"{_SK_CONV_PREFIX}{session_id}"}
    )
    item = resp.get("Item")
    if not item:
        return None

    messages: list[dict] = []
    key = item.get("s3_key")
    if key:
        try:
            obj = s3_client.get_object(Bucket=settings.CONVERSATIONS_BUCKET, Key=key)
            payload = json.loads(obj["Body"].read())
            messages = payload.get("messages", [])
        except Exception:
            logger.exception("Failed to read transcript for a conversation")

    return {
        "session_id": session_id,
        "title": item.get("title", "Chat"),
        "updated_at": item.get("updated_at", ""),
        "mode_config": item.get("mode_config"),
        "messages": messages,
    }


def rename_conversation(sub: str, session_id: str, title: str) -> bool:
    """Rename a conversation. Returns True when the item exists and was updated.

    Only touches an item in the caller's partition, so a user can never rename
    another user's chat.
    """
    if not is_persistence_configured() or not sub or not session_id:
        return False

    clean = " ".join((title or "").split())[:_TITLE_MAX_LEN].strip()
    if not clean:
        return False

    try:
        _table().update_item(
            Key={"person_id": sub, "sk": f"{_SK_CONV_PREFIX}{session_id}"},
            UpdateExpression="SET title = :t",
            ConditionExpression="attribute_exists(sk)",
            ExpressionAttributeValues={":t": clean},
        )
    except _table().meta.client.exceptions.ConditionalCheckFailedException:
        return False
    return True
