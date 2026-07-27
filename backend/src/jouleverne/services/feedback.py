"""Feedback persistence — save user feedback to S3."""

import json
import logging
from datetime import datetime, timezone

from ..config import settings
from .clients import s3_client

logger = logging.getLogger(__name__)


def save_feedback(
    *,
    session_id: str,
    message_index: int,
    rating: str | None,
    user_query: str,
    agent_response: str,
    agent_variant: str,
    comment: str | None = None,
    retrieved_chunks: list[dict] | None = None,
    tools_used: list[str] | None = None,
    s3_key_override: str | None = None,
    original_timestamp: str | None = None,
) -> tuple[str | None, str | None]:
    """Save user feedback to S3 as a JSON file.

    If s3_key_override is provided, uses that key (to overwrite a previously saved record).
    Returns (s3_key, timestamp) or (None, None) if bucket is not configured.
    """
    if not settings.FEEDBACK_BUCKET:
        logger.warning("FEEDBACK_BUCKET not configured, skipping feedback save.")
        return None, None

    now = datetime.now(timezone.utc)
    timestamp = original_timestamp or now.isoformat()

    feedback = {
        "session_id": session_id,
        "timestamp": timestamp,
        "rating": rating,
        "user_query": user_query,
        "agent_response": agent_response,
        "agent_variant": agent_variant,
        "message_index": message_index,
        "retrieved_chunks": retrieved_chunks or [],
        "comment": comment,
        "tools_used": tools_used or [],
    }

    key = s3_key_override or (
        f"feedback/{now.year}/{now.month:02d}/{now.day:02d}/"
        f"{session_id}_{message_index}.json"
    )

    s3_client.put_object(
        Bucket=settings.FEEDBACK_BUCKET,
        Key=key,
        Body=json.dumps(feedback, ensure_ascii=False),
        ContentType="application/json",
    )

    return key, timestamp
