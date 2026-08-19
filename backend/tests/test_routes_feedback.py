"""Tests for the feedback endpoint."""

import pytest
from unittest.mock import patch


@pytest.mark.asyncio
async def test_feedback_saves_successfully(client):
    """POST /v1/feedback should save and return s3_key + timestamp."""
    with patch("jouleverne.routes.feedback.save_feedback") as mock_save:
        mock_save.return_value = ("feedback/2026/07/16/s1_0.json", "2026-07-16T10:00:00+00:00")

        response = await client.post(
            "/v1/feedback",
            json={
                "session_id": "s1",
                "message_index": 0,
                "rating": "positive",
                "user_query": "What is energy?",
                "agent_response": "Energy is...",
                "agent_variant": "default",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["s3_key"] == "feedback/2026/07/16/s1_0.json"
    assert data["timestamp"] == "2026-07-16T10:00:00+00:00"


@pytest.mark.asyncio
async def test_feedback_with_comment(client):
    """Feedback with optional comment should be forwarded."""
    with patch("jouleverne.routes.feedback.save_feedback") as mock_save:
        mock_save.return_value = ("key", "ts")

        await client.post(
            "/v1/feedback",
            json={
                "session_id": "s1",
                "message_index": 1,
                "rating": "negative",
                "user_query": "Q",
                "agent_response": "A",
                "agent_variant": "web_search",
                "comment": "Not accurate",
            },
        )

    _, kwargs = mock_save.call_args
    assert kwargs["comment"] == "Not accurate"
    assert kwargs["agent_variant"] == "web_search"


@pytest.mark.asyncio
async def test_feedback_requires_fields(client):
    """Missing required fields should return 422."""
    response = await client.post("/v1/feedback", json={"session_id": "s1"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_feedback_with_override_key(client):
    """s3_key_override should be forwarded to save_feedback."""
    with patch("jouleverne.routes.feedback.save_feedback") as mock_save:
        mock_save.return_value = ("override/key.json", "2026-07-16T10:00:00+00:00")

        await client.post(
            "/v1/feedback",
            json={
                "session_id": "s1",
                "message_index": 0,
                "rating": "positive",
                "user_query": "Q",
                "agent_response": "A",
                "agent_variant": "default",
                "s3_key_override": "override/key.json",
                "original_timestamp": "2026-07-16T09:00:00+00:00",
            },
        )

    _, kwargs = mock_save.call_args
    assert kwargs["s3_key_override"] == "override/key.json"
    assert kwargs["original_timestamp"] == "2026-07-16T09:00:00+00:00"
