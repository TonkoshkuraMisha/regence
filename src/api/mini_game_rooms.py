# --- FILE: src/api/mini_game_rooms.py ---
"""
Trainer games with a human over the network (task 19.8): a room for two by link. Room rules - src/services/
mini_game_rooms.py, game rules - src/services/mini_games.py. Create, join, move, resign and "once more" - only for
logged-in users (limit - as for puzzles); anyone can watch the room (GET, the client repeats it once a second) - with no limit.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.fair_play import optional_user_id
from src.api.rate_limit import rate_limit
from src.core.errors import DomainError
from src.db.session import get_db
from src.models.user import User
from src.services import mini_game_rooms as service

router = APIRouter()
_LIMIT = Depends(rate_limit("mini_rooms", "RATE_LIMIT_PUZZLES"))
# HTTP statuses for refusal codes; the others are 409 (conflict with the room state).
_CODES = {
    "mini_room_not_found": status.HTTP_404_NOT_FOUND, "mini_game_not_found": status.HTTP_404_NOT_FOUND,
    "mini_room_not_player": status.HTTP_403_FORBIDDEN, "mini_game_illegal_move": status.HTTP_400_BAD_REQUEST,
    "mini_game_bad_position": status.HTTP_400_BAD_REQUEST,
}


def _http(exc: DomainError):
    return exc.to_http(_CODES.get(exc.code, status.HTTP_409_CONFLICT))


class CreateIn(BaseModel):
    game_id: str = Field(..., max_length=32)
    color: Literal["white", "black", "random"] = "random"


class MoveIn(BaseModel):
    move: str = Field(..., min_length=4, max_length=5)
    # The room version on which the player saw the position: a stale move is not applied.
    version: int = Field(..., ge=0)


@router.post("", dependencies=[_LIMIT])
async def create_room(payload: CreateIn, user: User = Depends(get_current_user)):
    """A new room: the creator takes the chosen colour, and sends the link /train/games/room/{code} to the opponent."""
    try:
        return await service.create(user, payload.game_id, payload.color)
    except DomainError as exc:
        raise _http(exc) from None


@router.get("/{code}")
async def get_room(code: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The room: position, moves, players, result and the requester's colour. Open to everyone - the page follows the game
    through it too."""
    try:
        return await service.get(code, await optional_user_id(request, db))
    except DomainError as exc:
        raise _http(exc) from None


@router.post("/{code}/join", dependencies=[_LIMIT])
async def join_room(code: str, user: User = Depends(get_current_user)):
    try:
        return await service.join(user, code)
    except DomainError as exc:
        raise _http(exc) from None


@router.post("/{code}/move", dependencies=[_LIMIT])
async def move(code: str, payload: MoveIn, user: User = Depends(get_current_user)):
    try:
        return await service.move(user, code, payload.move, payload.version)
    except DomainError as exc:
        raise _http(exc) from None


@router.post("/{code}/resign", dependencies=[_LIMIT])
async def resign(code: str, user: User = Depends(get_current_user)):
    try:
        return await service.resign(user, code)
    except DomainError as exc:
        raise _http(exc) from None


@router.post("/{code}/rematch", dependencies=[_LIMIT])
async def rematch(code: str, user: User = Depends(get_current_user)):
    try:
        return await service.rematch(user, code)
    except DomainError as exc:
        raise _http(exc) from None
