"""Tests for the document upload endpoint."""

import io

import pytest
from unittest.mock import patch


@pytest.mark.asyncio
async def test_upload_single_pdf(client):
    """Upload a single PDF-like file and get processed result."""
    processed = {
        "text_docs": [
            {
                "name": "test.pdf",
                "full_text": "Hello world",
                "page_count": 1,
                "context": "Hello world",
                "context_mode": "full",
            }
        ],
        "code_interpreter_docs": [],
        "errors": [],
    }

    with patch("jouleverne.routes.documents.process_multiple_documents", return_value=processed):
        response = await client.post(
            "/v1/documents/upload",
            files=[("files", ("test.pdf", b"fake pdf content", "application/pdf"))],
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["text_docs"]) == 1
    assert data["text_docs"][0]["name"] == "test.pdf"
    assert data["text_docs"][0]["context_mode"] == "full"
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_upload_unsupported_file_type(client):
    """Unsupported file types should be reported as errors."""
    response = await client.post(
        "/v1/documents/upload",
        files=[("files", ("image.png", b"fake png", "image/png"))],
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["errors"]) == 1
    assert "Unsupported" in data["errors"][0]["error"]
    assert data["text_docs"] == []


@pytest.mark.asyncio
async def test_upload_too_many_files(client):
    """More than 5 files should return 400."""
    files = [
        ("files", (f"doc{i}.txt", b"content", "text/plain"))
        for i in range(6)
    ]

    response = await client.post("/v1/documents/upload", files=files)
    assert response.status_code == 400
    assert "Maximum" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_file_too_large(client):
    """Files exceeding 10 MB should be reported as errors."""
    large_content = b"x" * (11 * 1024 * 1024)  # 11 MB

    with patch("jouleverne.routes.documents.process_multiple_documents") as mock_proc:
        mock_proc.return_value = {"text_docs": [], "code_interpreter_docs": [], "errors": []}

        response = await client.post(
            "/v1/documents/upload",
            files=[("files", ("big.txt", large_content, "text/plain"))],
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["errors"]) == 1
    assert "10 MB" in data["errors"][0]["error"]


@pytest.mark.asyncio
async def test_upload_multiple_files(client):
    """Multiple valid files should all be processed."""
    processed = {
        "text_docs": [
            {"name": "a.txt", "full_text": "A", "page_count": 1, "context": "A", "context_mode": "full"},
            {"name": "b.txt", "full_text": "B", "page_count": 1, "context": "B", "context_mode": "full"},
        ],
        "code_interpreter_docs": [],
        "errors": [],
    }

    with patch("jouleverne.routes.documents.process_multiple_documents", return_value=processed):
        response = await client.post(
            "/v1/documents/upload",
            files=[
                ("files", ("a.txt", b"content A", "text/plain")),
                ("files", ("b.txt", b"content B", "text/plain")),
            ],
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["text_docs"]) == 2


@pytest.mark.asyncio
async def test_upload_xlsx_routed_to_code_interpreter(client):
    """Large XLSX files should appear in code_interpreter_docs."""
    processed = {
        "text_docs": [],
        "code_interpreter_docs": [
            {"name": "data.xlsx", "bytes": b"...", "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
        ],
        "errors": [],
    }

    with patch("jouleverne.routes.documents.process_multiple_documents", return_value=processed):
        response = await client.post(
            "/v1/documents/upload",
            files=[("files", ("data.xlsx", b"fake xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))],
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["code_interpreter_docs"]) == 1
    assert data["code_interpreter_docs"][0]["name"] == "data.xlsx"
