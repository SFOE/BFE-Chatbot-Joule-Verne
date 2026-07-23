"""Source endpoints — presigned downloads and metadata for cited sources."""

import json
import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Request, Depends, HTTPException, Query

from ..services.clients import s3_client
from ..services.security import limiter, verify_cognito_auth
from ..config import settings

router = APIRouter(prefix="/v1", tags=["sources"])
logger = logging.getLogger(__name__)


def _parse_s3_uri(s3_uri: str) -> tuple[str, str, str]:
    """Parse s3://bucket/key into (bucket, key, filename)."""
    if not s3_uri.startswith("s3://"):
        raise ValueError("Invalid S3 URI")
    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    filename = key.rsplit("/", 1)[-1] if "/" in key else key
    return bucket, key, filename


@router.get("/sources/download")
@limiter.limit(settings.RATE_LIMIT)
async def get_download_url(
    request: Request,
    uri: str = Query(..., description="S3 URI (s3://bucket/key)"),
    _auth: None = Depends(verify_cognito_auth),
):
    """Generate a presigned download URL for an S3 source.

    Returns a short-lived presigned URL that the frontend can use
    to download the file directly from S3.
    """
    try:
        bucket, key, filename = _parse_s3_uri(uri)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid S3 URI format.")

    try:
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=300,  # 5 minutes
        )
    except Exception as e:
        logger.error("Failed to generate presigned URL for %s: %s", uri, e)
        raise HTTPException(status_code=500, detail="Failed to generate download URL.")

    return {"url": url, "filename": filename}


@router.get("/sources/metadata")
@limiter.limit(settings.RATE_LIMIT)
async def get_source_metadata(
    request: Request,
    uri: str = Query(..., description="S3 URI (s3://bucket/key)"),
    _auth: None = Depends(verify_cognito_auth),
):
    """Retrieve metadata for a source.

    For website bucket sources: returns the original source URL from S3 metadata.
    For Fedlex bucket sources: returns title, abbreviation, and fedlex URL.
    For other sources: returns basic file info.
    """
    try:
        bucket, key, filename = _parse_s3_uri(uri)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid S3 URI format.")

    result = {"filename": filename, "bucket": bucket}

    try:
        # Website sources — original URL stored in user metadata
        if bucket == settings.WEBSITE_BUCKET:
            head = s3_client.head_object(Bucket=bucket, Key=key)
            metadata = head.get("Metadata", {})
            result["source_url"] = metadata.get("source_url", "")
            result["type"] = "website"

        # Fedlex sources — metadata in a sidecar JSON file
        elif bucket == settings.FEDLEX_BUCKET:
            metadata_key = key + ".metadata.json"
            try:
                obj = s3_client.get_object(Bucket=bucket, Key=metadata_key)
                metadata_json = json.loads(obj["Body"].read())
                attrs = metadata_json.get("metadataAttributes", {})
                result["fedlex_url"] = (
                    attrs.get("fedlex_url", {}).get("value", {}).get("stringValue", "")
                )
                result["title"] = (
                    attrs.get("title", {}).get("value", {}).get("stringValue", "")
                )
                result["abbreviation"] = (
                    attrs.get("abbreviation", {}).get("value", {}).get("stringValue", "")
                )
            except Exception:
                pass
            result["type"] = "fedlex"

        # PDF/extracted text sources
        else:
            result["type"] = "document"

    except Exception as e:
        logger.error("Failed to get metadata for %s: %s", uri, e)
        raise HTTPException(status_code=500, detail="Failed to retrieve source metadata.")

    return result
