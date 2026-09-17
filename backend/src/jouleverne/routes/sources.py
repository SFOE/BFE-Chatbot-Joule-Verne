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


def _resolve_specific_original_key(extracted_bucket: str, extracted_key: str) -> str | None:
    """Map an extracted-bucket object key back to the original inbox object key.

    The processor Lambda writes a "<key>.metadata.json" sidecar next to every
    extracted object, carrying metadataAttributes.original_key. That is the
    authoritative mapping (it survives filename rewrites and splitting).

    Falls back to a best-effort reverse of the extracted naming convention when
    no sidecar is present, verifying the candidate exists in the inbox bucket:
      "<base>_partN.txt" -> "<base>.<original-ext>"
      "<base>.txt"       -> "<base>.<original-ext>"
      passthrough copies keep the same key.
    """
    # 1. Authoritative: the sidecar written alongside the extracted object.
    try:
        obj = s3_client.get_object(Bucket=extracted_bucket, Key=f"{extracted_key}.metadata.json")
        attrs = json.loads(obj["Body"].read()).get("metadataAttributes", {})
        original_key = attrs.get("original_key")
        if original_key:
            return original_key
    except Exception:
        pass

    # 2. Fallback: reverse the naming convention and confirm the object exists.
    import re
    base = re.sub(r"_part\d+\.txt$", "", extracted_key)
    if base == extracted_key:
        base = re.sub(r"\.txt$", "", extracted_key)

    # Passthrough copies share the exact key with the original.
    if _inbox_object_exists(extracted_key):
        return extracted_key

    # Text was extracted from some original with the same base name; probe the
    # extensions the processor extracts text from.
    for ext in (".pdf", ".docx", ".txt", ".md", ".html", ".htm", ".msg"):
        candidate = f"{base}{ext}"
        if _inbox_object_exists(candidate):
            return candidate

    return None


def _sidecar_source_url(extracted_bucket: str, extracted_key: str) -> str | None:
    """Return the "source_url" from an extracted object's ".metadata.json" sidecar.

    API-generated documents (e.g. BFE Medienmitteilungen) have no inbox original;
    their sidecar carries a "source_url" (public page URL) instead of "original_key".
    Returns None when there is no sidecar or no source_url.
    """
    try:
        obj = s3_client.get_object(
            Bucket=extracted_bucket, Key=f"{extracted_key}.metadata.json"
        )
        attrs = json.loads(obj["Body"].read()).get("metadataAttributes", {})
        source_url = attrs.get("source_url", {}).get("value", {}).get("stringValue", "")
        return source_url or None
    except Exception:
        return None


def _inbox_object_exists(key: str) -> bool:
    if not settings.SPECIFIC_KBS_BUCKET:
        return False
    try:
        s3_client.head_object(Bucket=settings.SPECIFIC_KBS_BUCKET, Key=key)
        return True
    except Exception:
        return False


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

        # PDF/extracted text sources — map to PDF in PDF bucket
        elif bucket == settings.EXTRACTED_BUCKET:
            import re
            # Strip _partN suffix and convert .txt → .pdf
            pdf_key = re.sub(r"_part\d+\.txt$", ".pdf", key)
            if pdf_key == key:
                pdf_key = key.replace(".txt", ".pdf")
            pdf_filename = pdf_key.rsplit("/", 1)[-1] if "/" in pdf_key else pdf_key
            try:
                download_url = s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": settings.PDF_BUCKET, "Key": pdf_key},
                    ExpiresIn=300,
                )
                result["download_url"] = download_url
                result["pdf_filename"] = pdf_filename
            except Exception:
                pass
            result["type"] = "document"

        # Specific-KB EXTRACTED bucket — the specific KBs sync from here, so
        # citations reference objects in this bucket. Two kinds of objects:
        #
        # 1. Website content under a "website/" sub-prefix (e.g.
        #    "<kb-prefix>/website/<page>.txt"), written by the same crawling
        #    pipeline as the shared website KB. It carries the original page URL
        #    in S3 user-metadata "source_url". Resolve it like WEBSITE_BUCKET so
        #    the sidebar links to the webpage.
        #
        # 2. Processed uploads (extracted "<name>.txt" / "<name>_partN.txt" or a
        #    passthrough-copied raw file). The citable artifact is the ORIGINAL
        #    file in the inbox bucket, not the extracted text. Read the object's
        #    ".metadata.json" sidecar to get "original_key", then presign a
        #    download of that original from SPECIFIC_KBS_BUCKET. Report type
        #    "specific" with the original filename so the sidebar cites the
        #    original document.
        elif settings.SPECIFIC_KBS_EXTRACTED_BUCKET and bucket == settings.SPECIFIC_KBS_EXTRACTED_BUCKET:
            if "/website/" in f"/{key}":
                try:
                    head = s3_client.head_object(Bucket=bucket, Key=key)
                    result["source_url"] = head.get("Metadata", {}).get("source_url", "")
                except Exception:
                    result["source_url"] = ""
                result["type"] = "website"
            elif (_source_url := _sidecar_source_url(bucket, key)):
                # API-generated documents (e.g. BFE Medienmitteilungen) have no inbox
                # original to download. Their ".metadata.json" sidecar carries a
                # "source_url" pointing at the public page. Cite it like a website
                # source so the sidebar links to the live page.
                result["source_url"] = _source_url
                result["type"] = "website"
            else:
                original_key = _resolve_specific_original_key(bucket, key)
                if original_key:
                    original_filename = original_key.rsplit("/", 1)[-1]
                    try:
                        download_url = s3_client.generate_presigned_url(
                            "get_object",
                            Params={
                                "Bucket": settings.SPECIFIC_KBS_BUCKET,
                                "Key": original_key,
                            },
                            ExpiresIn=300,
                        )
                        result["download_url"] = download_url
                        result["filename"] = original_filename
                    except Exception:
                        pass
                else:
                    # No original found — fall back to the extracted object.
                    try:
                        download_url = s3_client.generate_presigned_url(
                            "get_object",
                            Params={"Bucket": bucket, "Key": key},
                            ExpiresIn=300,
                        )
                        result["download_url"] = download_url
                    except Exception:
                        pass
                result["type"] = "specific"

        # Specific-KB INBOX bucket (legacy / direct reference). Kept so a
        # citation that still points at an original in the inbox resolves to a
        # raw download.
        elif settings.SPECIFIC_KBS_BUCKET and bucket == settings.SPECIFIC_KBS_BUCKET:
            if "/website/" in f"/{key}":
                try:
                    head = s3_client.head_object(Bucket=bucket, Key=key)
                    result["source_url"] = head.get("Metadata", {}).get("source_url", "")
                except Exception:
                    result["source_url"] = ""
                result["type"] = "website"
            else:
                try:
                    download_url = s3_client.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": bucket, "Key": key},
                        ExpiresIn=300,
                    )
                    result["download_url"] = download_url
                except Exception:
                    pass
                result["type"] = "specific"

        # Any other bucket — fallback: try a direct presigned download so the
        # source is still clickable rather than silently dropped.
        else:
            try:
                download_url = s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket, "Key": key},
                    ExpiresIn=300,
                )
                result["download_url"] = download_url
            except Exception:
                pass
            result["type"] = "document"

    except Exception as e:
        logger.error("Failed to get metadata for %s: %s", uri, e)
        raise HTTPException(status_code=500, detail="Failed to retrieve source metadata.")

    return result
