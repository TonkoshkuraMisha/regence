# --- FILE: src/api/themes.py ---
"""The registry of tactical themes (task 13.0): the client gets codes, sections, parents and minimums; the texts are on its
side."""

from fastapi import APIRouter

from src.services.themes import SECTIONS, registry_payload

router = APIRouter()


@router.get("")
async def list_themes() -> dict:
    """Sections A-L and all registry themes in catalogue order."""
    return {"sections": list(SECTIONS), "themes": registry_payload()}
