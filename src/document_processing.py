"""
Document upload processing: text extraction, summarization, and chunk retrieval.
"""

import csv
import io
import logging
import re
from typing import Optional

import boto3
from pypdf import PdfReader
from docx import Document as DocxDocument
from openpyxl import load_workbook

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TOKEN_THRESHOLD = 80_000  # ~80K tokens ≈ 320K chars
CHAR_THRESHOLD = TOKEN_THRESHOLD * 4  # rough char estimate
CHUNK_SIZE = 2000  # characters per chunk for targeted retrieval
SESSION_ATTR_MAX_CHARS = 24_000  # ~25KB limit for promptSessionAttributes value


# ---------------------------------------------------------------------------
# Text Extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_bytes: bytes) -> tuple[str, int]:
    """Extract text from a PDF file. Returns (text, page_count)."""
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    full_text = "\n\n".join(pages)
    full_text = _clean_text(full_text)
    return full_text, len(reader.pages)


def extract_text_from_txt(file_bytes: bytes) -> tuple[str, int]:
    """Extract text from a plain text file. Returns (text, 1)."""
    text = file_bytes.decode("utf-8", errors="replace")
    text = _clean_text(text)
    return text, 1


def extract_text_from_docx(file_bytes: bytes) -> tuple[str, int]:
    """Extract text from a DOCX file. Returns (text, page_count_estimate)."""
    doc = DocxDocument(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    full_text = "\n\n".join(paragraphs)
    full_text = _clean_text(full_text)
    # Estimate page count (~3000 chars per page)
    page_estimate = max(1, len(full_text) // 3000)
    return full_text, page_estimate


def extract_text_from_xlsx(file_bytes: bytes) -> tuple[str, int]:
    """Extract text from an Excel (.xlsx) file. Returns (text, sheet_count)."""
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    sheets_text = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            cell_values = [str(cell) if cell is not None else "" for cell in row]
            # Skip completely empty rows
            if any(v.strip() for v in cell_values):
                rows.append(" | ".join(cell_values))
        if rows:
            header = f"--- Sheet: {sheet_name} ---"
            sheets_text.append(f"{header}\n" + "\n".join(rows))
    wb.close()
    full_text = "\n\n".join(sheets_text)
    full_text = _clean_text(full_text)
    return full_text, len(wb.sheetnames)


def extract_text_from_csv(file_bytes: bytes) -> tuple[str, int]:
    """Extract text from a CSV file. Returns (text, 1)."""
    text_content = file_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text_content))
    rows = []
    for row in reader:
        if any(cell.strip() for cell in row):
            rows.append(" | ".join(row))
    full_text = "\n".join(rows)
    full_text = _clean_text(full_text)
    return full_text, 1


def extract_text(file_bytes: bytes, filename: str) -> tuple[str, int]:
    """
    Extract text from an uploaded file based on its extension.
    Returns (extracted_text, page_count).
    Raises ValueError if the file type is unsupported or extraction fails.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        text, pages = extract_text_from_pdf(file_bytes)
    elif ext == "txt":
        text, pages = extract_text_from_txt(file_bytes)
    elif ext == "docx":
        text, pages = extract_text_from_docx(file_bytes)
    elif ext == "xlsx":
        text, pages = extract_text_from_xlsx(file_bytes)
    elif ext == "csv":
        text, pages = extract_text_from_csv(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: .{ext}")

    # Skip quality check for tabular files (often mostly numeric)
    if ext not in ("xlsx", "csv") and not text_quality_ok(text):
        raise ValueError(
            "The extracted text appears to be of low quality (possibly a scanned PDF). "
            "Please upload a text-based document."
        )

    return text, pages


# ---------------------------------------------------------------------------
# Text Quality & Cleaning
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Remove SVG artifacts and normalize whitespace."""
    text = remove_svg_artifacts(text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_svg_artifacts(text: str) -> str:
    """Remove SVG/XML-like artifacts from extracted text."""
    text = re.sub(r"<svg[^>]*>.*?</svg>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def text_quality_ok(text: str, min_alpha_ratio: float = 0.3, min_length: int = 50) -> bool:
    """Check if extracted text has acceptable quality."""
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

def summarize_document(text: str, region: Optional[str] = None) -> str:
    """
    Summarize a large document using Bedrock Claude.
    Returns a comprehensive summary preserving key facts and structure.
    """
    import os
    import json

    region = region or os.getenv("AWS_REGION", "us-east-1")
    bedrock_runtime = boto3.client("bedrock-runtime", region_name=region)

    # Truncate input to ~200K chars to stay within model limits
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
        # Fallback: return truncated beginning
        fallback_len = SESSION_ATTR_MAX_CHARS - 500
        return text[:fallback_len] + "\n\n[... truncated, summarization unavailable ...]"


# ---------------------------------------------------------------------------
# Smart Context Strategy
# ---------------------------------------------------------------------------

def prepare_document_context(extracted_text: str, file_ext: str = "") -> tuple[str, str]:
    """
    Decide whether to use full text, a summary, or chunk-only mode based on size and file type.
    Returns (context_text, context_mode) where context_mode is "full", "summary", or "chunks_only".
    
    For tabular files (xlsx, csv), summarization is skipped — we rely on
    targeted chunk retrieval at query time to preserve exact data values.
    """
    is_tabular = file_ext in ("xlsx", "csv")

    if is_tabular:
        # For tables: if small enough, send full text; otherwise use chunk-only mode
        if len(extracted_text) <= SESSION_ATTR_MAX_CHARS:
            return extracted_text, "full"
        else:
            # Store a brief note as context; actual data comes from chunk retrieval
            note = (
                f"[Large tabular document — {len(extracted_text):,} characters. "
                f"Relevant rows will be retrieved based on each question.]"
            )
            return note, "chunks_only"

    # Non-tabular documents: existing logic
    if len(extracted_text) < CHAR_THRESHOLD:
        if len(extracted_text) <= SESSION_ATTR_MAX_CHARS:
            return extracted_text, "full"
        else:
            summary = summarize_document(extracted_text)
            return summary, "summary"
    else:
        summary = summarize_document(extracted_text)
        return summary, "summary"


# ---------------------------------------------------------------------------
# Targeted Chunk Retrieval (for large documents)
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    step = chunk_size - 200  # 200-char overlap
    for i in range(0, len(text), step):
        chunk = text[i:i + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def chunk_tabular_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """
    Split tabular text into chunks that always include the header row(s).
    
    Handles multi-sheet Excel files (sections starting with '--- Sheet: ...') by
    prepending the relevant sheet header + column header to each chunk.
    """
    lines = text.split("\n")
    if not lines:
        return []

    chunks = []
    current_sheet_header = ""
    current_col_header = ""
    current_chunk_lines: list[str] = []
    current_size = 0

    for line in lines:
        # Detect sheet separator (e.g. "--- Sheet: Sales ---")
        if line.startswith("--- Sheet:"):
            # Flush current chunk if any
            if current_chunk_lines:
                chunks.append(_build_table_chunk(current_sheet_header, current_col_header, current_chunk_lines))
                current_chunk_lines = []
                current_size = 0
            current_sheet_header = line
            current_col_header = ""  # Reset — next data line becomes the header
            continue

        # First data line after a sheet header (or at start) is the column header
        if not current_col_header:
            current_col_header = line
            continue

        # Check if adding this line would exceed chunk size
        line_len = len(line) + 1  # +1 for newline
        header_overhead = len(current_sheet_header) + len(current_col_header) + 4
        if current_size + line_len > (chunk_size - header_overhead) and current_chunk_lines:
            chunks.append(_build_table_chunk(current_sheet_header, current_col_header, current_chunk_lines))
            current_chunk_lines = []
            current_size = 0

        current_chunk_lines.append(line)
        current_size += line_len

    # Flush remaining
    if current_chunk_lines:
        chunks.append(_build_table_chunk(current_sheet_header, current_col_header, current_chunk_lines))

    return chunks


def _build_table_chunk(sheet_header: str, col_header: str, data_lines: list[str]) -> str:
    """Assemble a table chunk with its header context."""
    parts = []
    if sheet_header:
        parts.append(sheet_header)
    if col_header:
        parts.append(col_header)
    parts.extend(data_lines)
    return "\n".join(parts)


def find_relevant_chunks(full_text: str, query: str, top_k: int = 3, is_tabular: bool = False) -> str:
    """
    Simple keyword-based chunk retrieval.
    Returns the top matching chunks concatenated.
    
    For tabular data, uses header-aware chunking so each chunk includes
    column headers for context.
    """
    if is_tabular:
        chunks = chunk_tabular_text(full_text)
    else:
        chunks = chunk_text(full_text)

    if not chunks:
        return ""

    # Extract keywords from query (words > 3 chars)
    keywords = [w.lower() for w in re.split(r"\W+", query) if len(w) > 3]
    if not keywords:
        # For tabular data with no good keywords, return the first chunks (headers + start of data)
        if is_tabular and chunks:
            result = "\n\n---\n\n".join(chunks[:top_k])
            if len(result) > SESSION_ATTR_MAX_CHARS:
                result = result[:SESSION_ATTR_MAX_CHARS]
            return result
        return ""

    # Score each chunk by keyword occurrence
    scored = []
    for chunk in chunks:
        chunk_lower = chunk.lower()
        score = sum(chunk_lower.count(kw) for kw in keywords)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_chunks = [chunk for _, chunk in scored[:top_k]]

    # If no keyword matches for tabular, fall back to first chunks
    if not top_chunks and is_tabular:
        top_chunks = chunks[:top_k]

    result = "\n\n---\n\n".join(top_chunks)
    # Ensure it fits in session attributes
    if len(result) > SESSION_ATTR_MAX_CHARS:
        result = result[:SESSION_ATTR_MAX_CHARS]
    return result
