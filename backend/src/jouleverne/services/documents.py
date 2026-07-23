"""Document processing — text extraction, summarization, and chunking.

Ported from the Streamlit app's src/document_processing.py.
Supports multiple documents with a hybrid strategy:
- Large tabular files (XLSX, CSV) → flagged for Code Interpreter
- Text documents (PDF, TXT, DOCX) → full text or summary via session attributes
"""

import csv
import io
import json
import logging
import re
from typing import Optional

import boto3
from pypdf import PdfReader
from docx import Document as DocxDocument
from openpyxl import load_workbook

from ..config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TOKEN_THRESHOLD = 80_000  # ~80K tokens ≈ 320K chars
CHAR_THRESHOLD = TOKEN_THRESHOLD * 4
CHUNK_SIZE = 2000
SESSION_ATTR_MAX_CHARS = 24_000
MAX_UPLOAD_FILES = 5
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = {"pdf", "txt", "docx", "xlsx", "csv"}
MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


# ---------------------------------------------------------------------------
# Text Extraction
# ---------------------------------------------------------------------------

def extract_text(file_bytes: bytes, filename: str) -> tuple[str, int]:
    """Extract text from an uploaded file. Returns (text, page_count).

    Raises ValueError for unsupported types or low-quality extraction.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    extractors = {
        "pdf": _extract_pdf,
        "txt": _extract_txt,
        "docx": _extract_docx,
        "xlsx": _extract_xlsx,
        "csv": _extract_csv,
    }

    extractor = extractors.get(ext)
    if not extractor:
        raise ValueError(f"Unsupported file type: .{ext}")

    text, pages = extractor(file_bytes)

    # Skip quality check for tabular files
    if ext not in ("xlsx", "csv") and not _text_quality_ok(text):
        raise ValueError(
            "Extracted text appears low quality (possibly a scanned PDF). "
            "Please upload a text-based document."
        )

    return text, pages


def _extract_pdf(file_bytes: bytes) -> tuple[str, int]:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return _clean_text("\n\n".join(pages)), len(reader.pages)


def _extract_txt(file_bytes: bytes) -> tuple[str, int]:
    text = file_bytes.decode("utf-8", errors="replace")
    return _clean_text(text), 1


def _extract_docx(file_bytes: bytes) -> tuple[str, int]:
    doc = DocxDocument(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    full_text = _clean_text("\n\n".join(paragraphs))
    page_estimate = max(1, len(full_text) // 3000)
    return full_text, page_estimate


def _extract_xlsx(file_bytes: bytes) -> tuple[str, int]:
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    sheets_text = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            cell_values = [str(cell) if cell is not None else "" for cell in row]
            if any(v.strip() for v in cell_values):
                rows.append(" | ".join(cell_values))
        if rows:
            sheets_text.append(f"--- Sheet: {sheet_name} ---\n" + "\n".join(rows))
    wb.close()
    return _clean_text("\n\n".join(sheets_text)), len(wb.sheetnames)


def _extract_csv(file_bytes: bytes) -> tuple[str, int]:
    text_content = file_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text_content))
    rows = [" | ".join(row) for row in reader if any(cell.strip() for cell in row)]
    return _clean_text("\n".join(rows)), 1


# ---------------------------------------------------------------------------
# Text Quality & Cleaning
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    text = re.sub(r"<svg[^>]*>.*?</svg>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _text_quality_ok(text: str, min_alpha_ratio: float = 0.3, min_length: int = 50) -> bool:
    if len(text.strip()) < min_length:
        return False
    alpha_chars = sum(1 for c in text if c.isalpha())
    total_chars = len(text.replace(" ", "").replace("\n", ""))
    if total_chars == 0:
        return False
    return (alpha_chars / total_chars) >= min_alpha_ratio


# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------

def summarize_document(text: str) -> str:
    """Summarize a large document using Bedrock Claude Haiku."""
    bedrock_runtime = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION)

    max_input_chars = 200_000
    truncated = text[:max_input_chars]
    if len(text) > max_input_chars:
        truncated += "\n\n[... document truncated for summarization ...]"

    prompt = (
        "Summarize the following document comprehensively, preserving key facts, "
        "figures, dates, names, and structural sections. The summary should be "
        "detailed enough to answer most questions about the document's content.\n\n"
        f"DOCUMENT:\n{truncated}"
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    })

    try:
        response = bedrock_runtime.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"]
    except Exception as e:
        logger.error("Summarization failed: %s", e)
        fallback_len = SESSION_ATTR_MAX_CHARS - 500
        return text[:fallback_len] + "\n\n[... truncated, summarization unavailable ...]"


# ---------------------------------------------------------------------------
# Context Preparation
# ---------------------------------------------------------------------------

def prepare_document_context(extracted_text: str, file_ext: str = "") -> tuple[str, str]:
    """Decide whether to use full text or summary.

    Returns (context_text, context_mode) where context_mode is
    "full", "summary", or "code_interpreter".
    """
    is_tabular = file_ext in ("xlsx", "csv")

    if is_tabular:
        if len(extracted_text) <= SESSION_ATTR_MAX_CHARS:
            return extracted_text, "full"
        else:
            return (
                f"[Large tabular document — {len(extracted_text):,} characters. "
                f"File will be sent to Code Interpreter for analysis.]"
            ), "code_interpreter"

    if len(extracted_text) <= SESSION_ATTR_MAX_CHARS:
        return extracted_text, "full"
    else:
        summary = summarize_document(extracted_text)
        return summary, "summary"


# ---------------------------------------------------------------------------
# Multi-Document Processing
# ---------------------------------------------------------------------------

def process_multiple_documents(files_data: list[dict]) -> dict:
    """Process uploaded documents and categorize by handling strategy.

    Args:
        files_data: List of dicts with 'name' and 'bytes' keys.

    Returns:
        Dict with 'text_docs', 'code_interpreter_docs', and 'errors' lists.
    """
    result = {
        "text_docs": [],
        "code_interpreter_docs": [],
        "errors": [],
    }

    for file_info in files_data:
        name = file_info["name"]
        file_bytes = file_info["bytes"]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

        try:
            extracted_text, page_count = extract_text(file_bytes, name)
        except (ValueError, Exception) as e:
            result["errors"].append({"name": name, "error": str(e)})
            continue

        is_tabular = ext in ("xlsx", "csv")

        if is_tabular and len(extracted_text) > SESSION_ATTR_MAX_CHARS:
            media_type = MEDIA_TYPES.get(ext, "application/octet-stream")
            result["code_interpreter_docs"].append({
                "name": name,
                "bytes": file_bytes,
                "media_type": media_type,
            })
        else:
            doc_context, context_mode = prepare_document_context(extracted_text, file_ext=ext)
            result["text_docs"].append({
                "name": name,
                "full_text": extracted_text,
                "page_count": page_count,
                "context": doc_context,
                "context_mode": context_mode,
            })

    return result
