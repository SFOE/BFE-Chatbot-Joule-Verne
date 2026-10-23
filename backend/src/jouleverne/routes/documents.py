"""Document upload endpoint — process uploaded files for chat context."""

import asyncio
import base64
import logging

from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, HTTPException

from ..models.documents import (
    DocumentUploadResponse,
    TextDocResult,
    CodeInterpreterDocResult,
    IndexedDocResult,
    SessionFileResult,
    DocumentError,
)
from ..services.documents import (
    process_multiple_documents,
    build_indexed_documents_summary,
    MAX_UPLOAD_FILES,
    MAX_FILE_SIZE_BYTES,
    ALLOWED_EXTENSIONS,
)
from ..services import doc_index
from ..services import session_files
from ..services import conversations as convo
from ..services.security import limiter, verify_cognito_auth, extract_user_sub
from ..config import settings

router = APIRouter(prefix="/v1", tags=["documents"])
logger = logging.getLogger(__name__)


def _store_originals(
    prefix: str,
    bytes_by_name: dict[str, bytes],
    inline_docs: list[dict],
    indexed_docs: list[dict],
    ci_docs: list[dict],
) -> dict[str, str | None]:
    """Store every uploaded original + meta, tagged by routing. Returns name->id.

    Indexed docs also keep their docindex original (written by build_index); the
    uploads/ record links back via doc_id so the two layouts stay consistent.
    """
    name_to_id: dict[str, str | None] = {}

    def _store(name: str, routing: str, media_type: str = "", doc_id: str | None = None):
        raw = bytes_by_name.get(name, b"")
        if not raw:
            return
        meta = session_files.store_file(
            prefix=prefix, file_bytes=raw, filename=name,
            routing=routing, media_type=media_type, doc_id=doc_id,
        )
        name_to_id[name] = (meta or {}).get("file_id")

    for d in inline_docs:
        _store(d["name"], "inline")
    for d in indexed_docs:
        _store(d["name"], "index", doc_id=d.get("doc_id"))
    for d in ci_docs:
        _store(d["name"], "ci", media_type=d.get("media_type", ""))

    return name_to_id


def _index_large_text_docs(text_docs: list[dict], prefix: str) -> tuple[list[dict], list[dict]]:
    """Split processed text docs into small (inline) and large (indexed).

    Large text documents (``context_mode == "summary"``, i.e. over the inline
    size threshold) are indexed server-side instead of returning their text, so
    the agent searches them on demand. Small ones keep the current inline-context
    behaviour. Returns (inline_text_docs, indexed_docs).

    Runs the (blocking) extraction + embedding; call from a worker thread.
    """
    inline: list[dict] = []
    indexed: list[dict] = []
    for d in text_docs:
        if d.get("context_mode") == "summary":
            try:
                summary = doc_index.build_index(
                    prefix=prefix,
                    file_bytes=d["_raw_bytes"],
                    filename=d["name"],
                )
            except Exception:
                logger.exception("Indexing failed for %s; falling back to inline summary.", d["name"])
                summary = None
            if summary:
                indexed.append(summary)
                continue
            # Fall back to inline context if indexing produced nothing.
            inline.append(d)
        else:
            inline.append(d)
    return inline, indexed


@router.post("/documents/upload", response_model=DocumentUploadResponse)
@limiter.limit(settings.RATE_LIMIT)
async def upload_documents(
    request: Request,
    files: list[UploadFile] = File(...),
    session_id: str = Form(...),
    _auth: None = Depends(verify_cognito_auth),
):
    """Upload and process documents for use as chat context.

    Supported formats: PDF, TXT, DOCX, XLSX, CSV. Max 5 files, 10 MB each.

    Small text documents are returned inline (sent back with each chat request).
    Large text documents are indexed server-side (per session) and only a
    reference is returned; the agent searches them on demand. Tabular files go
    to the Code Interpreter path unchanged.
    """
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_UPLOAD_FILES} files allowed.",
        )

    files_data = []
    errors = []

    for upload_file in files:
        filename = upload_file.filename or "unknown"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext not in ALLOWED_EXTENSIONS:
            errors.append({"name": filename, "error": f"Unsupported file type: .{ext}"})
            continue

        content = await upload_file.read()

        if len(content) > MAX_FILE_SIZE_BYTES:
            errors.append({"name": filename, "error": "File exceeds 10 MB limit."})
            continue

        files_data.append({"name": filename, "bytes": content})

    # Identity + persistence mode decide whether large text docs are indexed and
    # where (persistent session prefix vs. short-lived ephemeral). Unknown user
    # => treat as opt-out, and index only when storage can be scoped and is
    # configured; otherwise fall back to the legacy inline-summary behaviour.
    sub = extract_user_sub(request)
    indexing_enabled = bool(sub and session_id and convo.is_persistence_configured())

    # Process valid files (offload to thread to avoid blocking the event loop).
    # ``can_index`` lets the processor safely drop a document's inline context
    # ONLY when we will index it below; otherwise content is preserved inline or
    # summarized so it is never lost. ``summarize_large`` is the no-index
    # fallback: summarize a too-large doc rather than inline the whole thing.
    try:
        processed = await asyncio.to_thread(
            process_multiple_documents,
            files_data,
            not indexing_enabled,  # summarize_large (no-index fallback)
            None,  # messages (fresh upload; no running history to count)
            None,  # session_attributes
            indexing_enabled,  # can_index
        )
    except Exception as e:
        logger.exception("Unexpected error processing documents: %s", e)
        raise HTTPException(status_code=500, detail=f"Document processing failed: {e}")

    inline_docs = processed["text_docs"]
    indexed_docs: list[dict] = []
    # Processed text docs that were indexed (kept so we can build the agent
    # summary from their full text, which the index dicts do not carry).
    indexed_source_docs: list[dict] = []

    # name -> file_id, for the originals stored this request.
    file_ids: dict[str, str | None] = {}

    if indexing_enabled:
        save_history = convo.get_save_enabled(sub)
        prefix = doc_index.session_prefix(sub, session_id, save_history)

        # Enforce the per-session file limit server-side (not just in the UI):
        # already-stored files + the valid files in this request must not exceed
        # MAX_UPLOAD_FILES.
        existing = await asyncio.to_thread(session_files.count_files, prefix)
        if existing + len(files_data) > MAX_UPLOAD_FILES:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {MAX_UPLOAD_FILES} files per chat.",
            )

        # Carry raw bytes into the indexing step (re-attach from files_data).
        bytes_by_name: dict[str, bytes] = {f["name"]: f["bytes"] for f in files_data}
        for d in processed["text_docs"]:
            d["_raw_bytes"] = bytes_by_name.get(d["name"], b"")

        # Docs flagged "summary" are the ones _index_large_text_docs will try to
        # index. Capture them (with full_text) before the call so a successful
        # index can be summarized for the agent.
        summary_candidates = [
            d for d in processed["text_docs"] if d.get("context_mode") == "summary"
        ]

        inline_docs, indexed_docs = await asyncio.to_thread(
            _index_large_text_docs, processed["text_docs"], prefix
        )

        # Keep only candidates that were actually indexed (indexing can fall
        # back to inline on failure, in which case they reappear in inline_docs).
        indexed_names = {d["name"] for d in indexed_docs}
        indexed_source_docs = [d for d in summary_candidates if d["name"] in indexed_names]

        # Store the original of every uploaded file (A), tagged with its routing
        # so a continued chat can list/restore them and the agent can load CI
        # files from S3 on demand (B). Runs on a worker thread (S3 I/O).
        file_ids = await asyncio.to_thread(
            _store_originals, prefix, bytes_by_name, inline_docs, indexed_docs,
            processed["code_interpreter_docs"],
        )

    # Agent-facing summary of the indexed ("teilweise") documents so the agent
    # knows they exist and what they are, even though their text is not inlined.
    document_summary = build_indexed_documents_summary(indexed_source_docs)

    all_errors = errors + processed["errors"]

    return DocumentUploadResponse(
        text_docs=[
            TextDocResult(
                name=d["name"],
                page_count=d["page_count"],
                context=d["context"],
                context_mode=d["context_mode"],
                file_id=file_ids.get(d["name"]),
            )
            for d in inline_docs
        ],
        code_interpreter_docs=[
            CodeInterpreterDocResult(
                name=d["name"],
                media_type=d["media_type"],
                data=base64.b64encode(d["bytes"]).decode("ascii"),
                file_id=file_ids.get(d["name"]),
            )
            for d in processed["code_interpreter_docs"]
        ],
        indexed_docs=[
            IndexedDocResult(
                name=d["name"],
                doc_id=d["doc_id"],
                chunk_count=d["chunk_count"],
                file_id=file_ids.get(d["name"]),
            )
            for d in indexed_docs
        ],
        errors=[DocumentError(name=e["name"], error=e["error"], sensitivity_blocked=e.get("sensitivity_blocked", False)) for e in all_errors],
        document_summary=document_summary,
    )


@router.get("/documents/indexed", response_model=list[IndexedDocResult])
@limiter.limit(settings.RATE_LIMIT)
async def list_indexed_documents(
    request: Request,
    session_id: str,
    _auth: None = Depends(verify_cognito_auth),
):
    """List the documents indexed for a session (for restoring the UI on load).

    Returns an empty list when the user has no identity, the session has no
    index, or persistence is unconfigured. Scoped to the caller's own `sub`.
    """
    sub = extract_user_sub(request)
    if not (sub and session_id and convo.is_persistence_configured()):
        return []

    # The index lives under the persistent prefix for a saved chat; opt-out
    # (ephemeral) sessions are not restored on load since they are not listed.
    prefix = doc_index.session_prefix(sub, session_id, save_history=True)
    docs = await asyncio.to_thread(doc_index.list_documents, prefix)
    return [
        IndexedDocResult(name=d["name"], doc_id=d["doc_id"], chunk_count=d["chunk_count"])
        for d in docs
    ]


def _list_session_files(sub: str, session_id: str) -> list[dict]:
    """List a session's uploaded files, trying persistent then ephemeral prefix.

    Returns the first non-empty result (a session's files all live under one
    prefix, decided by the save opt-in at upload time).
    """
    for save_history in (True, False):
        prefix = doc_index.session_prefix(sub, session_id, save_history=save_history)
        metas = session_files.list_files(prefix)
        if metas:
            return metas
    return []


@router.get("/documents/session-files", response_model=list[SessionFileResult])
@limiter.limit(settings.RATE_LIMIT)
async def list_session_files(
    request: Request,
    session_id: str,
    _auth: None = Depends(verify_cognito_auth),
):
    """List all files uploaded in a session (for restoring the UI on continue).

    Returns the stored originals' metadata (no bytes), each tagged with its
    routing. Scoped to the caller's own `sub`; empty when no identity/files.
    """
    sub = extract_user_sub(request)
    if not (sub and session_id and convo.is_persistence_configured()):
        return []
    metas = await asyncio.to_thread(_list_session_files, sub, session_id)
    return [
        SessionFileResult(
            file_id=m["file_id"],
            name=m["name"],
            media_type=m.get("media_type", ""),
            routing=m.get("routing", ""),
            doc_id=m.get("doc_id"),
        )
        for m in metas
    ]


def _delete_session_file(sub: str, session_id: str, file_id: str) -> bool:
    """Delete one uploaded file (any type) by file_id.

    Removes the uploads/<file_id>/ record (original + meta) and, for an indexed
    file, its docindex/<doc_id>.json. Tries the persistent then ephemeral prefix
    (a file lives under whichever matched the save opt-in at upload). Returns
    True if the file was found and deleted.
    """
    for save_history in (True, False):
        prefix = doc_index.session_prefix(sub, session_id, save_history=save_history)
        got = session_files.get_file_bytes(prefix, file_id)
        if got is None:
            continue
        _bytes, meta = got
        # Remove the index too when this file was indexed.
        doc_id = meta.get("doc_id")
        if doc_id:
            doc_index.delete_document(prefix, doc_id)
        session_files.delete_file(prefix, file_id)
        return True
    return False


@router.delete("/documents/{file_id}", status_code=204)
@limiter.limit(settings.RATE_LIMIT)
async def delete_session_file(
    request: Request,
    file_id: str,
    session_id: str,
    _auth: None = Depends(verify_cognito_auth),
):
    """Delete a single uploaded file (any type) from a session.

    Removes the stored original, its meta, and — for indexed documents — the
    search index. Scoped to the caller's own `sub` and session. 404 when not
    found.
    """
    sub = extract_user_sub(request)
    if not (sub and session_id and convo.is_persistence_configured()):
        raise HTTPException(status_code=404, detail="File not found")

    deleted = await asyncio.to_thread(_delete_session_file, sub, session_id, file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")
    return None
