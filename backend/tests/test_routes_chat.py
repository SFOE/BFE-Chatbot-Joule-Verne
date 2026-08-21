"""Tests for the chat SSE endpoint."""

import pytest
from unittest.mock import patch


@pytest.mark.asyncio
async def test_chat_returns_sse_stream(client):
    """POST /v1/chat should return a text/event-stream response."""
    mock_events = [
        ("token", '{"text": "Hello"}'),
        ("token", '{"text": " world"}'),
        ("done", "{}"),
    ]

    with patch("jouleverne.routes.chat.stream_agent_response", return_value=iter(mock_events)):
        response = await client.post(
            "/v1/chat",
            json={"message": "Hi", "session_id": "s1"},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_chat_streams_events(client):
    """Verify individual SSE events are present in the response body."""
    mock_events = [
        ("token", '{"text": "Hello"}'),
        ("trace", '{"label": "Thinking..."}'),
        ("citation", '{"source": "s3://b/k", "text": "ref"}'),
        ("done", "{}"),
    ]

    with patch("jouleverne.routes.chat.stream_agent_response", return_value=iter(mock_events)):
        response = await client.post(
            "/v1/chat",
            json={"message": "test", "session_id": "s1"},
        )

    body = response.text
    assert "event: token" in body
    assert "event: trace" in body
    assert "event: citation" in body
    assert "event: done" in body


@pytest.mark.asyncio
async def test_chat_passes_web_search_flag(client):
    """Verify web_search flag is forwarded to the agent service."""
    with patch("jouleverne.routes.chat.stream_agent_response", return_value=iter([("done", "{}")])) as mock:
        await client.post(
            "/v1/chat",
            json={"message": "search", "session_id": "s1", "web_search": True},
        )

    mock.assert_called_once()
    _, kwargs = mock.call_args
    assert kwargs["web_search"] is True


@pytest.mark.asyncio
async def test_chat_passes_session_attributes(client):
    """Verify session_attributes are forwarded."""
    attrs = {"uploaded_document": "some text", "document_name": "test.pdf"}

    with patch("jouleverne.routes.chat.stream_agent_response", return_value=iter([("done", "{}")])) as mock:
        await client.post(
            "/v1/chat",
            json={
                "message": "question",
                "session_id": "s1",
                "session_attributes": attrs,
            },
        )

    _, kwargs = mock.call_args
    assert kwargs["session_attributes"] == attrs


@pytest.mark.asyncio
async def test_chat_requires_message_and_session_id(client):
    """Missing required fields should return 422."""
    response = await client.post("/v1/chat", json={})
    assert response.status_code == 422

    response = await client.post("/v1/chat", json={"message": "hi"})
    assert response.status_code == 422
