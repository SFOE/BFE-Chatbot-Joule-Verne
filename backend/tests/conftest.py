"""Shared test fixtures."""

import os
import pytest
from unittest.mock import patch, MagicMock

# Set required env vars BEFORE importing anything from jouleverne
os.environ.setdefault("AGENTCORE_RUNTIME_ARN", "arn:aws:bedrock:eu-central-1:123456789:agent-runtime/test-runtime")
os.environ.setdefault("AGENTCORE_ENDPOINT_ARN", "")
os.environ.setdefault("FEEDBACK_BUCKET", "test-feedback")
os.environ.setdefault("PDF_BUCKET", "test-pdf")
os.environ.setdefault("EXTRACTED_BUCKET", "test-extracted")
os.environ.setdefault("WEBSITE_BUCKET", "test-website")
os.environ.setdefault("FEDLEX_BUCKET", "test-fedlex")
os.environ.setdefault("ENVIRONMENT", "DEV")

# Mock boto3 before it's imported by clients.py
_mock_boto3 = patch("boto3.client", return_value=MagicMock())
_mock_boto3.start()

from httpx import AsyncClient, ASGITransport  # noqa: E402
from jouleverne.app import app  # noqa: E402


@pytest.fixture
def client():
    """Async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")
