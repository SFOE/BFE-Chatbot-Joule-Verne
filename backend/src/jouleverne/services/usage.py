"""Usage tracking — log per-question usage to S3."""

import json
import logging
import uuid
from datetime import datetime, timezone

from ..config import settings
from .clients import s3_client

logger = logging.getLogger(__name__)


def log_usage(user_email: str | None, locale: str = "de", web_search: bool = False) -> None:
    """Log a single usage event (one chat question) to S3.

    Files are stored under usage/{year}/{week}/{uuid}.json grouped by
    ISO week number so that weekly aggregation is a simple prefix listing.
    """
    if not settings.FEEDBACK_BUCKET:
        logger.warning("FEEDBACK_BUCKET not configured, skipping usage log.")
        return

    if not user_email:
        return

    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()

    key = f"usage/{year}/{week:02d}/{uuid.uuid4().hex}.json"

    payload = {"user_email": user_email, "locale": locale, "web_search": web_search}

    try:
        s3_client.put_object(
            Bucket=settings.FEEDBACK_BUCKET,
            Key=key,
            Body=json.dumps(payload, ensure_ascii=False),
            ContentType="application/json",
        )
    except Exception:
        logger.exception("Failed to log usage for user")
