"""Editable agent system prompts — stored in S3, versioned, forwarded to the agent.

The agent's prompt text lives in code (the "defaults"). An admin can override any
part of it from the app. Overrides apply to ALL users and take effect on the
next chat message, without a deploy.

Storage (conversations bucket, prefix ``prompt-overrides/``):

- ``current.json``                   {key: text} of active overrides only
- ``versions/<key>/<version>.txt``   every saved text (empty text = reset to default)

Every save writes an immutable version object first, then updates
``current.json``. Restoring an old version is just loading it and saving again,
so history is never rewritten.
"""

import json
import logging
import re
import threading
import time
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from ..config import settings
from .clients import agentcore_client, s3_client

logger = logging.getLogger(__name__)

MAX_PROMPT_CHARS = 60000
MAX_VERSIONS_LISTED = 50

_PREFIX = "prompt-overrides/"
_CURRENT_KEY = f"{_PREFIX}current.json"

KEY_RE = re.compile(r"^[a-z0-9_]{1,64}$")
VERSION_RE = re.compile(r"^\d{8}T\d{12}Z$")

# Chat requests read the overrides on every message; keep S3 traffic low. Other
# ECS tasks may see a change up to this many seconds late.
_OVERRIDES_TTL_SECONDS = 30
_DEFAULTS_TTL_SECONDS = 300

_lock = threading.Lock()
_overrides_cache: tuple[float, dict[str, str]] | None = None
_defaults_cache: tuple[float, list[dict]] | None = None


def is_configured() -> bool:
    return bool(settings.CONVERSATIONS_BUCKET)


def _version_prefix(key: str) -> str:
    return f"{_PREFIX}versions/{key}/"


def _read_current() -> dict[str, str]:
    """Read current.json. Raises on S3 errors other than 'not found'."""
    try:
        obj = s3_client.get_object(Bucket=settings.CONVERSATIONS_BUCKET, Key=_CURRENT_KEY)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return {}
        raise
    data = json.loads(obj["Body"].read().decode("utf-8"))
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and v.strip()}


def get_overrides() -> dict[str, str]:
    """Active overrides ({} when none or on error). Never breaks a chat."""
    global _overrides_cache
    if not is_configured():
        return {}
    now = time.monotonic()
    with _lock:
        cached = _overrides_cache
    if cached and now - cached[0] < _OVERRIDES_TTL_SECONDS:
        return cached[1]
    try:
        current = _read_current()
    except Exception as e:
        logger.warning("Failed to load prompt overrides: %s", e)
        return cached[1] if cached else {}
    with _lock:
        _overrides_cache = (now, current)
    return current


def _set_cache(current: dict[str, str]) -> None:
    global _overrides_cache
    with _lock:
        _overrides_cache = (time.monotonic(), current)


def put_override(key: str, text: str) -> str | None:
    """Save ``text`` as the override for ``key`` (blank = back to default).

    Returns the new version id, or None when nothing changed.
    """
    current = _read_current()  # strict: never overwrite on a transient read error
    text = text if text.strip() else ""
    if current.get(key, "") == text:
        return None

    version_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    s3_client.put_object(
        Bucket=settings.CONVERSATIONS_BUCKET,
        Key=f"{_version_prefix(key)}{version_id}.txt",
        Body=text.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )

    updated = dict(current)
    if text:
        updated[key] = text
    else:
        updated.pop(key, None)
    s3_client.put_object(
        Bucket=settings.CONVERSATIONS_BUCKET,
        Key=_CURRENT_KEY,
        Body=json.dumps(updated, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )
    _set_cache(updated)
    return version_id


def list_versions(key: str) -> list[dict]:
    """Saved versions of a key, newest first (id, timestamp, size in bytes)."""
    prefix = _version_prefix(key)
    versions: list[dict] = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.CONVERSATIONS_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            name = obj["Key"][len(prefix):]
            if not name.endswith(".txt"):
                continue
            version_id = name[: -len(".txt")]
            if not VERSION_RE.match(version_id):
                continue
            versions.append(
                {
                    "version_id": version_id,
                    "saved_at": obj["LastModified"].isoformat(),
                    "size": obj["Size"],
                }
            )
    versions.sort(key=lambda v: v["version_id"], reverse=True)
    return versions[:MAX_VERSIONS_LISTED]


def get_version(key: str, version_id: str) -> str | None:
    """Text of one saved version ("" = it was a reset), or None if not found."""
    try:
        obj = s3_client.get_object(
            Bucket=settings.CONVERSATIONS_BUCKET,
            Key=f"{_version_prefix(key)}{version_id}.txt",
        )
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return None
        raise
    return obj["Body"].read().decode("utf-8")


# ---------------------------------------------------------------------------
# Defaults (owned by the agent, fetched through the runtime)
# ---------------------------------------------------------------------------

def _iter_frames(raw: str):
    """Yield the JSON values of an AgentCore stream body ("data: <json>" frames)."""
    from .agent import _extract_json_value

    buffer = raw
    while buffer.strip():
        stripped = buffer.lstrip()
        if stripped.startswith("data:"):
            stripped = stripped[5:]
        value, buffer = _extract_json_value(stripped)
        if value is None:
            return
        if isinstance(value, str):
            try:
                inner = json.loads(value)
                if isinstance(inner, (dict, list)):
                    value = inner
            except ValueError:
                pass
        yield value


def get_defaults() -> list[dict]:
    """Default prompt parts from the agent: [{key, label, group, default}, ...].

    Returns [] when the agent cannot be reached or does not support the action
    yet (older deployment). Cached for a few minutes.
    """
    global _defaults_cache
    now = time.monotonic()
    with _lock:
        cached = _defaults_cache
    if cached and now - cached[0] < _DEFAULTS_TTL_SECONDS:
        return cached[1]
    try:
        response = agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=settings.AGENTCORE_RUNTIME_ARN,
            payload=json.dumps({"action": "get_prompt_defaults"}).encode("utf-8"),
        )
        raw = response["response"].read().decode("utf-8", errors="ignore")
        for frame in _iter_frames(raw):
            if isinstance(frame, dict) and frame.get("type") == "prompt_defaults":
                parts = [
                    p
                    for p in frame.get("prompts", [])
                    if isinstance(p, dict) and isinstance(p.get("key"), str)
                ]
                with _lock:
                    _defaults_cache = (now, parts)
                return parts
        logger.warning("Agent did not return prompt defaults (old agent version?).")
    except Exception as e:
        logger.warning("Failed to fetch prompt defaults from agent: %s", e)
    return cached[1] if cached else []
