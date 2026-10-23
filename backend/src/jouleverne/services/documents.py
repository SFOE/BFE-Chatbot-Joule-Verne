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
import zipfile
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
MAX_UPLOAD_FILES = 50
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = {"pdf", "txt", "docx", "xlsx", "csv"}
MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# ---------------------------------------------------------------------------
# Sensitivity / Classification
# ---------------------------------------------------------------------------

# Sensitivity labels that are NOT allowed (empty = no MIP labels blocked)
RESTRICTED_SENSITIVITY_LABELS: set[str] = set()

# Classification keywords to search for in document headers/footers/text
# These are common classifications used in the Swiss federal administration
RESTRICTED_CLASSIFICATION_KEYWORDS = {
    "GEHEIM",
    "VERTRAULICH",
}


def check_sensitivity_label(file_bytes: bytes, filename: str) -> dict | None:
    """Check if a file contains a Microsoft Information Protection (MIP) sensitivity label.

    Supports:
    - PDF: reads raw bytes for MSIP_Label markers
    - DOCX/XLSX: reads custom XML parts inside the ZIP archive

    Returns a dict with label info if found, e.g.:
        {"name": "L3", "guid": "...", "enabled": True}
    Returns None if no label is detected.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        return _check_sensitivity_label_pdf(file_bytes)
    elif ext in ("docx", "xlsx"):
        return _check_sensitivity_label_ooxml(file_bytes)
    else:
        return None


def _check_sensitivity_label_pdf(file_bytes: bytes) -> dict | None:
    """Extract MSIP label from PDF metadata."""
    match = re.search(
        rb"MSIP_Label_([0-9a-f\-]+)_Name[>\s/\(]+([A-Za-z0-9_\- ]+)",
        file_bytes,
    )
    if match:
        guid = match.group(1).decode("utf-8", errors="ignore")
        label_name = match.group(2).decode("utf-8", errors="ignore").strip().rstrip(")")
        return {"name": label_name, "guid": guid, "enabled": True}

    # Fallback: check XMP/pdfx namespace
    match = re.search(
        rb"MSIP_Label_([0-9a-f\-]+)_Name>([^<]+)<",
        file_bytes,
    )
    if match:
        guid = match.group(1).decode("utf-8", errors="ignore")
        label_name = match.group(2).decode("utf-8", errors="ignore").strip()
        return {"name": label_name, "guid": guid, "enabled": True}

    return None


def _check_sensitivity_label_ooxml(file_bytes: bytes) -> dict | None:
    """Extract MSIP label from Office Open XML (docx, xlsx) custom XML parts."""
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as zf:
            for entry in zf.namelist():
                if "customXml/item" in entry or "docProps/custom" in entry:
                    try:
                        content = zf.read(entry).decode("utf-8", errors="ignore")
                    except Exception:
                        continue
                    if "MSIP_Label" not in content:
                        continue
                    match = re.search(
                        r"MSIP_Label_([0-9a-f\-]+)_Name[^>]*>([^<]+)<",
                        content,
                    )
                    if match:
                        guid = match.group(1)
                        label_name = match.group(2).strip()
                        return {"name": label_name, "guid": guid, "enabled": True}
                    # Alternative: property with fmtid (custom.xml style)
                    match = re.search(
                        r'name="MSIP_Label_([0-9a-f\-]+)_Name"[^>]*>.*?<vt:lpwstr>([^<]+)',
                        content,
                        re.DOTALL,
                    )
                    if match:
                        guid = match.group(1)
                        label_name = match.group(2).strip()
                        return {"name": label_name, "guid": guid, "enabled": True}
    except zipfile.BadZipFile:
        logger.debug("File is not a valid ZIP/OOXML archive: check skipped")
    except Exception as e:
        logger.debug("Error checking sensitivity label in OOXML: %s", e)

    return None


def is_sensitivity_restricted(label_info: dict | None) -> bool:
    """Return True if the label indicates a restricted classification (L3+)."""
    if label_info is None:
        return False
    return label_info.get("name", "").upper() in {label.upper() for label in RESTRICTED_SENSITIVITY_LABELS}


def check_classification_in_text(file_bytes: bytes, filename: str) -> str | None:
    """Check if a document contains classification keywords (e.g. GEHEIM, VERTRAULICH)
    in headers, footers, or the first/last lines of the document text.

    Returns the found keyword or None.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        return _check_classification_text_pdf(file_bytes)
    elif ext == "docx":
        return _check_classification_text_docx(file_bytes)
    elif ext == "xlsx":
        return None
    else:
        return None


def _check_classification_text_pdf(file_bytes: bytes) -> str | None:
    """Check first and last page of a PDF for classification keywords."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages_to_check = []
        if reader.pages:
            pages_to_check.append(reader.pages[0])
        if len(reader.pages) > 1:
            pages_to_check.append(reader.pages[-1])

        for page in pages_to_check:
            text = (page.extract_text() or "").upper()
            header_area = text[:500]
            footer_area = text[-500:] if len(text) > 500 else text
            for keyword in RESTRICTED_CLASSIFICATION_KEYWORDS:
                if keyword in header_area or keyword in footer_area:
                    return keyword
    except Exception as e:
        logger.debug("Error checking classification text in PDF: %s", e)
    return None


def _check_classification_text_docx(file_bytes: bytes) -> str | None:
    """Check headers, footers, and first paragraphs of a DOCX for classification keywords."""
    try:
        doc = DocxDocument(io.BytesIO(file_bytes))

        for section in doc.sections:
            for header in (section.header, section.first_page_header):
                for para in header.paragraphs:
                    text_upper = para.text.strip().upper()
                    for keyword in RESTRICTED_CLASSIFICATION_KEYWORDS:
                        if keyword in text_upper:
                            return keyword
            for footer in (section.footer, section.first_page_footer):
                for para in footer.paragraphs:
                    text_upper = para.text.strip().upper()
                    for keyword in RESTRICTED_CLASSIFICATION_KEYWORDS:
                        if keyword in text_upper:
                            return keyword

        for para in doc.paragraphs[:5]:
            text_upper = para.text.strip().upper()
            for keyword in RESTRICTED_CLASSIFICATION_KEYWORDS:
                if keyword in text_upper:
                    return keyword

    except Exception as e:
        logger.debug("Error checking classification text in DOCX: %s", e)
    return None


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
    sheet_count = len(wb.sheetnames)
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
    return _clean_text("\n\n".join(sheets_text)), sheet_count


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

# ---------------------------------------------------------------------------
# Prompt budget
# ---------------------------------------------------------------------------
# Rough budget for the total inline text we are willing to put into a single
# prompt. 1 token ≈ 4 characters, so ~45K chars ≈ ~11K tokens of uploaded
# document text, leaving generous headroom for the system prompt, the chat
# history, retrieved KB passages and the model's own output within a typical
# context window. This is deliberately conservative; large documents have a
# proper home (the per-session index) when indexing is enabled.
PROMPT_CHAR_BUDGET = 45_000


def estimate_prompt_size(
    messages: list[dict] | None = None,
    session_attributes: dict | None = None,
) -> int:
    """Estimate how many characters of uploaded-document text are already in play.

    Counts the text we actually inline into the prompt: the running chat
    history plus any uploaded-document payload carried in ``session_attributes``.
    Used to decide whether a newly uploaded document still fits inline.
    """
    total = 0
    for msg in messages or []:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    total += len(item["text"])
    if session_attributes:
        total += len(session_attributes.get("uploaded_document", ""))
    return total


def prepare_document_context(
    extracted_text: str,
    file_ext: str = "",
    summarize_large: bool = True,
    current_prompt_size: int = 0,
    can_index: bool = False,
) -> tuple[str, str]:
    """Decide how a single document is carried into the prompt.

    Returns ``(context_text, context_mode)`` where ``context_mode`` is one of:

    - ``"full"``        — the whole extracted text is inlined.
    - ``"code_interpreter"`` — a large tabular file handled by Code Interpreter.
    - ``"summary"``     — the document is NOT inlined. Its content lives in the
      per-session index (when ``can_index`` is True) or, as a fallback when no
      index is available, in a generated summary.

    A document is pushed to ``"summary"`` when it is individually larger than
    ``SESSION_ATTR_MAX_CHARS`` OR when inlining it would push the running prompt
    past ``PROMPT_CHAR_BUDGET``.

    The critical invariant: an empty ``context`` is only ever returned when the
    caller can actually index the document (``can_index``). When no index is
    available we never drop content — we either keep it inline or fall back to a
    generated summary — so the agent always has something to work with.
    """
    is_tabular = file_ext in ("xlsx", "csv")

    if is_tabular:
        if len(extracted_text) <= SESSION_ATTR_MAX_CHARS:
            return extracted_text, "full"
        return (
            f"[Large tabular document — {len(extracted_text):,} characters. "
            f"File will be sent to Code Interpreter for analysis.]"
        ), "code_interpreter"

    fits_inline_size = len(extracted_text) <= SESSION_ATTR_MAX_CHARS
    fits_budget = current_prompt_size + len(extracted_text) <= PROMPT_CHAR_BUDGET

    if fits_inline_size and fits_budget:
        return extracted_text, "full"

    # The document will not be inlined. Decide where its content actually lives.
    if can_index:
        # The caller indexes "summary" docs with empty context; content is safe
        # in the per-session index.
        return "", "summary"
    if summarize_large:
        # No index available — never drop the content. Summarize so the agent
        # still gets a condensed version inline.
        return summarize_document(extracted_text), "summary"
    # No index and summarization disabled: inlining the full text is the only
    # way to preserve the content, so keep it inline despite the budget.
    return extracted_text, "full"


# ---------------------------------------------------------------------------
# Multi-Document Processing
# ---------------------------------------------------------------------------

def process_multiple_documents(
    files_data: list[dict],
    summarize_large: bool = True,
    messages: list[dict] | None = None,
    session_attributes: dict | None = None,
    can_index: bool = False,
) -> dict:
    """Process uploaded documents and categorize by handling strategy.

    Args:
        files_data: List of dicts with 'name' and 'bytes' keys.
        summarize_large: When True, a large text document that is NOT going to
            be indexed is summarized for inline context (legacy fallback). When
            False, such a document is kept inline as a last resort so its
            content is never dropped.
        messages: Optional chat history, counted towards the inline prompt
            budget so uploads on top of a long chat still fit.
        session_attributes: Optional existing session attributes (e.g. a prior
            ``uploaded_document``) counted towards the inline prompt budget.
        can_index: Whether the caller will index "summary" documents
            server-side. Only when True may a document be emitted with an empty
            ``context`` (its content then lives in the per-session index); when
            False the content is always preserved inline or as a summary.

    Returns:
        Dict with 'text_docs', 'code_interpreter_docs', and 'errors' lists.
        Documents are processed largest-first so a few big files cannot starve
        several small ones out of the inline budget.
    """
    result = {
        "text_docs": [],
        "code_interpreter_docs": [],
        "errors": [],
    }

    # Running total of inline text already committed to the prompt: the existing
    # chat history / session attributes, plus each document we inline below.
    current_prompt_size = estimate_prompt_size(messages, session_attributes)

    # Process largest files first so a couple of big documents can't consume the
    # whole inline budget and push several small ones into the index/summary
    # path. Ordering is by raw upload size (a cheap proxy for text length).
    ordered_files = sorted(files_data, key=lambda f: len(f.get("bytes", b"")), reverse=True)

    for file_info in ordered_files:
        name = file_info["name"]
        file_bytes = file_info["bytes"]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

        # --- Sensitivity check BEFORE processing ---
        label_info = check_sensitivity_label(file_bytes, name)
        if is_sensitivity_restricted(label_info):
            label_name = label_info.get("name", "unknown")
            result["errors"].append({
                "name": name,
                "error": f"sensitivity_label_blocked:{label_name}",
                "sensitivity_blocked": True,
            })
            continue

        # Fallback: check for classification keywords in document text
        classification_keyword = check_classification_in_text(file_bytes, name)
        if classification_keyword:
            result["errors"].append({
                "name": name,
                "error": f"sensitivity_keyword_blocked:{classification_keyword}",
                "sensitivity_blocked": True,
            })
            continue

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
            doc_context, context_mode = prepare_document_context(
                extracted_text,
                file_ext=ext,
                summarize_large=summarize_large,
                current_prompt_size=current_prompt_size,
                can_index=can_index,
            )
            # Only inlined text (full/summarized) counts against the budget;
            # indexed docs carry an empty context and cost nothing here.
            current_prompt_size += len(doc_context)
            result["text_docs"].append({
                "name": name,
                "full_text": extracted_text,
                "page_count": page_count,
                "context": doc_context,
                "context_mode": context_mode,
            })

    return result


# ---------------------------------------------------------------------------
# Indexed-document summary (agent awareness)
# ---------------------------------------------------------------------------
# Number of leading characters of a document's text used as a preview in the
# agent-facing summary. Enough to identify the document's subject without
# bloating the prompt.
INDEXED_SUMMARY_PREVIEW_CHARS = 200


def _document_preview(text: str, limit: int = INDEXED_SUMMARY_PREVIEW_CHARS) -> str:
    """Collapse whitespace and take the first ``limit`` characters of ``text``.

    Produces a single-line preview safe to embed in the prompt. Appends an
    ellipsis when the text was longer than the limit.
    """
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit].rstrip() + "…"


def build_indexed_documents_summary(docs: list[dict]) -> str:
    """Build an agent-facing summary of documents that are indexed, not inlined.

    These are the "teilweise" (partial) documents: their full text is NOT in the
    prompt, it lives in the per-session index and is reached via the
    ``search_uploaded_documents`` tool. The agent otherwise has no visibility
    into their name, size or subject, so we surface a compact metadata block.

    ``docs`` are dicts carrying at least ``name`` and the full extracted text
    under ``full_text`` (or ``_raw_text``). One line per document:

        - <name> (<TYPE>, ~<n> chars): "<first 200 chars>"

    Returns an empty string when there are no indexed documents, so the caller
    can omit the attribute entirely.
    """
    lines: list[str] = []
    for d in docs:
        name = d.get("name", "document")
        ext = name.rsplit(".", 1)[-1].upper() if "." in name else "FILE"
        full_text = d.get("full_text") or d.get("_raw_text") or ""
        size = len(full_text)
        preview = _document_preview(full_text)
        if preview:
            lines.append(f'- {name} ({ext}, ~{size:,} chars): "{preview}"')
        else:
            lines.append(f"- {name} ({ext}, ~{size:,} chars)")

    if not lines:
        return ""

    header = (
        "The following uploaded documents are NOT included in full below; "
        "their content is indexed and searchable via the "
        "search_uploaded_documents tool. Use that tool to read them:"
    )
    return header + "\n" + "\n".join(lines)
