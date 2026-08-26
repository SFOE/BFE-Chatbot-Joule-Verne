"""Knowledge base endpoint — lists specific (personal/group) KBs selectable as chat modes."""

from fastapi import APIRouter

from ..config import settings

router = APIRouter(prefix="/v1", tags=["kbs"])


def parse_specific_kbs() -> list[dict]:
    """Parse SPECIFIC_KB_DISPLAY_NAMES into a list of {id, prefix, names} entries.

    Format: "id:prefix:DE_Name|FR_Name|IT_Name|EN_Name, id2:prefix2:Name"
    """
    kbs: list[dict] = []
    for entry in settings.SPECIFIC_KB_DISPLAY_NAMES.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":", 2)
        if len(parts) != 3:
            continue
        kb_id, prefix, names_str = parts
        name_parts = names_str.strip().split("|")
        if len(name_parts) == 4:
            names = {
                "de": name_parts[0].strip(),
                "fr": name_parts[1].strip(),
                "it": name_parts[2].strip(),
                "en": name_parts[3].strip(),
            }
        else:
            name = names_str.strip()
            names = {"de": name, "fr": name, "it": name, "en": name}
        kbs.append({"id": kb_id.strip(), "prefix": prefix.strip(), "names": names})
    return kbs


def get_prefix_for_kb(kb_id: str) -> str | None:
    """Return the S3 prefix for a given specific KB ID, or None if not found."""
    for kb in parse_specific_kbs():
        if kb["id"] == kb_id:
            return kb["prefix"]
    return None


@router.get("/kbs/specific")
async def get_specific_kbs():
    """Return the list of specific knowledge bases selectable as a chat mode."""
    # Do not expose the S3 prefix to the frontend — only id + display names.
    return [{"id": kb["id"], "names": kb["names"]} for kb in parse_specific_kbs()]
