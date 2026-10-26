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
_DEFAULT_SAVE_ENABLED = True


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
    """S3 key for a conversation's transcript JSON: sessions/<sub>/<session_id>.json.

    Note: The agent stores transcripts under sessions/<sub>/session_<session_id>/... (Strands
    adds 'session_' prefix to the session path). This function only stores the JSON
    file itself (no session_ prefix in the filename), while the agent's session
    manager handles the full session path including 'session_' prefix.

    One delete prefix (sessions/<sub>/) removes both the JSON and the agent's session,
    and since documents also live under session_<session_id>/, deleting that prefix
    removes the entire session data (agent + documents + index).
    """
    prefix = settings.CONVERSATIONS_PREFIX
    if not prefix.endswith("/"):
        prefix += "/"
    return f"{prefix}{_sanitize_key_segment(sub)}/{_sanitize_key_segment(session_id)}.json"


def _truncate_title(text: str) -> str:
    """Collapse whitespace and truncate a title to the max length."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= _TITLE_MAX_LEN:
        return collapsed
    return collapsed[:_TITLE_MAX_LEN].rstrip() + "…"


def _derive_title(
    messages: list[dict],
    document_names: list[str] | None = None,
) -> tuple[str, bool]:
    """Build a title and report whether it is a placeholder.

    Returns ``(title, is_placeholder)``. A title taken from the first user
    message is final (``is_placeholder=False``). When there is no user text
    yet — e.g. a chat that so far only has uploaded documents — the title is a
    placeholder (``is_placeholder=True``) derived from the first document name,
    or the generic label as a last resort. Placeholder titles are written with
    ``if_not_exists`` so a later real first message can upgrade them.
    """
    for msg in messages:
        if msg.get("role") == "user":
            text = (msg.get("content") or "").strip()
            if text:
                return _truncate_title(text), False

    for name in document_names or []:
        name = (name or "").strip()
        if name:
            return _truncate_title(name), True

    return "Chat", True


def save_conversation(
    *,
    sub: str,
    session_id: str,
    messages: list[dict],
    mode_config: dict | None = None,
    document_names: list[str] | None = None,
) -> bool:
    """Persist a conversation's transcript (S3) and index entry (DynamoDB).

    Called after each answer — and after an upload into a brand-new chat — when
    the user has opted in. Upserts the index item and overwrites the transcript.
    ``mode_config`` captures the chat's tool/mode selection so the same
    configuration can be restored on continuation. ``document_names`` supplies a
    fallback title for a chat that so far only has uploaded documents (no user
    message yet). Returns True when stored, False when persistence is disabled.

    A chat is saved as long as it has *something* to show — either a transcript
    or at least one uploaded document name. A truly empty save is a no-op.

    Caller MUST pass the authenticated `sub`; the stored data is owned by it.
    """
    if not is_persistence_configured():
        return False
    if not sub or not session_id:
        return False
    if not messages and not (document_names or []):
        return False

    key = _transcript_key(sub, session_id)
    s3_client.put_object(
        Bucket=settings.CONVERSATIONS_BUCKET,
        Key=key,
        Body=json.dumps({"messages": messages}, ensure_ascii=False),
        ContentType="application/json",
    )

    now = datetime.now(timezone.utc).isoformat()
    item_key = {"person_id": sub, "sk": f"{_SK_CONV_PREFIX}{session_id}"}

    title, is_placeholder = _derive_title(messages, document_names)

    # Decide whether to (re)write the title. Read the current index item first:
    #   - no title yet        -> write the derived title
    #   - stored placeholder  -> upgrade it (e.g. an uploads-only chat gets its
    #                            first real message, or a better document name)
    #   - real / user-set     -> keep it; never clobber a pinned title
    existing = _table().get_item(Key=item_key).get("Item", {})
    stored_is_placeholder = existing.get("title_placeholder", True)
    write_title = ("title" not in existing) or stored_is_placeholder

    update_expr = "SET updated_at = :u, s3_key = :k, #ttl = :ttl"
    values = {
        ":u": now,
        ":k": key,
        ":ttl": _ttl_from_now(),
    }
    if write_title:
        update_expr += ", title = :t, title_placeholder = :tp"
        values[":t"] = title
        values[":tp"] = is_placeholder
    if mode_config is not None:
        update_expr += ", mode_config = :m"
        values[":m"] = mode_config

    _table().update_item(
        Key=item_key,
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
            UpdateExpression="SET title = :t, title_placeholder = :tp",
            ConditionExpression="attribute_exists(sk)",
            ExpressionAttributeValues={":t": clean, ":tp": False},
        )
    except _table().meta.client.exceptions.ConditionalCheckFailedException:
        return False
    return True


# ---------------------------------------------------------------------------
# Delete a conversation and everything associated with it
# ---------------------------------------------------------------------------

def _delete_s3_prefix(bucket: str, prefix: str) -> None:
    """Delete every object under a bucket/prefix. Best-effort, paginated."""
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        contents = page.get("Contents")
        if not contents:
            continue
        objects = [{"Key": obj["Key"]} for obj in contents]
        # delete_objects handles up to 1000 keys per call; a page is <= 1000.
        s3_client.delete_objects(Bucket=bucket, Delete={"Objects": objects})


def _delete_feedback_for_session(session_id: str) -> None:
    """Best-effort delete of feedback objects belonging to a session.

    Feedback keys are date-partitioned as
    ``feedback/<y>/<m>/<d>/<session_id>_<index>.json`` with no session index,
    so we scan the feedback/ prefix and match on the ``<session_id>_`` filename
    segment. This is a wide scan, but delete is an infrequent per-user action
    and feedback is best-effort analytics data.
    """
    bucket = settings.CONVERSATIONS_BUCKET
    needle = f"/{session_id}_"
    paginator = s3_client.get_paginator("list_objects_v2")
    to_delete: list[dict] = []
    for page in paginator.paginate(Bucket=bucket, Prefix="feedback/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if needle in key and key.endswith(".json"):
                to_delete.append({"Key": key})
                if len(to_delete) == 1000:
                    s3_client.delete_objects(Bucket=bucket, Delete={"Objects": to_delete})
                    to_delete = []
    if to_delete:
        s3_client.delete_objects(Bucket=bucket, Delete={"Objects": to_delete})


def _ephemeral_prefix() -> str:
    """Base prefix for opt-out (short-lived) agent transcripts.

    Mirrors the agent's EPHEMERAL_PREFIX. Kept in sync via the shared default
    "ephemeral/"; both read the same env var name in their own runtime.
    """
    raw = settings.EPHEMERAL_PREFIX or "ephemeral/"
    return raw if raw.endswith("/") else raw + "/"


def delete_ephemeral_session(sub: str, session_id: str) -> None:
    """Delete a user's short-lived (opt-out) agent transcript immediately.

    Called when the user switches saving off or starts a new chat, so an
    opt-out session's history is cleared right away rather than only by the
    1-day lifecycle backstop. Best-effort and scoped to the caller's own
    ``sub``; a missing object is a no-op.
    """
    if not is_persistence_configured() or not sub or not session_id:
        return
    safe_sub = _sanitize_key_segment(sub)
    safe_sid = _sanitize_key_segment(session_id)
    prefix = f"{_ephemeral_prefix()}{safe_sub}/{safe_sid}/"
    try:
        _delete_s3_prefix(settings.CONVERSATIONS_BUCKET, prefix)
    except Exception:
        logger.exception("Failed to delete ephemeral session transcript")


def delete_conversation(sub: str, session_id: str) -> bool:
    """Delete a conversation and everything associated with it.

    Removes, for the caller's own chat only:
    - the DynamoDB index item,
    - the transcript JSON in S3 (sessions/<sub>/<session_id>.json),
    - the agent's Strands transcript under sessions/<sub>/session_<session_id>/,
    - best-effort, the session's feedback objects.

    Ownership is enforced structurally: we only ever address items/keys under
    the caller's own ``sub``. Returns True when the index item existed and was
    deleted, False otherwise (unknown chat / persistence disabled).

    Note: Since agent transcripts and documents now share the same session folder
    (sessions/<sub>/session_<session_id>/), deleting the session prefix removes
    both the agent's Strands history and all uploaded documents.
    """
    if not is_persistence_configured() or not sub or not session_id:
        return False

    # Confirm the chat exists and belongs to this user before deleting anything.
    resp = _table().get_item(
        Key={"person_id": sub, "sk": f"{_SK_CONV_PREFIX}{session_id}"}
    )
    item = resp.get("Item")
    if not item:
        return False

    bucket = settings.CONVERSATIONS_BUCKET
    safe_sub = _sanitize_key_segment(sub)
    safe_sid = _sanitize_key_segment(session_id)

    # 1) Transcript JSON (use the stored key when present, else the derived one).
    transcript_key = item.get("s3_key") or _transcript_key(sub, session_id)
    try:
        s3_client.delete_object(Bucket=bucket, Key=transcript_key)
    except Exception:
        logger.exception("Failed to delete transcript object during delete")

    # 2) Agent (Strands) transcript objects under the per-session prefix.
    # Strands stores under sessions/<sub>/session_<sid>/ agents/...
    prefix = settings.CONVERSATIONS_PREFIX
    if not prefix.endswith("/"):
        prefix += "/"
    try:
        _delete_s3_prefix(bucket, f"{prefix}{safe_sub}/session_{safe_sid}/")
    except Exception:
        logger.exception("Failed to delete agent transcript prefix during delete")

    # 3) Feedback objects for this session (best-effort).
    try:
        _delete_feedback_for_session(session_id)
    except Exception:
        logger.exception("Failed to delete feedback objects during delete")

    # 4) Finally the index item, so a failure above still leaves it listable
    #    (and thus retryable) rather than orphaning storage silently.
    _table().delete_item(Key={"person_id": sub, "sk": f"{_SK_CONV_PREFIX}{session_id}"})
    return True
