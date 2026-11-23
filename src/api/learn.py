# --- FILE: src/api/learn.py ---
"""
School (task 14.1): lesson progress. Lessons are client data, so the server accepts any lesson id in the
slug format and stores for it the step, completion and the best result of the quiz questions. Progress only grows: repeating
a lesson does not reset what was passed, and the exam result stored is the best one.

GET /learn/after-game/{game_id} - the "Club Coach" cards after one's own finished game
(src/services/coach_cards.py).

GET /learn/course-progress - what was done by exercise kind, for the auto-credit of course steps
(src/services/course_progress.py).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.rate_limit import rate_limit
from src.core.errors import ApiError
from src.db.session import get_db
from src.models.game import Game, GameStatus
from src.models.lesson import LessonProgress
from src.models.user import User
from src.services import coach_cards, product_metrics
from src.services import course_progress as course_progress_service

router = APIRouter()

LESSON_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{1,63}$"
MAX_STEPS = 200
MAX_EXAM_QUESTIONS = 10
# Lessons are client data, and the server does not know their list (task A.8): a ceiling of records per player so that
# arbitrary ids do not
# pile up endlessly. There are dozens of lessons in the plan.
MAX_LESSON_RECORDS = 300


class ProgressUpdate(BaseModel):
    """
    Lesson progress from the client: the furthest passed step, the number of steps, whether the lesson is completed and the
    result of the quiz questions.
    """
    step: int = Field(..., ge=0, lt=MAX_STEPS, description="The furthest passed step (from zero)")
    steps_total: int = Field(..., ge=1, le=MAX_STEPS)
    completed: bool = False
    exam_score: int | None = Field(None, ge=0, le=MAX_EXAM_QUESTIONS)
    exam_total: int | None = Field(None, ge=1, le=MAX_EXAM_QUESTIONS)

    @model_validator(mode="after")
    def _consistent(self) -> ProgressUpdate:
        if self.step >= self.steps_total:
            raise ValueError("step must be less than steps_total")
        if (self.exam_score is None) != (self.exam_total is None):
            raise ValueError("exam_score and exam_total go together")
        if self.exam_score is not None and self.exam_total is not None and self.exam_score > self.exam_total:
            raise ValueError("exam_score cannot exceed exam_total")
        return self


class ProgressOut(BaseModel):
    lesson_id: str
    step: int
    steps_total: int
    completed: bool
    exam_score: int | None
    exam_total: int | None


def _out(p: LessonProgress) -> ProgressOut:
    return ProgressOut(
        lesson_id=p.lesson_id, step=p.step, steps_total=p.steps_total, completed=p.completed_at is not None,
        exam_score=p.exam_score, exam_total=p.exam_total,
    )


@router.get("/progress", response_model=list[ProgressOut])
async def list_progress(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(LessonProgress).where(LessonProgress.user_id == user.id).order_by(LessonProgress.lesson_id)
    )).scalars().all()
    return [_out(p) for p in rows]


@router.get("/course-progress")
async def course_progress(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """
    What the player did by exercise kind - for the auto-credit of steps of the Big Course and programmes (norms -
    src/services/course_progress.py): {lessons, themes, trainers, exams}.
    """
    return await course_progress_service.summary(db, user.id)


@router.put("/progress/{lesson_id}", response_model=ProgressOut)
async def save_progress(
        payload: ProgressUpdate,
        lesson_id: str = Path(..., pattern=LESSON_ID_PATTERN),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
):
    """
    Saves lesson progress. Repeating a passed lesson does not reset it: the step only grows, the result of the
    quiz questions stored is the best one.
    """
    progress = (await db.execute(
        select(LessonProgress).where(LessonProgress.user_id == user.id, LessonProgress.lesson_id == lesson_id)
    )).scalar_one_or_none()
    if progress is None:
        count = (await db.execute(
            select(func.count(LessonProgress.id)).where(LessonProgress.user_id == user.id)
        )).scalar_one()
        if count >= MAX_LESSON_RECORDS:
            raise ApiError(409, "lesson_progress_limit", max=MAX_LESSON_RECORDS)
        progress = LessonProgress(user_id=user.id, lesson_id=lesson_id, step=0, steps_total=payload.steps_total)
        db.add(progress)

    # The lesson may have been rewritten (fewer steps now) - the step does not go beyond its length.
    progress.steps_total = payload.steps_total
    progress.step = min(max(progress.step, payload.step), payload.steps_total - 1)
    if payload.completed and progress.completed_at is None:
        progress.completed_at = datetime.now(UTC)
        await product_metrics.record_event(db, user.id, product_metrics.LESSON_COMPLETED)
    if payload.exam_score is not None and payload.exam_total is not None:
        if progress.exam_total != payload.exam_total:
            # The exam changed - the former result does not apply to it.
            progress.exam_score, progress.exam_total = payload.exam_score, payload.exam_total
        else:
            progress.exam_score = max(progress.exam_score or 0, payload.exam_score)
    await db.commit()
    await db.refresh(progress)
    return _out(progress)


@router.get("/after-game/{game_id}", dependencies=[Depends(rate_limit("after_game", "RATE_LIMIT_PUZZLES"))])
async def after_game(game_id: int = Path(..., ge=1), db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """
    "Club Coach" cards after a game: a personal puzzle from the costliest mistake, a deviation from the repertoire and the
    mistake themes
    for a lesson (src/services/coach_cards.py). Only one's own finished game, otherwise 404 game_not_found.
    """
    game = await db.get(Game, game_id)
    player = game is not None and user.id in (game.white_player_id, game.black_player_id)
    if game is None or not player or game.status != GameStatus.COMPLETED:
        raise ApiError(404, "game_not_found", game_id=game_id)
    return await coach_cards.for_game(db, game, user.id)
