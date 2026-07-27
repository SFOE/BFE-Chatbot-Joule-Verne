"""External links endpoint — provides sidebar/footer links for the frontend."""

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["links"])


@router.get("/links")
async def get_links():
    """Return external links to display in the frontend sidebar/footer."""
    return [
        {
            "label": "Use Copilot to generate images",
            "url": "https://m365.cloud.microsoft/chat",
            "icon": "🎨",
            "target": "_blank",
        },
    ]
