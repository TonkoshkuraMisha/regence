# --- FILE: src/api/puzzles.py ---
"""
Puzzles (task 13.2): serving, move check, hint, "show the solution", the puzzle of the day, the solver profile.
Defence drills (task 13.6): /defense/*.
"""

import datetime as dt

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.rate_limit import rate_limit
from src.core.errors import DomainValueError
from src.db.session import get_db
from src.models.user import User
from src.services import defense_drills, generated_drills, personal_puzzles, puzzle_leaders
from src.services import mate_course as mate_course_service
from src.services import puzzles as service

router = APIRouter(dependencies=[Depends(rate_limit("puzzles", "RATE_LIMIT_PUZZLES"))])


class TimedStartRequest(BaseModel):
    minutes: int = Field(..., description="3 or 5")


class MoveRequest(BaseModel):
    move: str = Field(..., min_length=4, max_length=5, description="The solver's move in UCI")


def _http(exc: service.PuzzleError):
    return exc.to_http(exc.status)


@router.get("/next")
async def next_puzzle(
        theme: str | None = Query(default=None, max_length=40, description="Registry theme code"),
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """A puzzle for the solver's rating (and by theme), without recently solved ones. Starting it cancels the previous one."""
    try:
        puzzle = await service.pick_puzzle(db, user, theme)
    except service.PuzzleError as exc:
        raise _http(exc) from exc
    await service.start(user, puzzle)
    return service.public_view(puzzle)


@router.get("/train")
async def train(
        theme: str | None = Query(default=None, max_length=40, description="Registry theme"),
        section: str | None = Query(default=None, max_length=1, description="Catalogue section (a mixed selection)"),
        stage: int | None = Query(default=None, description="Tier 1-4; by default the player's current tier"),
        blind: bool = Query(default=False, description="Do not show the puzzle themes until the solution is complete"),
        goal: str | None = Query(default=None, max_length=12, description="Goal: mate / draw / promotion / material"),
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """
    Training by tactical themes (task 13.4): a theme puzzle at the player's tier, mixed by section or - by a single goal
    without a theme
    and section - mixed by goal ("Save the game", 27.9: goal=draw).
    """
    try:
        puzzle, chosen_stage = await service.pick_training(db, user, theme=theme, section=section, stage=stage,
                                                           goal=goal)
    except service.PuzzleError as exc:
        raise _http(exc) from exc
    await service.start(user, puzzle, training=theme, stage=chosen_stage)
    return {**service.public_view(puzzle, show_themes=not blind), "stage": chosen_stage}


@router.get("/demo")
async def demo(theme: str = Query(..., max_length=40), user: User = Depends(get_current_user),
               db: AsyncSession = Depends(get_db)):
    """Showing a theme: two puzzles of the theme with the solution (not an attempt - rating and history do not change)."""
    try:
        return {"theme": theme, "examples": await service.demo_puzzles(db, theme)}
    except service.PuzzleError as exc:
        raise _http(exc) from exc


@router.get("/training")
async def training(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Progress over all themes: tier, latest results, whether mastered, how many puzzles on the tiers."""
    return await service.training_overview(db, user)


@router.get("/daily")
async def daily(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The puzzle of the day - one for everybody (by UTC date)."""
    try:
        puzzle = await service.daily_puzzle(db, dt.datetime.now(dt.UTC).date())
    except service.PuzzleError as exc:
        raise _http(exc) from exc
    await service.start(user, puzzle, daily=True)
    return {**service.public_view(puzzle), "daily": True}


@router.get("/personal")
async def personal_summary(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """"Your mistakes" (task 13.5): how many puzzles are due for repetition now, total in work, mastered, when the next one
    is."""
    return await personal_puzzles.summary(db, user)


@router.get("/personal/next")
async def personal_next(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    puzzle = await personal_puzzles.next_due(db, user)
    if puzzle is None:
        raise service.PuzzleError("no_puzzles_available", 404).to_http(404)
    return {**personal_puzzles.view(puzzle), **await personal_puzzles.game_context(db, puzzle, user)}


@router.post("/personal/{puzzle_id}/answer")
async def personal_answer(puzzle_id: int, payload: MoveRequest, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    try:
        return await personal_puzzles.answer(db, user, puzzle_id, payload.move)
    except service.PuzzleError as exc:
        raise _http(exc) from exc
    except DomainValueError as exc:
        raise exc.to_http(400) from exc


@router.get("/personal/game/{game_id}")
async def personal_for_game(game_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Plies of the game from which the player's puzzles were made - the badge in the game review."""
    return {"game_id": game_id, "plies": await personal_puzzles.plies_for_game(db, game_id, user)}


class SquareRequest(BaseModel):
    square: str = Field(..., min_length=2, max_length=2, description="A board square, for example e4")


@router.get("/defense/next")
async def defense_next(
        kind: str = Query(..., max_length=10, description="threat: \"What is threatened?\", blunder: \"Don't blunder\""),
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """A defence drill (task 13.6) at the player's tier. The threat and the correct moves are not sent."""
    try:
        return defense_drills.public_view(await defense_drills.pick(db, user, kind))
    except service.PuzzleError as exc:
        raise _http(exc) from exc


@router.post("/defense/{drill_id}/threat")
async def defense_threat(drill_id: int, payload: SquareRequest, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """"What does the opponent threaten?", the first stage: the square of the attacking piece or the square of the attack. The
    threat is revealed."""
    try:
        return await defense_drills.show_threat(db, user, drill_id, payload.square)
    except service.PuzzleError as exc:
        raise _http(exc) from exc


@router.post("/defense/{drill_id}/answer")
async def defense_answer(drill_id: int, payload: MoveRequest, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """A defence (or a move out of three in "Don't blunder"): the result, correct moves, refutations, theme progress."""
    try:
        return await defense_drills.answer(db, user, drill_id, payload.move)
    except service.PuzzleError as exc:
        raise _http(exc) from exc
    except DomainValueError as exc:
        raise exc.to_http(400) from exc


class DrillAnswerRequest(BaseModel):
    key: str = Field(..., max_length=60, description="The drill key from /drills/next")
    moves: list[str] = Field(..., min_length=1, max_length=3, description="Solution moves (mate in 2 - three)")
    run: bool = Field(default=False, description="The answer in a timed run")


class DrillRunRequest(BaseModel):
    kind: str = Field(..., max_length=10)
    piece: str = Field(..., max_length=1)
    level: int = Field(..., ge=1, le=3)


@router.get("/drills/next")
async def drills_next(
        kind: str = Query(..., max_length=10), piece: str = Query(..., max_length=1),
        level: int = Query(..., ge=1, le=3), user: User = Depends(get_current_user),
):
    """A generator drill (task 13.7): a position by the seed table; the solution is not sent."""
    try:
        return generated_drills.view(generated_drills.pick(kind, piece, level))
    except service.PuzzleError as exc:
        raise _http(exc) from exc


@router.post("/drills/answer")
async def drills_answer(payload: DrillAnswerRequest, user: User = Depends(get_current_user)):
    try:
        return await generated_drills.answer(user, payload.key, payload.moves, in_run=payload.run)
    except service.PuzzleError as exc:
        raise _http(exc) from exc


@router.post("/drills/run/start")
async def drills_run_start(payload: DrillRunRequest, user: User = Depends(get_current_user)):
    try:
        return await generated_drills.start_run(user, payload.kind, payload.piece, payload.level)
    except service.PuzzleError as exc:
        raise _http(exc) from exc


@router.get("/drills/run/next")
async def drills_run_next(user: User = Depends(get_current_user)):
    try:
        drill, run = await generated_drills.next_in_run(user)
    except service.PuzzleError as exc:
        raise _http(exc) from exc
    return {**generated_drills.view(drill), "run": run}


@router.post("/drills/run/finish")
async def drills_run_finish(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await generated_drills.finish_run(db, user)
    except service.PuzzleError as exc:
        raise _http(exc) from exc


@router.get("/drills/records")
async def drills_records(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"records": await generated_drills.records(db, user), "themes": generated_drills.THEME_DRILLS}


@router.get("/course/mates")
async def mate_course(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The mating-pattern course (task 14.6): patterns in order and the number of puzzles for each."""
    return await mate_course_service.overview(db)


@router.get("/course/mates/exam")
async def mate_course_exam(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The final check plan: puzzles of different patterns (the theme and the number in its set)."""
    return {"minutes": mate_course_service.EXAM_MINUTES, "tasks": await mate_course_service.exam_plan(db)}


@router.get("/course/mates/{theme}/{index}")
async def mate_course_task(theme: str, index: int, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """Start a course puzzle: the index-th puzzle of the pattern by difficulty; it does not change the puzzle rating."""
    try:
        puzzle = await mate_course_service.start_task(db, user, theme, index)
    except service.PuzzleError as exc:
        raise _http(exc) from exc
    return {**service.public_view(puzzle), "course": theme, "index": index}


@router.post("/timed/start")
async def timed_start(payload: TimedStartRequest, user: User = Depends(get_current_user)):
    """Start a timed run (the previous unfinished one is cancelled)."""
    try:
        return await service.start_run(user, payload.minutes)
    except service.PuzzleError as exc:
        raise _http(exc) from exc


@router.get("/timed/next")
async def timed_next(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The next puzzle of the run: harder with each solved one; it does not change the rating."""
    try:
        puzzle, run = await service.next_in_run(db, user)
    except service.PuzzleError as exc:
        raise _http(exc) from exc
    return {**service.public_view(puzzle), "run": run}


@router.post("/timed/finish")
async def timed_finish(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await service.finish_run(db, user)
    except service.PuzzleError as exc:
        raise _http(exc) from exc


@router.get("/timed/leaders")
async def timed_leaders(
        minutes: int = Query(default=3), scope: str = Query(default="week"),
        user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """The timed-run leaderboard: scope "week" - the current week, "all" - records; plus one's own row."""
    if minutes not in puzzle_leaders.MINUTES or scope not in puzzle_leaders.SCOPES:
        raise DomainValueError("invalid_timed_leaders", minutes=minutes, scope=scope).to_http(400)
    return await puzzle_leaders.leaders(db, minutes, scope, user.id)


@router.post("/{puzzle_id}/move")
async def move(puzzle_id: int, payload: MoveRequest, user: User = Depends(get_current_user),
               db: AsyncSession = Depends(get_db)):
    try:
        return await service.play(db, user, puzzle_id, payload.move)
    except service.PuzzleError as exc:
        raise _http(exc) from exc
    except DomainValueError as exc:
        raise exc.to_http(400) from exc


@router.post("/{puzzle_id}/hint")
async def hint(puzzle_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await service.hint(db, user, puzzle_id)
    except service.PuzzleError as exc:
        raise _http(exc) from exc


@router.post("/{puzzle_id}/give-up")
async def give_up(puzzle_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return await service.give_up(db, user, puzzle_id)
    except service.PuzzleError as exc:
        raise _http(exc) from exc


@router.get("/me")
async def my_puzzles(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.profile(db, user)
