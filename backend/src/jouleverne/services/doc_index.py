"""Lightweight per-session RAG index for uploaded chat documents.

For large uploaded documents we build a small vector index instead of pushing
the whole text into every turn: extract text, chunk it, embed each chunk with
the same multilingual Bedrock model the knowledge bases use, and store the
vectors + text as one JSON object per document in S3. At query time we embed the
question and return the most similar chunks (cosine) across the session's
documents.

Design notes:
- **Prefix-neutral.** build/search/delete take an explicit S3 key prefix. Today
  callers pass the session prefix (``sessions/<sub>/session_<session_id>/``) or the
  ephemeral one; a future per-user document library can reuse this unchanged by
  passing ``docs/<sub>/``.
- **No managed KB, no vector DB.** A handful of documents per session means a
  few hundred vectors — cosine in pure Python is more than fast enough and adds
  no infrastructure.
- Index objects live under ``<prefix>docindex/<doc_id>.json`` so the existing
  session delete (which clears the whole session prefix) removes them for free.

This module is self-contained and NOT yet wired into the upload flow; that
happens in a later step.
"""

import json
import logging
import math
import re
import uuid

from .clients import bedrock_runtime_client, s3_client
from .documents import extract_text
from ..config import settings

logger = logging.getLogger(__name__)

# Index objects live under this sub-prefix of whatever base prefix is passed in.
_DOCINDEX_SUBPREFIX = "docindex/"

# Rough chars-per-token used to turn the token-based chunk config into character
# windows (we chunk on characters to avoid a tokenizer dependency). ~4 is a safe
# average for DE/FR/IT/EN.
_CHARS_PER_TOKEN = 4


# ---------------------------------------------------------------------------
# Chunking (size-based, with overlap)
# ---------------------------------------------------------------------------

def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping, size-based chunks.

    Window and overlap come from the token-based config, converted to characters
    via a fixed ratio. Overlap preserves context across cut points so a sentence
    split by a blind size-based boundary still appears whole in a neighbour.
    """
    window = max(1, settings.DOC_CHUNK_TOKENS * _CHARS_PER_TOKEN)
    overlap = max(0, settings.DOC_CHUNK_OVERLAP_TOKENS * _CHARS_PER_TOKEN)
    stride = max(1, window - overlap)

    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        chunk = text[start:start + window].strip()
        if chunk:
            chunks.append(chunk)
        if start + window >= n:
            break
        start += stride
    return chunks


# ---------------------------------------------------------------------------
# Embeddings (Bedrock Titan v2)
# ---------------------------------------------------------------------------

def embed_text(text: str) -> list[float]:
    """Embed a single string with the configured Bedrock embedding model.

    Titan Text Embeddings v2 embeds one input per invoke_model call and returns
    a float vector of EMBEDDING_DIMENSIONS length.
    """
    body = json.dumps({
        "inputText": text,
        "dimensions": settings.EMBEDDING_DIMENSIONS,
        "normalize": True,
    })
    resp = bedrock_runtime_client.invoke_model(
        modelId=settings.EMBEDDING_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    payload = json.loads(resp["body"].read())
    return payload["embedding"]


def embed_many(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings, one invoke per text (Titan has no batch API)."""
    return [embed_text(t) for t in texts]


# ---------------------------------------------------------------------------
# Cosine similarity (pure Python)
# ---------------------------------------------------------------------------

def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors. 0.0 for a zero vector."""
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

def _normalize_prefix(prefix: str) -> str:
    return prefix if prefix.endswith("/") else prefix + "/"


def session_prefix(sub: str, session_id: str, save_history: bool) -> str:
    """Build the per-session base prefix for a user's document index.

    Mirrors the agent's transcript prefix so the index lives beside the chat
    history: persistent chats under CONVERSATIONS_PREFIX, opt-out chats under
    the short-lived EPHEMERAL_PREFIX. Both segments are sanitised so a malformed
    id can never introduce a path separator.

    The agent stores transcripts under session_<id>/ (Strands requirement), so
    we match that by prefixing the session_id with 'session_' here. This ensures
    both agent and documents share the same session folder for easier management.

    Example output: sessions/<sub>/session_<session_id>/
    """
    base = settings.CONVERSATIONS_PREFIX if save_history else settings.EPHEMERAL_PREFIX
    base = _normalize_prefix(base or ("sessions/" if save_history else "ephemeral/"))
    safe_sub = re.sub(r"[^A-Za-z0-9._-]", "_", sub or "")
    safe_sid = re.sub(r"[^A-Za-z0-9._-]", "_", session_id or "")
    return f"{base}{safe_sub}/session_{safe_sid}/"


def _index_key(prefix: str, doc_id: str) -> str:
    return f"{_normalize_prefix(prefix)}{_DOCINDEX_SUBPREFIX}{doc_id}.json"


def _index_list_prefix(prefix: str) -> str:
    return f"{_normalize_prefix(prefix)}{_DOCINDEX_SUBPREFIX}"


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_index(
    *,
    prefix: str,
    file_bytes: bytes,
    filename: str,
    bucket: str | None = None,
) -> dict | None:
    """Extract, chunk, embed and store an index for one document.

    ``prefix`` is the base S3 key prefix the index is stored under (session or,
    later, per-user). Returns a small summary {doc_id, name, chunk_count} or
    None when there was nothing to index (empty/low-quality text).

    Text extraction (and its quality/sensitivity checks) reuses the existing
    document service. Raises ValueError from extract_text for unsupported or
    low-quality files — the caller decides how to surface that.
    """
    target_bucket = bucket or settings.CONVERSATIONS_BUCKET
    if not target_bucket:
        logger.warning("No bucket configured for document index; skipping build.")
        return None

    text, _pages = extract_text(file_bytes, filename)
    chunks = _chunk_text(text)
    if not chunks:
        return None

    vectors = embed_many(chunks)
    doc_id = uuid.uuid4().hex

    # NOTE: the original file is stored once by the upload flow via
    # session_files.store_file (under uploads/<file_id>/original/). We no longer
    # keep a second copy under docindex/<doc_id>/original/ — the index only
    # needs the chunks + vectors.
    index = {
        "doc_id": doc_id,
        "name": filename,
        "model": settings.EMBEDDING_MODEL_ID,
        "dim": settings.EMBEDDING_DIMENSIONS,
        "chunks": [
            {"i": i, "text": chunk, "vector": vec}
            for i, (chunk, vec) in enumerate(zip(chunks, vectors))
        ],
    }

    s3_client.put_object(
        Bucket=target_bucket,
        Key=_index_key(prefix, doc_id),
        Body=json.dumps(index, ensure_ascii=False),
        ContentType="application/json",
    )
    return {
        "doc_id": doc_id,
        "name": filename,
        "chunk_count": len(chunks),
    }


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _is_index_object(key: str, list_prefix: str) -> bool:
    """True only for an index JSON directly under docindex/ (not an original).

    Index files are ``<list_prefix><doc_id>.json``. Original files live deeper,
    under ``<list_prefix><doc_id>/original/...`` and must be skipped here.
    """
    if not key.endswith(".json"):
        return False
    remainder = key[len(list_prefix):]
    return "/" not in remainder


def _load_indexes(bucket: str, prefix: str) -> list[dict]:
    """Load all index objects stored under a prefix. Best-effort."""
    indexes: list[dict] = []
    list_prefix = _index_list_prefix(prefix)
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=list_prefix):
        for obj in page.get("Contents", []):
            if not _is_index_object(obj["Key"], list_prefix):
                continue
            try:
                data = s3_client.get_object(Bucket=bucket, Key=obj["Key"])
                indexes.append(json.loads(data["Body"].read()))
            except Exception:
                logger.exception("Failed to load a document index object")
    return indexes


def search(
    *,
    prefix: str,
    query: str,
    top_n: int | None = None,
    bucket: str | None = None,
    with_neighbors: bool = True,
) -> list[dict]:
    """Return the most similar chunks to ``query`` across all indexed documents.

    Each hit: {doc_id, name, chunk_index, score, text}. When ``with_neighbors``
    is set, the adjacent chunks of the same document are merged into ``text`` so
    a size-based cut does not strand half a thought.
    """
    target_bucket = bucket or settings.CONVERSATIONS_BUCKET
    if not target_bucket or not query.strip():
        return []

    indexes = _load_indexes(target_bucket, prefix)
    if not indexes:
        return []

    q_vec = embed_text(query)
    n = top_n or settings.DOC_SEARCH_TOP_N

    scored: list[dict] = []
    for idx in indexes:
        chunks = idx.get("chunks", [])
        for chunk in chunks:
            score = _cosine(q_vec, chunk["vector"])
            scored.append({
                "doc_id": idx.get("doc_id"),
                "name": idx.get("name"),
                "chunk_index": chunk["i"],
                "score": score,
                "_chunks": chunks,  # transient, for neighbour lookup
            })

    scored.sort(key=lambda h: h["score"], reverse=True)
    top = scored[:n]

    results: list[dict] = []
    for hit in top:
        chunks = hit.pop("_chunks")
        text = _chunk_with_neighbors(chunks, hit["chunk_index"]) if with_neighbors \
            else _chunk_at(chunks, hit["chunk_index"])
        results.append({**hit, "text": text})
    return results


def _chunk_at(chunks: list[dict], index: int) -> str:
    for c in chunks:
        if c["i"] == index:
            return c["text"]
    return ""


def _chunk_with_neighbors(chunks: list[dict], index: int) -> str:
    """Join the chunk at ``index`` with its immediate neighbours (by order)."""
    by_i = {c["i"]: c["text"] for c in chunks}
    parts = [by_i[i] for i in (index - 1, index, index + 1) if i in by_i]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Delete / list
# ---------------------------------------------------------------------------

def list_documents(prefix: str, bucket: str | None = None) -> list[dict]:
    """List indexed documents under a prefix: [{doc_id, name, chunk_count}]."""
    target_bucket = bucket or settings.CONVERSATIONS_BUCKET
    if not target_bucket:
        return []
    docs = []
    for idx in _load_indexes(target_bucket, prefix):
        docs.append({
            "doc_id": idx.get("doc_id"),
            "name": idx.get("name"),
            "chunk_count": len(idx.get("chunks", [])),
        })
    return docs


def count_documents(prefix: str, bucket: str | None = None) -> int:
    """Count index objects under a prefix (for the per-session document limit)."""
    target_bucket = bucket or settings.CONVERSATIONS_BUCKET
    if not target_bucket:
        return 0
    total = 0
    list_prefix = _index_list_prefix(prefix)
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=target_bucket, Prefix=list_prefix):
        for obj in page.get("Contents", []):
            if _is_index_object(obj["Key"], list_prefix):
                total += 1
    return total


def delete_document(prefix: str, doc_id: str, bucket: str | None = None) -> bool:
    """Delete a single indexed document: its index JSON and its original file.

    Removes ``<prefix>docindex/<doc_id>.json`` and everything under
    ``<prefix>docindex/<doc_id>/`` (the stored original). Returns True if the
    index object existed and was deleted, False otherwise. ``doc_id`` is
    sanitised so it cannot escape the prefix.
    """
    target_bucket = bucket or settings.CONVERSATIONS_BUCKET
    if not target_bucket or not doc_id:
        return False

    safe_doc_id = re.sub(r"[^A-Za-z0-9._-]", "_", doc_id)
    index_key = _index_key(prefix, safe_doc_id)

    # Confirm the index exists before reporting success (so a wrong/foreign id
    # returns False rather than a silent no-op).
    try:
        s3_client.head_object(Bucket=target_bucket, Key=index_key)
    except Exception:
        return False

    # Delete the index JSON.
    try:
        s3_client.delete_object(Bucket=target_bucket, Key=index_key)
    except Exception:
        logger.exception("Failed to delete document index %s", index_key)

    # Delete the original file(s) under docindex/<doc_id>/.
    original_prefix = f"{_index_list_prefix(prefix)}{safe_doc_id}/"
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=target_bucket, Prefix=original_prefix):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if objects:
                s3_client.delete_objects(Bucket=target_bucket, Delete={"Objects": objects})
    except Exception:
        logger.exception("Failed to delete original files under %s", original_prefix)

    return True
