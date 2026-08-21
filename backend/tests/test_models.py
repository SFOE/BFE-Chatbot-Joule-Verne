"""Tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from jouleverne.models.chat import ChatRequest, TokenEvent, TraceEvent, CitationEvent


class TestChatRequest:
    def test_valid_request(self):
        req = ChatRequest(message="Hello", session_id="abc-123")
        assert req.message == "Hello"
        assert req.session_id == "abc-123"
        assert req.web_search is False

    def test_web_search_flag(self):
        req = ChatRequest(message="Search this", session_id="s1", web_search=True)
        assert req.web_search is True

    def test_missing_message_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest(session_id="s1")

    def test_missing_session_id_raises(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="Hello")


class TestTokenEvent:
    def test_serialization(self):
        evt = TokenEvent(text="chunk")
        data = evt.model_dump()
        assert data == {"text": "chunk"}

    def test_json_output(self):
        evt = TokenEvent(text="hello")
        assert '"text":"hello"' in evt.model_dump_json().replace(" ", "")


class TestTraceEvent:
    def test_with_detail(self):
        evt = TraceEvent(label="thinking", detail="some detail")
        assert evt.label == "thinking"
        assert evt.detail == "some detail"

    def test_without_detail(self):
        evt = TraceEvent(label="step")
        assert evt.detail is None


class TestCitationEvent:
    def test_valid(self):
        evt = CitationEvent(source="s3://bucket/doc.pdf", text="relevant text")
        assert evt.source == "s3://bucket/doc.pdf"
        assert evt.text == "relevant text"
