# --- FILE: src/api/guess.py ---
""""Guess the master's move" (task 14.3): positions from masters' games selected by the engine; the answer is scored in
points."""

import chess
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.fair_play import optional_user_id
from src.api.rate_limit import rate_limit
from src.core.errors import ApiError
from src.db.session import get_db
from src.models.guess import GuessPosition
from src.models.user import User
from src.services import guess as guess_service
from src.services.guess_quiz import check_quiz

router = APIRouter(dependencies=[Depends(rate_limit("guess", "RATE_LIMIT_PUZZLES"))])

DEFAULT_TARGET = 1500
MAX_GAMES = 100


class AnswerRequest(BaseModel):
    move: str = Field(..., min_length=4, max_length=5, description="The player's move in UCI")
    attempt: int | None = Field(default=None, ge=1, le=guess_service.MAX_ATTEMPTS,
                                description="Attempt number in the \"three attempts\" mode; without it the answer is final")
    hints: int = Field(default=0, ge=0, le=3, description="How many hints were taken before the answer (a points penalty)")


class QuizRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict, max_length=5, description="Question -> code of the chosen option")


async def _position(db: AsyncSession, position_id: int) -> GuessPosition:
    position = await db.get(GuessPosition, position_id)
    if position is None:
        raise ApiError(404, "guess_position_not_found")
    return position


@router.get("/next")
async def next_position(
        request: Request,
        series: bool = Query(default=False, description="The start of a series of moves from a game"),
        candidates: bool = Query(default=False, description="Add options to choose from (beginner mode)"),
        db: AsyncSession = Depends(get_db),
):
    """The next position near the player's strength (puzzle rating; 1500 for a guest). Empty - positions have not been selected
    yet."""
    user_id = await optional_user_id(request, db)
    user = await db.get(User, user_id) if user_id else None
    target = user.puzzle_rating if user else DEFAULT_TARGET
    position = await guess_service.pick_position(db, target, series)
    return {"position": await guess_service.payload(db, position, candidates) if position else None}


@router.get("/position/{position_id}")
async def get_position(position_id: int, candidates: bool = Query(default=False), db: AsyncSession = Depends(get_db)):
    """A position by id (a jump from the game viewer); candidates - add options to choose from."""
    return await guess_service.payload(db, await _position(db, position_id), candidates)


@router.get("/game/{game_id}")
async def positions_of_game(game_id: int, db: AsyncSession = Depends(get_db)):
    """The selected moments of a game - for the "Guess the move" button in the game viewer; an empty list means no button."""
    positions = await guess_service.game_positions(db, game_id)
    return {"positions": [{"id": p.id, "ply": p.ply, "series_id": p.series_id} for p in positions]}


@router.get("/game/{game_id}/quiz")
async def game_quiz(game_id: int, db: AsyncSession = Depends(get_db)):
    """Questions after a "whole" game (who won, the key moment, the mate): option codes without answers."""
    quiz = await guess_service.game_quiz(db, game_id)
    if quiz is None:
        raise ApiError(404, "guess_position_not_found")
    return {"questions": quiz[0]}


@router.post("/game/{game_id}/quiz")
async def check_game_quiz(game_id: int, payload: QuizRequest, db: AsyncSession = Depends(get_db)):
    """Checking the answers to the post-game questions: the score, what is correct and the correct answers."""
    quiz = await guess_service.game_quiz(db, game_id)
    if quiz is None:
        raise ApiError(404, "guess_position_not_found")
    return check_quiz(payload.answers, quiz[1])


@router.get("/games")
async def games_with_positions(
        ids: str = Query(..., max_length=2000, description="Game ids separated by commas"),
        db: AsyncSession = Depends(get_db),
):
    """Which of the games have selected moments: {game_id: id of the first position} (up to MAX_GAMES games per request)."""
    game_ids = [int(part) for part in ids.split(",") if part.strip().isdigit()][:MAX_GAMES]  # anything else is skipped
    found = await guess_service.first_positions(db, game_ids)
    return {"games": {str(game_id): position_id for game_id, position_id in found.items()}}


@router.get("/position/{position_id}/hint")
async def get_hint(position_id: int, step: int = Query(default=1, ge=1, le=3), db: AsyncSession = Depends(get_db)):
    """A tiered hint (1 - a nudge, 2 - the piece, 3 - the arrow of the master's move); each one costs a penalty in the
    answer."""
    return guess_service.hint(await _position(db, position_id), step)


@router.post("/position/{position_id}/answer")
async def answer(position_id: int, payload: AnswerRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """The player's answer; the answer of a logged-in player changes the position rating (src/services/guess.py)."""
    position = await _position(db, position_id)
    board = chess.Board(position.fen)
    try:
        move = chess.Move.from_uci(payload.move)
    except ValueError:
        move = None
    if move is None or move not in board.legal_moves:
        raise ApiError(400, "illegal_move", move=payload.move)
    user_id = await optional_user_id(request, db)
    user = await db.get(User, user_id) if user_id else None
    return await guess_service.answer(db, position, payload.move, user, payload.attempt, payload.hints)
