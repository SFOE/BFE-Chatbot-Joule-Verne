"""Tests for the document upload endpoint."""

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
            data={"session_id": "s1"},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["text_docs"]) == 1
    assert data["text_docs"][0]["name"] == "test.pdf"
    assert data["text_docs"][0]["context_mode"] == "full"
    assert data["errors"] == []
    assert data["indexed_docs"] == []


@pytest.mark.asyncio
async def test_upload_unsupported_file_type(client):
    """Unsupported file types should be reported as errors."""
    response = await client.post(
        "/v1/documents/upload",
        files=[("files", ("image.png", b"fake png", "image/png"))],
        data={"session_id": "s1"},
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

    response = await client.post(
        "/v1/documents/upload", files=files, data={"session_id": "s1"}
    )
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
            data={"session_id": "s1"},
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
            data={"session_id": "s1"},
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
            data={"session_id": "s1"},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data["code_interpreter_docs"]) == 1
    assert data["code_interpreter_docs"][0]["name"] == "data.xlsx"


@pytest.mark.asyncio
async def test_upload_large_text_doc_is_indexed(client):
    """With identity + persistence, a large text doc is indexed, not inlined."""
    import base64
    import json as _json

    processed = {
        "text_docs": [
            {
                "name": "big.pdf",
                "full_text": "",
                "page_count": 50,
                "context": "",
                "context_mode": "summary",  # flagged large
            }
        ],
        "code_interpreter_docs": [],
        "errors": [],
    }

    def _oidc_header(sub: str) -> dict:
        header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(_json.dumps({"sub": sub}).encode()).rstrip(b"=").decode()
        return {"x-amzn-oidc-data": f"{header}.{payload}.sig"}

    def _fake_store(**kwargs):
        return {"file_id": "f-" + kwargs["filename"], "name": kwargs["filename"]}

    with patch("jouleverne.routes.documents.process_multiple_documents", return_value=processed), \
         patch("jouleverne.routes.documents.convo.is_persistence_configured", return_value=True), \
         patch("jouleverne.routes.documents.convo.get_save_enabled", return_value=True), \
         patch("jouleverne.routes.documents.doc_index.session_prefix", return_value="sessions/u1/s1/"), \
         patch("jouleverne.routes.documents.session_files.store_file", side_effect=_fake_store) as mock_store, \
         patch(
             "jouleverne.routes.documents.doc_index.build_index",
             return_value={"doc_id": "d1", "name": "big.pdf", "chunk_count": 7},
         ) as mock_build:
        response = await client.post(
            "/v1/documents/upload",
            files=[("files", ("big.pdf", b"fake large pdf", "application/pdf"))],
            data={"session_id": "s1"},
            headers=_oidc_header("u1"),
        )

    assert response.status_code == 200
    data = response.json()
    # Large doc moved out of inline text_docs into indexed_docs.
    assert data["text_docs"] == []
    assert len(data["indexed_docs"]) == 1
    assert data["indexed_docs"][0]["doc_id"] == "d1"
    assert data["indexed_docs"][0]["chunk_count"] == 7
    # Indexed under the resolved session prefix.
    assert mock_build.call_args.kwargs["prefix"] == "sessions/u1/s1/"
    # Original stored (A) with routing "index" + doc_id link, file_id returned.
    assert data["indexed_docs"][0]["file_id"] == "f-big.pdf"
    store_kwargs = mock_store.call_args.kwargs
    assert store_kwargs["routing"] == "index"
    assert store_kwargs["doc_id"] == "d1"


@pytest.mark.asyncio
async def test_list_indexed_documents(client):
    import base64
    import json as _json

    def _oidc_header(sub: str) -> dict:
        header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(_json.dumps({"sub": sub}).encode()).rstrip(b"=").decode()
        return {"x-amzn-oidc-data": f"{header}.{payload}.sig"}

    with patch("jouleverne.routes.documents.convo.is_persistence_configured", return_value=True), \
         patch("jouleverne.routes.documents.doc_index.session_prefix", return_value="sessions/u1/s1/"), \
         patch(
             "jouleverne.routes.documents.doc_index.list_documents",
             return_value=[{"doc_id": "d1", "name": "a.pdf", "chunk_count": 3}],
         ):
        response = await client.get(
            "/v1/documents/indexed",
            params={"session_id": "s1"},
            headers=_oidc_header("u1"),
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["doc_id"] == "d1"


@pytest.mark.asyncio
async def test_list_indexed_documents_without_identity(client):
    # No sub => empty list, never an error.
    response = await client.get("/v1/documents/indexed", params={"session_id": "s1"})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_session_files(client):
    import base64
    import json as _json

    def _oidc_header(sub: str) -> dict:
        header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(_json.dumps({"sub": sub}).encode()).rstrip(b"=").decode()
        return {"x-amzn-oidc-data": f"{header}.{payload}.sig"}

    metas = [
        {"file_id": "f1", "name": "a.csv", "media_type": "text/csv", "routing": "ci", "doc_id": None},
        {"file_id": "f2", "name": "b.pdf", "media_type": "", "routing": "index", "doc_id": "d2"},
    ]
    with patch("jouleverne.routes.documents.convo.is_persistence_configured", return_value=True), \
         patch("jouleverne.routes.documents.doc_index.session_prefix", return_value="sessions/u1/s1/"), \
         patch("jouleverne.routes.documents.session_files.list_files", return_value=metas):
        response = await client.get(
            "/v1/documents/session-files",
            params={"session_id": "s1"},
            headers=_oidc_header("u1"),
        )
    assert response.status_code == 200
    data = response.json()
    assert {d["file_id"] for d in data} == {"f1", "f2"}
    ci = next(d for d in data if d["file_id"] == "f1")
    assert ci["routing"] == "ci"
    idx = next(d for d in data if d["file_id"] == "f2")
    assert idx["doc_id"] == "d2"


@pytest.mark.asyncio
async def test_list_session_files_without_identity(client):
    response = await client.get("/v1/documents/session-files", params={"session_id": "s1"})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_delete_session_file_indexed(client):
    import base64
    import json as _json

    def _oidc_header(sub: str) -> dict:
        header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(_json.dumps({"sub": sub}).encode()).rstrip(b"=").decode()
        return {"x-amzn-oidc-data": f"{header}.{payload}.sig"}

    # File found under the persistent prefix, with a doc_id => index also deleted.
    with patch("jouleverne.routes.documents.convo.is_persistence_configured", return_value=True), \
         patch("jouleverne.routes.documents.doc_index.session_prefix", return_value="sessions/u1/s1/"), \
         patch("jouleverne.routes.documents.session_files.get_file_bytes",
               return_value=(b"x", {"file_id": "f1", "doc_id": "d1"})), \
         patch("jouleverne.routes.documents.doc_index.delete_document", return_value=True) as mock_idx_del, \
         patch("jouleverne.routes.documents.session_files.delete_file", return_value=True) as mock_file_del:
        response = await client.delete(
            "/v1/documents/f1",
            params={"session_id": "s1"},
            headers=_oidc_header("u1"),
        )
    assert response.status_code == 204
    mock_idx_del.assert_called_once_with("sessions/u1/s1/", "d1")
    mock_file_del.assert_called_once_with("sessions/u1/s1/", "f1")


@pytest.mark.asyncio
async def test_delete_session_file_tries_ephemeral_then_404(client):
    import base64
    import json as _json

    def _oidc_header(sub: str) -> dict:
        header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(_json.dumps({"sub": sub}).encode()).rstrip(b"=").decode()
        return {"x-amzn-oidc-data": f"{header}.{payload}.sig"}

    # Not found under either prefix => 404, get_file_bytes tried twice.
    with patch("jouleverne.routes.documents.convo.is_persistence_configured", return_value=True), \
         patch("jouleverne.routes.documents.doc_index.session_prefix",
               side_effect=lambda sub, sid, save_history: f"{'sessions' if save_history else 'ephemeral'}/u1/s1/"), \
         patch("jouleverne.routes.documents.session_files.get_file_bytes", return_value=None) as mock_get:
        response = await client.delete(
            "/v1/documents/ghost",
            params={"session_id": "s1"},
            headers=_oidc_header("u1"),
        )
    assert response.status_code == 404
    assert mock_get.call_count == 2


@pytest.mark.asyncio
async def test_delete_session_file_without_identity(client):
    response = await client.delete("/v1/documents/f1", params={"session_id": "s1"})
    assert response.status_code == 404
