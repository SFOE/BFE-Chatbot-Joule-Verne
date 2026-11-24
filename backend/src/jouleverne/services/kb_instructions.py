"""Per-KB agent instructions — stored in S3, appended to the agent prompt.

Users with write permission on a specific KB can maintain a free-text
instruction for it. When that KB is selected in a chat, the instruction is
loaded server-side and forwarded to the agent, which appends it to its system
prompt. The text is stored under ``kb-instructions/<kb_id>.txt`` in the
conversations bucket (not in the KB inbox bucket, so it is never ingested).
"""

import logging

from botocore.exceptions import ClientError

from ..config import settings
from .clients import s3_client

logger = logging.getLogger(__name__)

MAX_INSTRUCTION_CHARS = 4000
_PREFIX = "kb-instructions/"


def _key(kb_id: str) -> str:
    return f"{_PREFIX}{kb_id}.txt"


def is_configured() -> bool:
    return bool(settings.CONVERSATIONS_BUCKET)


def get_instruction(kb_id: str) -> str:
    """Return the stored instruction for a KB ("" when none or on error)."""
    if not is_configured():
        return ""
    try:
        obj = s3_client.get_object(Bucket=settings.CONVERSATIONS_BUCKET, Key=_key(kb_id))
        return obj["Body"].read().decode("utf-8")
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") not in ("NoSuchKey", "404"):
            logger.warning("Failed to load instruction for KB %s: %s", kb_id, e)
        return ""
    except Exception as e:  # never break a chat because of an instruction
        logger.warning("Failed to load instruction for KB %s: %s", kb_id, e)
        return ""


def put_instruction(kb_id: str, text: str) -> None:
    """Store the instruction; an empty text removes it."""
    key = _key(kb_id)
    if not text.strip():
        s3_client.delete_object(Bucket=settings.CONVERSATIONS_BUCKET, Key=key)
        return
    s3_client.put_object(
        Bucket=settings.CONVERSATIONS_BUCKET,
        Key=key,
        Body=text.encode("utf-8"),
        ContentType="text/plain; charset=utf-8",
    )


def get_instructions_for(kb_ids: list[str]) -> dict[str, str]:
    """Return {kb_id: instruction} for the given KBs, omitting empty ones."""
    result: dict[str, str] = {}
    for kb_id in dict.fromkeys(kb_ids):
        text = get_instruction(kb_id).strip()
        if text:
            result[kb_id] = text
    return result
