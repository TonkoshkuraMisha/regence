"""
Regular events (/events; task 26.1): the weekly tournament against legends (src/services/weekly_legends.py).

GET /events/weekly-legends is open to guests (the lobby banner and the page show the line-up and the table); starting a
game needs a login. The game itself is played on the main board and counted by POST /bots/save-game with weekly=true.
"""

import random
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.library import optional_user
from src.core.errors import DomainError
from src.db.session import get_db
from src.models.user import User
from src.services import weekly_legends

router = APIRouter(prefix="/events", tags=["Events"])

_CODES = {"weekly_legend_unknown": status.HTTP_404_NOT_FOUND, "weekly_legend_played": status.HTTP_409_CONFLICT}


class WeeklyStartRequest(BaseModel):
    bot_id: str
    color: Literal["white", "black", "random"] = "random"


@router.get("/weekly-legends")
async def weekly_legends_event(db: AsyncSession = Depends(get_db), viewer: User | None = Depends(optional_user)):
    """This week's legends, the time control, the end of the week, the standings and the viewer's own results."""
    return await weekly_legends.event(db, viewer)


@router.post("/weekly-legends/start")
async def start_weekly_game(payload: WeeklyStartRequest, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    """Opens a fair game with a legend of this week; a previously started weekly game counts as an abandoned loss."""
    color = payload.color if payload.color != "random" else random.choice(("white", "black"))
    try:
        return await weekly_legends.start_game(db, user, payload.bot_id, color)
    except DomainError as exc:
        raise exc.to_http(_CODES.get(exc.code, status.HTTP_400_BAD_REQUEST)) from exc
