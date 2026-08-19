"""Tests for the health check endpoint."""

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    response = await client.get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_method_not_allowed(client):
    response = await client.post("/v1/health")
    assert response.status_code == 405
