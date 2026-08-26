"""Knowledge base endpoint — lists specific (personal/group) KBs selectable as chat modes."""

from fastapi import APIRouter

from ..config import settings

router = APIRouter(prefix="/v1", tags=["kbs"])


def _parse_specific_kbs() -> list[dict]:
    """Parse SPECIFIC_KB_DISPLAY_NAMES into a list of {id, names} entries.

    Format: "id:DE_Name|FR_Name|IT_Name|EN_Name, id2:Name"
    """
    kbs: list[dict] = []
    for pair in settings.SPECIFIC_KB_DISPLAY_NAMES.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        kb_id, names_str = pair.split(":", 1)
        parts = names_str.strip().split("|")
        if len(parts) == 4:
            names = {
                "de": parts[0].strip(),
                "fr": parts[1].strip(),
                "it": parts[2].strip(),
                "en": parts[3].strip(),
            }
        else:
            name = names_str.strip()
            names = {"de": name, "fr": name, "it": name, "en": name}
        kbs.append({"id": kb_id.strip(), "names": names})
    return kbs


@router.get("/kbs/specific")
async def get_specific_kbs():
    """Return the list of specific knowledge bases selectable as a chat mode."""
    return _parse_specific_kbs()
