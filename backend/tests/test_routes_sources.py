"""Tests for the sources endpoint."""

import json

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_download_url_valid_uri(client):
    """GET /v1/sources/download should return a presigned URL."""
    with patch("jouleverne.routes.sources.s3_client") as mock_s3:
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/presigned"

        response = await client.get(
            "/v1/sources/download",
            params={"uri": "s3://my-bucket/path/to/file.pdf"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://s3.example.com/presigned"
    assert data["filename"] == "file.pdf"


@pytest.mark.asyncio
async def test_download_url_invalid_uri(client):
    """Invalid S3 URI should return 400."""
    response = await client.get(
        "/v1/sources/download",
        params={"uri": "https://not-s3.com/file.pdf"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_download_url_missing_param(client):
    """Missing uri parameter should return 422."""
    response = await client.get("/v1/sources/download")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_metadata_website_source(client):
    """Website bucket sources should return source_url from S3 metadata."""
    with patch("jouleverne.routes.sources.s3_client") as mock_s3, \
         patch("jouleverne.routes.sources.settings") as mock_settings:
        mock_settings.WEBSITE_BUCKET = "website-bucket"
        mock_settings.FEDLEX_BUCKET = "fedlex-bucket"
        mock_settings.RATE_LIMIT = "100/minute"

        mock_s3.head_object.return_value = {
            "Metadata": {"source_url": "https://www.bfe.admin.ch/page"}
        }

        response = await client.get(
            "/v1/sources/metadata",
            params={"uri": "s3://website-bucket/content.txt"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "website"
    assert data["source_url"] == "https://www.bfe.admin.ch/page"


@pytest.mark.asyncio
async def test_metadata_fedlex_source(client):
    """Fedlex bucket sources should return title and URL from sidecar JSON."""
    metadata_json = {
        "metadataAttributes": {
            "fedlex_url": {"value": {"stringValue": "https://fedlex.admin.ch/law/123"}},
            "title": {"value": {"stringValue": "Energiegesetz"}},
            "abbreviation": {"value": {"stringValue": "EnG"}},
        }
    }

    with patch("jouleverne.routes.sources.s3_client") as mock_s3, \
         patch("jouleverne.routes.sources.settings") as mock_settings:
        mock_settings.WEBSITE_BUCKET = "website-bucket"
        mock_settings.FEDLEX_BUCKET = "fedlex-bucket"
        mock_settings.RATE_LIMIT = "100/minute"

        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(metadata_json).encode()
        mock_s3.get_object.return_value = {"Body": mock_body}

        response = await client.get(
            "/v1/sources/metadata",
            params={"uri": "s3://fedlex-bucket/law.txt"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "fedlex"
    assert data["fedlex_url"] == "https://fedlex.admin.ch/law/123"
    assert data["title"] == "Energiegesetz"
    assert data["abbreviation"] == "EnG"


@pytest.mark.asyncio
async def test_metadata_document_source(client):
    """Other bucket sources should return type 'document'."""
    with patch("jouleverne.routes.sources.settings") as mock_settings:
        mock_settings.WEBSITE_BUCKET = "website-bucket"
        mock_settings.FEDLEX_BUCKET = "fedlex-bucket"
        mock_settings.RATE_LIMIT = "100/minute"

        response = await client.get(
            "/v1/sources/metadata",
            params={"uri": "s3://other-bucket/doc.pdf"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "document"


@pytest.mark.asyncio
async def test_metadata_specific_kb_website_subprefix(client):
    """Specific-KB objects under a 'website/' sub-prefix resolve like website
    sources: type 'website' with the source_url from S3 metadata."""
    with patch("jouleverne.routes.sources.s3_client") as mock_s3, \
         patch("jouleverne.routes.sources.settings") as mock_settings:
        mock_settings.WEBSITE_BUCKET = "website-bucket"
        mock_settings.FEDLEX_BUCKET = "fedlex-bucket"
        mock_settings.EXTRACTED_BUCKET = "extracted-bucket"
        mock_settings.SPECIFIC_KBS_BUCKET = "specific-kbs-bucket"
        mock_settings.RATE_LIMIT = "100/minute"

        mock_s3.head_object.return_value = {
            "Metadata": {"source_url": "https://www.dasgebaeudeprogramm.ch/page"}
        }

        response = await client.get(
            "/v1/sources/metadata",
            params={"uri": "s3://specific-kbs-bucket/gebaeude/website/page.txt"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "website"
    assert data["source_url"] == "https://www.dasgebaeudeprogramm.ch/page"


@pytest.mark.asyncio
async def test_metadata_specific_kb_uploaded_file(client):
    """Specific-KB objects NOT under 'website/' resolve as raw downloads
    with type 'specific'."""
    with patch("jouleverne.routes.sources.s3_client") as mock_s3, \
         patch("jouleverne.routes.sources.settings") as mock_settings:
        mock_settings.WEBSITE_BUCKET = "website-bucket"
        mock_settings.FEDLEX_BUCKET = "fedlex-bucket"
        mock_settings.EXTRACTED_BUCKET = "extracted-bucket"
        mock_settings.SPECIFIC_KBS_BUCKET = "specific-kbs-bucket"
        mock_settings.RATE_LIMIT = "100/minute"

        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/presigned"

        response = await client.get(
            "/v1/sources/metadata",
            params={"uri": "s3://specific-kbs-bucket/gebaeude/report.pdf"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "specific"
    assert data["download_url"] == "https://s3.example.com/presigned"
