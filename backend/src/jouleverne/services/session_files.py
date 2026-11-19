"""Per-session storage of uploaded original files.

Every file a user uploads in a chat — regardless of size or type — is stored
here as its original bytes plus a small ``meta.json`` describing how it is used
(inline context, RAG index, or Code Interpreter). This gives three things:

- a complete record of what was uploaded (A),
- the raw file for Code Interpreter to load on demand instead of shipping it in
  every chat payload (B / reference approach),
- restoration of the upload list when a saved chat is continued.

Layout (under the caller-provided base ``prefix`` — session or ephemeral):

    <prefix>uploads/<file_id>/original/<name>   # raw bytes
    <prefix>uploads/<file_id>/meta.json         # {file_id, name, media_type,
                                                 #  routing, doc_id?}

``routing`` is one of: "inline" (small text/table in context), "index" (large
text, searchable via docindex), "ci" (table for Code Interpreter). ``doc_id``
links an "index" file to its docindex entry.

Prefix-neutral like doc_index: callers pass the session/ephemeral prefix, and a
future per-user library can reuse this by passing a different base.
"""

import json
import logging
import re
import uuid

from ..config import settings
from .clients import s3_client

logger = logging.getLogger(__name__)

_UPLOADS_SUBPREFIX = "uploads/"
_ORIGINAL_SEGMENT = "original/"
_META_NAME = "meta.json"


def _normalize_prefix(prefix: str) -> str:
    return prefix if prefix.endswith("/") else prefix + "/"


def _sanitize(value: str) -> str:
    """Collapse a value to a single safe key segment (no path separators)."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", value or "")


def _uploads_prefix(prefix: str) -> str:
    return f"{_normalize_prefix(prefix)}{_UPLOADS_SUBPREFIX}"


def _file_dir(prefix: str, file_id: str) -> str:
    return f"{_uploads_prefix(prefix)}{_sanitize(file_id)}/"


def _original_key(prefix: str, file_id: str, filename: str) -> str:
    return f"{_file_dir(prefix, file_id)}{_ORIGINAL_SEGMENT}{_sanitize(filename)}"


def _meta_key(prefix: str, file_id: str) -> str:
    return f"{_file_dir(prefix, file_id)}{_META_NAME}"


def store_file(
    *,
    prefix: str,
    file_bytes: bytes,
    filename: str,
    routing: str,
    media_type: str = "",
    doc_id: str | None = None,
    bucket: str | None = None,
) -> dict | None:
    """Store one original file + its meta. Returns the meta dict, or None.

    ``routing`` in {"inline", "index", "ci"}; ``doc_id`` links an indexed file to
    its docindex entry. Returns None when no bucket is configured.
    """
    target_bucket = bucket or settings.CONVERSATIONS_BUCKET
    if not target_bucket:
        return None

    file_id = uuid.uuid4().hex
    original_key = _original_key(prefix, file_id, filename)
    s3_client.put_object(Bucket=target_bucket, Key=original_key, Body=file_bytes)

    meta = {
        "file_id": file_id,
        "name": filename,
        "media_type": media_type,
        "routing": routing,
        "doc_id": doc_id,
        "original_key": original_key,
    }
    s3_client.put_object(
        Bucket=target_bucket,
        Key=_meta_key(prefix, file_id),
        Body=json.dumps(meta, ensure_ascii=False),
        ContentType="application/json",
    )
    return meta


def list_files(prefix: str, bucket: str | None = None) -> list[dict]:
    """List the session's stored files (one meta dict each)."""
    target_bucket = bucket or settings.CONVERSATIONS_BUCKET
    if not target_bucket:
        return []
    uploads_prefix = _uploads_prefix(prefix)
    metas: list[dict] = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=target_bucket, Prefix=uploads_prefix):
        for obj in page.get("Contents", []):
            if not obj["Key"].endswith(f"/{_META_NAME}"):
                continue
            try:
                data = s3_client.get_object(Bucket=target_bucket, Key=obj["Key"])
                metas.append(json.loads(data["Body"].read()))
            except Exception:
                logger.exception("Failed to read file meta %s", obj["Key"])
    return metas


def get_file_bytes(prefix: str, file_id: str, bucket: str | None = None) -> tuple[bytes, dict] | None:
    """Return (bytes, meta) for a stored file, or None if not found.

    Scoped to the given prefix, so a caller can only read files under a session
    it owns.
    """
    target_bucket = bucket or settings.CONVERSATIONS_BUCKET
    if not target_bucket or not file_id:
        return None
    try:
        meta_obj = s3_client.get_object(Bucket=target_bucket, Key=_meta_key(prefix, file_id))
        meta = json.loads(meta_obj["Body"].read())
    except Exception:
        return None
    try:
        orig = s3_client.get_object(Bucket=target_bucket, Key=meta["original_key"])
        return orig["Body"].read(), meta
    except Exception:
        logger.exception("Failed to read original for file_id %s", file_id)
        return None


def delete_file(prefix: str, file_id: str, bucket: str | None = None) -> bool:
    """Delete one stored file (original + meta). Returns True if it existed."""
    target_bucket = bucket or settings.CONVERSATIONS_BUCKET
    if not target_bucket or not file_id:
        return False
    file_dir = _file_dir(prefix, file_id)
    found = False
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=target_bucket, Prefix=file_dir):
        objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if objects:
            found = True
            s3_client.delete_objects(Bucket=target_bucket, Delete={"Objects": objects})
    return found


def count_files(prefix: str, bucket: str | None = None) -> int:
    """Count stored files under a prefix (one per meta.json)."""
    target_bucket = bucket or settings.CONVERSATIONS_BUCKET
    if not target_bucket:
        return 0
    total = 0
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=target_bucket, Prefix=_uploads_prefix(prefix)):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(f"/{_META_NAME}"):
                total += 1
    return total
