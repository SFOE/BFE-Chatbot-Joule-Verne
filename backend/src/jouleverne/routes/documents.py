"""Document upload endpoint — process uploaded files for chat context."""

import logging

from fastapi import APIRouter, Request, UploadFile, File, Depends, HTTPException

from ..models.documents import (
    DocumentUploadResponse,
    TextDocResult,
    CodeInterpreterDocResult,
    DocumentError,
)
from ..services.documents import (
    process_multiple_documents,
    MAX_UPLOAD_FILES,
    MAX_FILE_SIZE_BYTES,
    ALLOWED_EXTENSIONS,
)
from ..services.security import limiter, verify_cognito_auth
from ..config import settings

router = APIRouter(prefix="/v1", tags=["documents"])
logger = logging.getLogger(__name__)


@router.post("/documents/upload", response_model=DocumentUploadResponse)
@limiter.limit(settings.RATE_LIMIT)
async def upload_documents(
    request: Request,
    files: list[UploadFile] = File(...),
    _auth: None = Depends(verify_cognito_auth),
):
    """Upload and process documents for use as chat context.

    Supported formats: PDF, TXT, DOCX, XLSX, CSV.
    Max 5 files, 10 MB each.

    The frontend stores the response and sends relevant context
    back with each chat request (stateless backend).
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

    # Process valid files
    processed = process_multiple_documents(files_data)

    # Combine early validation errors with processing errors
    all_errors = errors + processed["errors"]

    return DocumentUploadResponse(
        text_docs=[
            TextDocResult(
                name=d["name"],
                page_count=d["page_count"],
                context=d["context"],
                context_mode=d["context_mode"],
            )
            for d in processed["text_docs"]
        ],
        code_interpreter_docs=[
            CodeInterpreterDocResult(name=d["name"], media_type=d["media_type"])
            for d in processed["code_interpreter_docs"]
        ],
        errors=[DocumentError(name=e["name"], error=e["error"]) for e in all_errors],
    )
