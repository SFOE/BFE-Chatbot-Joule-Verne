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


def _specific_kb_settings(mock_settings):
    """Common bucket wiring for specific-KB source tests."""
    mock_settings.WEBSITE_BUCKET = "website-bucket"
    mock_settings.FEDLEX_BUCKET = "fedlex-bucket"
    mock_settings.EXTRACTED_BUCKET = "extracted-bucket"
    mock_settings.SPECIFIC_KBS_BUCKET = "specific-kbs-bucket"
    mock_settings.SPECIFIC_KBS_EXTRACTED_BUCKET = "specific-kbs-extracted-bucket"
    mock_settings.RATE_LIMIT = "100/minute"


@pytest.mark.asyncio
async def test_metadata_extracted_website_subprefix(client):
    """Extracted-bucket objects under a 'website/' sub-prefix resolve like
    website sources: type 'website' with source_url from S3 metadata."""
    with patch("jouleverne.routes.sources.s3_client") as mock_s3, \
         patch("jouleverne.routes.sources.settings") as mock_settings:
        _specific_kb_settings(mock_settings)

        mock_s3.head_object.return_value = {
            "Metadata": {"source_url": "https://www.dasgebaeudeprogramm.ch/page"}
        }

        response = await client.get(
            "/v1/sources/metadata",
            params={"uri": "s3://specific-kbs-extracted-bucket/gebaeudeprogramm/website/page.txt"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "website"
    assert data["source_url"] == "https://www.dasgebaeudeprogramm.ch/page"


@pytest.mark.asyncio
async def test_metadata_extracted_maps_to_original_via_sidecar(client):
    """An extracted .txt resolves to the ORIGINAL file in the inbox bucket via
    the sidecar's original_key: type 'specific', download of the original."""
    sidecar = {"metadataAttributes": {"original_key": "gebaeudeprogramm/report.pdf"}}

    with patch("jouleverne.routes.sources.s3_client") as mock_s3, \
         patch("jouleverne.routes.sources.settings") as mock_settings:
        _specific_kb_settings(mock_settings)

        body = MagicMock()
        body.read.return_value = json.dumps(sidecar).encode()
        mock_s3.get_object.return_value = {"Body": body}
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/original.pdf"

        response = await client.get(
            "/v1/sources/metadata",
            params={"uri": "s3://specific-kbs-extracted-bucket/gebaeudeprogramm/report.txt"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "specific"
    assert data["download_url"] == "https://s3.example.com/original.pdf"
    # The sidebar cites the ORIGINAL filename, not the extracted .txt.
    assert data["filename"] == "report.pdf"
    # The presigned download targets the inbox bucket + the original key.
    _, kwargs = mock_s3.generate_presigned_url.call_args
    assert kwargs["Params"]["Bucket"] == "specific-kbs-bucket"
    assert kwargs["Params"]["Key"] == "gebaeudeprogramm/report.pdf"


@pytest.mark.asyncio
async def test_metadata_extracted_part_file_maps_to_original(client):
    """A split _partN.txt maps back to the same original via its own sidecar."""
    sidecar = {"metadataAttributes": {"original_key": "medienarchiv/big report.docx"}}

    with patch("jouleverne.routes.sources.s3_client") as mock_s3, \
         patch("jouleverne.routes.sources.settings") as mock_settings:
        _specific_kb_settings(mock_settings)

        body = MagicMock()
        body.read.return_value = json.dumps(sidecar).encode()
        mock_s3.get_object.return_value = {"Body": body}
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/original.docx"

        response = await client.get(
            "/v1/sources/metadata",
            params={"uri": "s3://specific-kbs-extracted-bucket/medienarchiv/big report_part2.txt"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "specific"
    assert data["filename"] == "big report.docx"
    _, kwargs = mock_s3.generate_presigned_url.call_args
    assert kwargs["Params"]["Key"] == "medienarchiv/big report.docx"


@pytest.mark.asyncio
async def test_metadata_extracted_no_sidecar_falls_back_to_extracted(client):
    """If no sidecar and no matching inbox original exists, fall back to a
    presigned download of the extracted object itself (type 'specific')."""
    with patch("jouleverne.routes.sources.s3_client") as mock_s3, \
         patch("jouleverne.routes.sources.settings") as mock_settings:
        _specific_kb_settings(mock_settings)

        # No sidecar, and no inbox original matches.
        mock_s3.get_object.side_effect = Exception("no sidecar")
        mock_s3.head_object.side_effect = Exception("not found")
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/extracted.txt"

        response = await client.get(
            "/v1/sources/metadata",
            params={"uri": "s3://specific-kbs-extracted-bucket/interne-weisungen/orphan.txt"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "specific"
    assert data["download_url"] == "https://s3.example.com/extracted.txt"


@pytest.mark.asyncio
async def test_metadata_inbox_direct_reference_still_downloads(client):
    """A citation that still points directly at the inbox bucket resolves to a
    raw download (legacy path)."""
    with patch("jouleverne.routes.sources.s3_client") as mock_s3, \
         patch("jouleverne.routes.sources.settings") as mock_settings:
        _specific_kb_settings(mock_settings)

        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/inbox.pdf"

        response = await client.get(
            "/v1/sources/metadata",
            params={"uri": "s3://specific-kbs-bucket/gebaeudeprogramm/report.pdf"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "specific"
    assert data["download_url"] == "https://s3.example.com/inbox.pdf"
