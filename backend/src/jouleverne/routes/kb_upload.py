"""Presigned upload endpoint — generate a presigned S3 PUT URL for specific KB documents.

The frontend requests an upload URL for a given KB, then uploads the file
directly to S3. The uploaded object lands under the KB's configured prefix,
which triggers the debounced KB sync.
"""

import asyncio
import os
import re
import logging

from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from ..services.clients import s3_client
from ..services.security import limiter, verify_cognito_auth, verify_kb_write_permission
from ..services.documents import (
    check_sensitivity_label,
    is_sensitivity_restricted,
    check_classification_in_text,
)
from ..config import settings
from .kbs import get_prefix_for_kb

router = APIRouter(prefix="/v1", tags=["kb_upload"])
logger = logging.getLogger(__name__)

# Upload size limits for KB documents. Kept in sync with the frontend
# (KbUploadView.vue): images are capped lower because Bedrock image ingestion
# has a smaller payload limit than text documents.
MAX_DOC_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_IMAGE_SIZE_BYTES = int(3.75 * 1024 * 1024)  # 3.75 MB
IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png"}


def _sanitize_kb_filename(filename: str) -> str:
    """Sanitize and validate an uploaded filename, returning the cleaned name.

    Mirrors the BFE publications pipeline: strips forbidden characters,
    collapses whitespace, truncates, and preserves the extension.
    Raises HTTPException(400) for missing/invalid names.
    """
    filename = (filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Missing filename.")

    forbidden_chars = r'\/:*?"<>|'
    cleaned = ''.join(c for c in filename if c not in forbidden_chars)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = cleaned[:150] if cleaned else "document"

    name_part, ext_part = os.path.splitext(cleaned)
    if not name_part:
        name_part = "document"
    filename = name_part + ext_part

    if not filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename.")

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' is not supported.",
        )

    return filename

# File types the Bedrock KB can ingest (or that we convert before ingestion)
ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".html", ".doc", ".docx",
    ".csv", ".xls", ".xlsx", ".pdf",
    ".jpeg", ".jpg", ".png",
    ".msg",
}

CONTENT_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".csv": "text/csv",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pdf": "application/pdf",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".msg": "application/vnd.ms-outlook",
}


class UploadUrlRequest(BaseModel):
    kb_id: str
    filename: str


@router.post("/kbs/upload-url")
@limiter.limit(settings.RATE_LIMIT)
async def create_upload_url(
    request: Request,
    body: UploadUrlRequest,
    _auth: None = Depends(verify_cognito_auth),
):
    """Generate a presigned S3 PUT URL for uploading a document to a specific KB."""
    if not settings.SPECIFIC_KBS_BUCKET:
        raise HTTPException(status_code=500, detail="Upload is not configured.")

    prefix = get_prefix_for_kb(body.kb_id)
    if prefix is None:
        raise HTTPException(status_code=403, detail="Unknown or not-allowed knowledge base.")

    # Per-KB write allowlist: only permitted e-mails may upload to this KB.
    verify_kb_write_permission(body.kb_id, request)

    filename = _sanitize_kb_filename(body.filename)
    ext = os.path.splitext(filename)[1].lower()

    content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
    key = f"{prefix}/{filename}"

    try:
        url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.SPECIFIC_KBS_BUCKET,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=settings.UPLOAD_URL_EXPIRATION,
        )
    except Exception as e:
        logger.error("Failed to generate presigned URL: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate upload URL.")

    return {
        "upload_url": url,
        "key": key,
        "content_type": content_type,
        "expires_in": settings.UPLOAD_URL_EXPIRATION,
    }


@router.post("/kbs/upload")
@limiter.limit(settings.RATE_LIMIT)
async def upload_kb_document(
    request: Request,
    kb_id: str = Form(...),
    file: UploadFile = File(...),
    _auth: None = Depends(verify_cognito_auth),
):
    """Upload a document to a specific KB *through the backend*.

    Unlike the presigned-URL flow, the file passes through the backend so it
    can be screened for sensitivity/classification markers (GEHEIM,
    VERTRAULICH, MIP labels) before it is written to S3 — the same check the
    chat document upload applies.
    """
    if not settings.SPECIFIC_KBS_BUCKET:
        raise HTTPException(status_code=500, detail="Upload is not configured.")

    prefix = get_prefix_for_kb(kb_id)
    if prefix is None:
        raise HTTPException(status_code=403, detail="Unknown or not-allowed knowledge base.")

    # Per-KB write allowlist: only permitted e-mails may upload to this KB.
    verify_kb_write_permission(kb_id, request)

    filename = _sanitize_kb_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()

    content = await file.read()

    is_image = ext in IMAGE_EXTENSIONS
    max_size = MAX_IMAGE_SIZE_BYTES if is_image else MAX_DOC_SIZE_BYTES
    if len(content) > max_size:
        max_label = "3.75 MB" if is_image else "50 MB"
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds the {max_label} limit.",
        )

    # --- Sensitivity / classification screening (same as chat upload) ---
    label_info = await asyncio.to_thread(check_sensitivity_label, content, filename)
    if is_sensitivity_restricted(label_info):
        label_name = (label_info or {}).get("name", "unknown")
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Die Datei ist als vertraulich/geheim eingestuft und kann nicht hochgeladen werden.",
                "sensitivity_blocked": True,
                "reason": f"sensitivity_label_blocked:{label_name}",
            },
        )

    classification_keyword = await asyncio.to_thread(
        check_classification_in_text, content, filename
    )
    if classification_keyword:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    f'Die Datei enthält den Hinweis "{classification_keyword}" '
                    "und kann nicht hochgeladen werden."
                ),
                "sensitivity_blocked": True,
                "reason": f"sensitivity_keyword_blocked:{classification_keyword}",
            },
        )

    content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
    key = f"{prefix}/{filename}"

    try:
        s3_client.put_object(
            Bucket=settings.SPECIFIC_KBS_BUCKET,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
    except Exception as e:
        logger.error("Failed to upload object %s: %s", key, e)
        raise HTTPException(status_code=500, detail="Failed to upload file.")

    return {
        "key": key,
        "name": filename,
        "content_type": content_type,
        "size": len(content),
    }


@router.get("/kbs/{kb_id}/files")
@limiter.limit(settings.RATE_LIMIT)
async def list_kb_files(
    kb_id: str,
    request: Request,
    _auth: None = Depends(verify_cognito_auth),
):
    """List all files in a specific KB's S3 prefix."""
    if not settings.SPECIFIC_KBS_BUCKET:
        raise HTTPException(status_code=500, detail="Upload is not configured.")

    prefix = get_prefix_for_kb(kb_id)
    if prefix is None:
        raise HTTPException(status_code=403, detail="Unknown or not-allowed knowledge base.")

    try:
        files = []
        paginator = s3_client.get_paginator("list_objects_v2")
        # Delimiter="/" keeps the listing flat: objects directly under the
        # prefix land in "Contents", while anything inside a subdirectory is
        # rolled up into "CommonPrefixes" (which we ignore). This mirrors the
        # upload endpoint, which only ever writes flat "{prefix}/{filename}"
        # keys.
        for page in paginator.paginate(
            Bucket=settings.SPECIFIC_KBS_BUCKET,
            Prefix=f"{prefix}/",
            Delimiter="/",
        ):
            for obj in page.get("Contents", []):
                name = obj["Key"].split("/")[-1]
                if not name:
                    continue
                files.append({
                    "key": obj["Key"],
                    "name": name,
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                })
        return files
    except Exception as e:
        logger.error("Failed to list objects for KB %s: %s", kb_id, e)
        raise HTTPException(status_code=500, detail="Failed to list files.")


class DeleteFileRequest(BaseModel):
    key: str


@router.delete("/kbs/{kb_id}/files")
@limiter.limit(settings.RATE_LIMIT)
async def delete_kb_file(
    kb_id: str,
    body: DeleteFileRequest,
    request: Request,
    _auth: None = Depends(verify_cognito_auth),
):
    """Delete a file from a specific KB's S3 prefix."""
    if not settings.SPECIFIC_KBS_BUCKET:
        raise HTTPException(status_code=500, detail="Upload is not configured.")

    prefix = get_prefix_for_kb(kb_id)
    if prefix is None:
        raise HTTPException(status_code=403, detail="Unknown or not-allowed knowledge base.")

    # Per-KB write allowlist: only permitted e-mails may delete from this KB.
    verify_kb_write_permission(kb_id, request)

    # Ensure the key belongs to the KB's prefix (prevent deletion of other files)
    if not body.key.startswith(f"{prefix}/"):
        raise HTTPException(status_code=403, detail="Cannot delete files outside this knowledge base.")

    try:
        s3_client.delete_object(
            Bucket=settings.SPECIFIC_KBS_BUCKET,
            Key=body.key,
        )
    except Exception as e:
        logger.error("Failed to delete object %s: %s", body.key, e)
        raise HTTPException(status_code=500, detail="Failed to delete file.")

    return {"deleted": body.key}


class DownloadUrlRequest(BaseModel):
    key: str


@router.post("/kbs/{kb_id}/download-url")
@limiter.limit(settings.RATE_LIMIT)
async def create_download_url(
    kb_id: str,
    body: DownloadUrlRequest,
    request: Request,
    _auth: None = Depends(verify_cognito_auth),
):
    """Generate a presigned S3 GET URL for downloading a file from a specific KB."""
    if not settings.SPECIFIC_KBS_BUCKET:
        raise HTTPException(status_code=500, detail="Upload is not configured.")

    prefix = get_prefix_for_kb(kb_id)
    if prefix is None:
        raise HTTPException(status_code=403, detail="Unknown or not-allowed knowledge base.")

    # Ensure the key belongs to the KB's prefix
    if not body.key.startswith(f"{prefix}/"):
        raise HTTPException(status_code=403, detail="Cannot download files outside this knowledge base.")

    try:
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.SPECIFIC_KBS_BUCKET,
                "Key": body.key,
            },
            ExpiresIn=settings.UPLOAD_URL_EXPIRATION,
        )
    except Exception as e:
        logger.error("Failed to generate download URL for %s: %s", body.key, e)
        raise HTTPException(status_code=500, detail="Failed to generate download URL.")

    return {"download_url": url}
