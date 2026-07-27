"""Release notes endpoint — serves release history from the build-time JSON."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["releases"])
logger = logging.getLogger(__name__)

# The JSON is generated at Docker build time by scripts/fetch_releases.py
# and placed in the project root. At runtime it's copied into the container.
_RELEASE_NOTES_PATH = Path(__file__).parent.parent.parent.parent / "release_notes.json"


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
