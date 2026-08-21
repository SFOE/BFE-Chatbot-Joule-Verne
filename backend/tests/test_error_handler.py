"""Tests for the error handler decorator."""

import pytest
from unittest.mock import patch
from fastapi import HTTPException

from jouleverne.services.error_handler import handle_errors


class TestHandleErrors:
    @pytest.mark.asyncio
    async def test_passes_through_on_success(self):
        @handle_errors
        async def good_handler():
            return {"result": "ok"}

        result = await good_handler()
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_reraises_http_exception(self):
        @handle_errors
        async def handler_with_http_error():
            raise HTTPException(status_code=404, detail="Not found")

        with pytest.raises(HTTPException) as exc_info:
            await handler_with_http_error()
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_reraises_in_dev_mode(self):
        @handle_errors
        async def broken_handler():
            raise ValueError("something broke")

        with patch("jouleverne.services.error_handler.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "DEV"
            with pytest.raises(ValueError, match="something broke"):
                await broken_handler()

    @pytest.mark.asyncio
    async def test_returns_500_in_prod_mode(self):
        @handle_errors
        async def broken_handler():
            raise RuntimeError("internal failure")

        with patch("jouleverne.services.error_handler.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "production"
            with pytest.raises(HTTPException) as exc_info:
                await broken_handler()
            assert exc_info.value.status_code == 500
            assert "internal failure" in exc_info.value.detail
