"""Tests for security middleware (Cognito auth)."""

import base64
import json

import pytest
from unittest.mock import patch
from fastapi import Request

from jouleverne.services.security import _extract_cognito_groups, verify_cognito_auth


def _make_fake_token(groups: list[str]) -> str:
    """Create a fake JWT-shaped token with cognito:groups in the payload."""
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    payload_data = {"cognito:groups": groups, "sub": "user-123"}
    payload = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).rstrip(b"=").decode()
    signature = "fakesig"
    return f"{header}.{payload}.{signature}"


def _mock_request(headers: dict | None = None) -> Request:
    """Create a minimal ASGI request with given headers."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    return Request(scope)


class TestExtractCognitoGroups:
    def test_no_header_returns_empty(self):
        request = _mock_request()
        assert _extract_cognito_groups(request) == set()

    def test_valid_token_extracts_groups(self):
        token = _make_fake_token(["admin", "users"])
        request = _mock_request({"x-amzn-oidc-accesstoken": token})
        groups = _extract_cognito_groups(request)
        assert groups == {"admin", "users"}

    def test_invalid_token_returns_empty(self):
        request = _mock_request({"x-amzn-oidc-accesstoken": "not.a.valid.token"})
        groups = _extract_cognito_groups(request)
        assert groups == set()

    def test_empty_groups_claim(self):
        token = _make_fake_token([])
        request = _mock_request({"x-amzn-oidc-accesstoken": token})
        groups = _extract_cognito_groups(request)
        assert groups == set()


class TestVerifyCognitoAuth:
    @pytest.mark.asyncio
    async def test_open_access_when_no_groups_configured(self):
        """When ALLOWED_COGNITO_GROUPS is empty, auth is skipped."""
        request = _mock_request()
        with patch("jouleverne.services.security._allowed_groups", set()):
            # Should not raise
            await verify_cognito_auth(request)

    @pytest.mark.asyncio
    async def test_denies_access_without_matching_group(self):
        request = _mock_request()
        with patch("jouleverne.services.security._allowed_groups", {"admin"}):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await verify_cognito_auth(request)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_allows_access_with_matching_group(self):
        token = _make_fake_token(["admin", "readers"])
        request = _mock_request({"x-amzn-oidc-accesstoken": token})
        with patch("jouleverne.services.security._allowed_groups", {"admin"}):
            # Should not raise
            await verify_cognito_auth(request)
