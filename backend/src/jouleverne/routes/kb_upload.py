"""Presigned upload endpoint — generate a presigned S3 PUT URL for specific KB documents.

The frontend requests an upload URL for a given KB, then uploads the file
directly to S3. The uploaded object lands under the KB's configured prefix,
which triggers the debounced KB sync.
"""

import os
import re
import logging

from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel

from ..services.clients import s3_client
from ..services.security import limiter, verify_cognito_auth
from ..config import settings
from .kbs import get_prefix_for_kb

router = APIRouter(prefix="/v1", tags=["kb_upload"])
logger = logging.getLogger(__name__)

# File types the Bedrock KB can ingest (or that we convert before ingestion)
ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".html", ".doc", ".docx",
    ".csv", ".xls", ".xlsx", ".pdf",
    ".jpeg", ".jpg", ".png",
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

    filename = body.filename.strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Missing filename.")

    # Sanitize filename — letters, numbers, hyphens, underscores, spaces, dots
    if not re.match(r"^[\w\-. ]+$", filename):
        raise HTTPException(
            status_code=400,
            detail="Invalid filename. Use only letters, numbers, hyphens, underscores, spaces, and dots.",
        )

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' is not supported.",
        )

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
