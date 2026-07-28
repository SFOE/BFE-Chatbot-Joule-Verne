"""Release notes endpoint — serves release history from the build-time JSON."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["releases"])
logger = logging.getLogger(__name__)

# The JSON is generated at Docker build time by scripts/fetch_releases.py.
# In Docker it lives at /app/release_notes.json (4 parents up from this file).
# In local dev it may be at the project root (5 parents up).
_base = Path(__file__).parent.parent.parent.parent  # → backend/ or /app/
_RELEASE_NOTES_PATH = _base / "release_notes.json"
if not _RELEASE_NOTES_PATH.exists():
    _RELEASE_NOTES_PATH = _base.parent / "release_notes.json"


def _load_releases() -> list:
    """Load release notes from the JSON file."""
    if not _RELEASE_NOTES_PATH.exists():
        logger.warning("release_notes.json not found at %s", _RELEASE_NOTES_PATH)
        return []
    try:
        return json.loads(_RELEASE_NOTES_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Failed to load release notes: %s", e)
        return []


@router.get("/releases")
async def get_releases():
    """Return the list of release notes."""
    return _load_releases()
