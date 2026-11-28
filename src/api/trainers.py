# --- FILE: src/api/trainers.py ---
"""
Trainers (task 19.1): recording an attempt result, personal records and history for a chart. Trainers are computed on the
client, so the server only checks the value bounds: records are personal and do not affect the rating.
"""

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.rate_limit import rate_limit
from src.core.errors import ApiError
from src.db.session import get_db
from src.models.trainer import TrainerResult
from src.models.user import User

router = APIRouter(dependencies=[Depends(rate_limit("trainers", "RATE_LIMIT_PUZZLES"))])

# Known trainers: "Quiet Path", "Fork", "Knight's Route", "Tail" (task 16.5); coordinates (19.2):
# their level is a combination of settings (side, coordinates on the board, 30/60 s), see frontend/src/trainers/coordinates.ts.
TRAINERS = ("quiet_path", "double_strike", "knight_route", "tail",
            "coord_find", "coord_name", "coord_color", "coord_diagonal",
            # Memory (19.3): "Restore the position" and "Remember the game".
            "memory_position", "memory_game",
            # Board puzzles (19.4): for placement the level is the puzzle number, for the tour - the board size (3 - 8x8).
            "board_placement", "knight_tour",
            # Visualisation (19.6): a blindfold move and "Where is the piece?", the level is the number of plies blindfold
            # (1-10).
            "blind_move", "blind_where",
            # Counting and attention (19.7): there are no levels (always 1).
            "calc_checks", "calc_exchange", "calc_distance", "calc_square", "calc_eval", "calc_compare",
            # Pawn structures and miniatures (27.9): no levels either. The list must match TRAINER_IDS in
            # frontend/src/services/trainers.ts (tests/test_trainers.py compares them).
            "structure_quiz", "plan_quiz", "miniatures")
MAX_LEVEL = 20
HISTORY = 50


class ResultIn(BaseModel):
    trainer: str = Field(..., max_length=32)
    level: int = Field(..., ge=1, le=MAX_LEVEL)
    score: int = Field(..., ge=0, le=100_000)
    time_ms: int = Field(..., ge=0, le=3_600_000)
    mistakes: int = Field(0, ge=0, le=1_000)


def _check(trainer: str) -> None:
    if trainer not in TRAINERS:
        raise ApiError(404, "trainer_not_found", trainer=trainer)


async def _best(db: AsyncSession, user_id: int, trainer: str, level: int | None = None) -> int | None:
    query = select(func.max(TrainerResult.score)).where(TrainerResult.user_id == user_id, TrainerResult.trainer == trainer)
    if level is not None:
        query = query.where(TrainerResult.level == level)
    return await db.scalar(query)


@router.post("/results")
async def save_result(payload: ResultIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """An attempt result; record - whether the level's personal record was beaten."""
    _check(payload.trainer)
    previous = await _best(db, user.id, payload.trainer, payload.level)
    db.add(TrainerResult(user_id=user.id, **payload.model_dump()))
    await db.commit()
    return {"record": previous is None or payload.score > previous,
            "best": max(payload.score, previous or 0)}


@router.get("/records")
async def records(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """For each trainer: the best result, the highest level passed, the number of attempts."""
    rows = (await db.execute(
        select(TrainerResult.trainer, func.max(TrainerResult.score), func.max(TrainerResult.level), func.count())
        .where(TrainerResult.user_id == user.id).group_by(TrainerResult.trainer)
    )).all()
    return {"records": {trainer: {"best": best, "max_level": level, "attempts": count}
                        for trainer, best, level, count in rows}}


@router.get("/history/{trainer}")
async def history(trainer: str = Path(..., max_length=32), db: AsyncSession = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """The latest results of a trainer - for a chart (oldest first)."""
    _check(trainer)
    rows = (await db.execute(
        select(TrainerResult).where(TrainerResult.user_id == user.id, TrainerResult.trainer == trainer)
        .order_by(TrainerResult.created_at.desc(), TrainerResult.id.desc()).limit(HISTORY)
    )).scalars().all()
    return {"results": [{"level": r.level, "score": r.score, "time_ms": r.time_ms, "mistakes": r.mistakes,
                         "created_at": r.created_at.isoformat()} for r in reversed(rows)]}
