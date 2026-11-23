# --- FILE: src/services/puzzles.py ---
"""
Solving puzzles (task 13.2). The solution is not sent to the client: the server keeps track of which move the solver is on
(Redis, one active puzzle per player), checks every move and replies with the opponent's move. Mate always counts, even if the
database solution has a different move. The first mistake ends the puzzle (as in a game: a move cannot be taken back) -
then the solution is shown in full.

The solver's rating is Elo against the puzzle's rating: K = 40 for the first PROVISIONAL_GAMES puzzles, then 20. A hint reduces
the gain: one - by half, two (the move is shown) - to zero; a loss counts in full. The streak is puzzles solved in a row
without mistakes and hints. The "Puzzle of the Day" is one for everybody: chosen by date from popular puzzles of medium level.

Timed mode (task 13.3): a run of 3 or 5 minutes is kept on the server - the server counts the score and mistakes, the
client only shows the timer. Run puzzles do not change the rating; difficulty grows with each solved one (from the player's
rating -300 with step TIMED_STEP). Three mistakes or the end of time end the run, the best score is a personal record.

Training by techniques (task 13.4): puzzles of a theme at the player's current stage (1-4); a stage is passed when out of
the last STAGE_WINDOW puzzles at least STAGE_PASS were solved cleanly (without a mistake or a hint). A mixed selection is
by section of the catalogue; "without theme name" - the puzzle's themes are not shown until the solution is finished.

Where the data lives. PostgreSQL: puzzles are puzzles and puzzle_themes (the open lichess database, loaded by
src/services/puzzle_import.py); each finished attempt is puzzle_attempts (run and course puzzles too: they
enter the history, streak and the recent list, only the rating is unchanged); theme progress is theme_progress; the solver's
rating, puzzle count and run records are users.puzzle_rating, puzzle_games, puzzle_best_3, puzzle_best_5. The rating
of the puzzle itself (puzzles.rating) never changes. Redis: ``puzzle:session:{user_id}`` - the active puzzle (JSON
PuzzleSession, lives SESSION_TTL_S), ``puzzle:run:{user_id}`` - the timed run (until its end plus 10 minutes).
Routes - src/api/puzzles.py.
"""

import datetime as dt
import json
import time
import uuid
import zlib
from dataclasses import asdict, dataclass

import chess
from sqlalchemy import ColumnElement, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.core.errors import DomainError, DomainValueError
from src.db import redis as redis_module
from src.models.puzzle import Puzzle, PuzzleAttempt, PuzzleTheme, ThemeProgress
from src.models.user import User
from src.services import product_metrics, puzzle_leaders
from src.services.themes import GOAL_THEMES, PUZZLE_GOALS, SECTIONS, THEMES, THEMES_BY_CODE, puzzle_goal

SESSION_TTL_S = 2 * 60 * 60  # an active puzzle without moves lives 2 hours, then counts as abandoned (rating unchanged)
RECENT_EXCLUDED = 300  # how many of the last solved puzzles are not issued again
# Rating window around the player's rating when choosing a puzzle: widens in steps, None - any puzzle.
RATING_WINDOWS = (75, 150, 300, 600, None)
PROVISIONAL_GAMES = 30  # for the first puzzles the rating is "provisional": K = 40 (same as rating.py for games)
MIN_RATING = 400  # the solver's rating does not fall below this
HINT_FACTORS = (1.0, 0.5, 0.0)  # gain multiplier for a solved puzzle with 0, 1 and 2 hints
DAILY_RATING = (1300, 1900)  # "puzzle of the day": the puzzle rating within these limits...
DAILY_POPULARITY = 95  # ...and popularity in the lichess database not lower than this
TIMED_MINUTES = (3, 5)  # allowed duration of a timed run
TIMED_MISTAKES = 3  # this many mistakes end the run
TIMED_START_OFFSET = -300  # the first puzzle of a run is 300 points easier than the player's rating...
TIMED_STEP = 40  # ...and each solved one raises the target by 40 (not below 600)
TIMED_GRACE_S = 2  # grace for the end of a run for network delay: a move arriving 2 s after the deadline still counts
STAGES = (1, 2, 3, 4)  # theme stages; the puzzle's stage (puzzles.stage) is assigned by puzzle_import.stage_for
STAGE_WINDOW = 10  # a stage is passed when out of the last 10 puzzles of the stage...
STAGE_PASS = 8  # ...at least 8 were solved cleanly


class PuzzleError(DomainError):
    """A puzzle-solving error with a catalogue code and an HTTP status."""

    def __init__(self, code: str, status: int, **params: object):
        super().__init__(code, **params)
        self.status = status


@dataclass
class PuzzleSession:
    """
    The player's active puzzle (stored in Redis): which puzzle, which solver move is expected, how many hints were taken and
    in which mode it is being solved.
    """
    puzzle_id: int
    index: int = 1          # index of the expected solver move in moves
    hints: int = 0
    daily: bool = False     # puzzle of the day: a mark, it does not affect the check or the rating
    run: str | None = None  # timed-mode run: a puzzle without a rating
    training: str | None = None  # training by theme: its code (theme progress is updated by the outcome)
    stage: int | None = None
    course: str | None = None  # course of mating patterns (14.6): a puzzle without a rating


def _session_key(user_id: int) -> str:
    return f"puzzle:session:{user_id}"


async def _load_session(user_id: int) -> PuzzleSession | None:
    raw = await redis_module.redis_client.get(_session_key(user_id))
    return PuzzleSession(**json.loads(raw)) if raw else None


async def _save_session(user_id: int, session: PuzzleSession) -> None:
    await redis_module.redis_client.set(_session_key(user_id), json.dumps(asdict(session)), ex=SESSION_TTL_S)


async def _drop_session(user_id: int) -> None:
    await redis_module.redis_client.delete(_session_key(user_id))


def solver_color(puzzle: Puzzle) -> str:
    """Solver colour: the side that moves after the opponent's first move."""
    return "black" if puzzle.fen.split()[1] == "w" else "white"


def public_view(puzzle: Puzzle, *, show_themes: bool = True) -> dict:
    """What the client sees: position, the opponent's first move, rating, themes and the solution length - not the solution."""
    moves = puzzle.moves.split()
    return {
        "id": puzzle.id,
        "fen": puzzle.fen,
        "first_move": moves[0],
        "rating": puzzle.rating,
        "themes": puzzle.theme_codes if show_themes else [],
        "goal": puzzle_goal(puzzle.theme_codes) if show_themes else None,
        "color": solver_color(puzzle),
        "solution_length": len(moves[1::2]),
    }


async def _recent_ids(db: AsyncSession, user_id: int) -> list[int]:
    """Puzzles of the player's last RECENT_EXCLUDED attempts (puzzle_attempts) - the selection does not issue them again."""
    rows = await db.execute(
        select(PuzzleAttempt.puzzle_id).where(PuzzleAttempt.user_id == user_id)
        .order_by(PuzzleAttempt.created_at.desc(), PuzzleAttempt.id.desc()).limit(RECENT_EXCLUDED)
    )
    return list(rows.scalars())


async def pick_puzzle(
        db: AsyncSession, user: User, theme: str | None = None, target_rating: int | None = None,
) -> Puzzle:
    """
    A puzzle for the player's rating (the window widens until one is found), by theme, without recent ones. target_rating
    replaces the player's rating (timed run). Within the window a puzzle is chosen randomly.
    """
    if theme is not None and theme not in THEMES_BY_CODE:
        raise PuzzleError("unknown_theme", 400, theme=theme)
    recent = await _recent_ids(db, user.id)
    target = user.puzzle_rating if target_rating is None else target_rating
    for window in RATING_WINDOWS:
        query = select(Puzzle)
        if theme is not None:
            query = query.join(PuzzleTheme).where(PuzzleTheme.theme == theme)
        if window is not None:
            query = query.where(Puzzle.rating.between(target - window, target + window))
        if recent:
            query = query.where(Puzzle.id.not_in(recent))
        puzzle = await db.scalar(query.order_by(func.random()).limit(1))
        if puzzle is not None:
            return puzzle
    # Everything suitable was solved recently (a narrow theme) - better to repeat than leave the player without a puzzle.
    query = select(Puzzle)
    if theme is not None:
        query = query.join(PuzzleTheme).where(PuzzleTheme.theme == theme)
    puzzle = await db.scalar(query.order_by(func.random()).limit(1))
    if puzzle is not None:
        return puzzle
    raise PuzzleError("no_puzzles_available", 404)


async def daily_puzzle(db: AsyncSession, day: dt.date) -> Puzzle:
    """
    One puzzle for everybody for this day: popular, of medium level, by date. The index among suitable puzzles (in
    ascending id order) is the checksum of the date modulo their count: a day always gives the same puzzle until the database
    changes. If there are no suitable ones, the choice is made from all puzzles.
    """
    condition: ColumnElement[bool] = (Puzzle.popularity >= DAILY_POPULARITY) & Puzzle.rating.between(*DAILY_RATING)
    count = await db.scalar(select(func.count()).select_from(Puzzle).where(condition)) or 0
    if count == 0:
        condition = Puzzle.id.is_not(None)
        count = await db.scalar(select(func.count()).select_from(Puzzle)) or 0
    if count == 0:
        raise PuzzleError("no_puzzles_available", 404)
    offset = zlib.crc32(day.isoformat().encode()) % count
    puzzle = await db.scalar(select(Puzzle).where(condition).order_by(Puzzle.id).offset(offset).limit(1))
    assert puzzle is not None
    return puzzle


async def start(user: User, puzzle: Puzzle, *, daily: bool = False, run: str | None = None,
                training: str | None = None, stage: int | None = None, course: str | None = None) -> None:
    """
    Start a puzzle: a previous unfinished one is simply cancelled (no rating change and no attempt record).
    Parameters are the solving mode: puzzle of the day, timed run, theme training with a stage, course of mating patterns.
    """
    await _save_session(user.id, PuzzleSession(puzzle_id=puzzle.id, daily=daily, run=run, training=training,
                                               stage=stage, course=course))


# --- training by techniques ---------------------------------------------------------------------------------

# The ``stage_counts`` cache in process memory: (theme, stage) -> number of puzzles. Each API process has its own.
_stage_counts: dict[tuple[str, int], int] | None = None


async def stage_counts(db: AsyncSession) -> dict[tuple[str, int], int]:
    """
    How many puzzles each theme has at each stage. The puzzle database changes only by import - computed once per
    process (the import runs at deployment, before the API starts; an import into a running system is seen by the API
    processes after a restart). The themes "What Does the Opponent Threaten?" and "Don't Blunder" are solved by defensive
    exercises (task 13.6) - their count comes from there.
    """
    from src.services import defense_drills

    global _stage_counts
    if _stage_counts is None:
        rows = await db.execute(
            select(PuzzleTheme.theme, Puzzle.stage, func.count()).join(Puzzle, Puzzle.id == PuzzleTheme.puzzle_id)
            .group_by(PuzzleTheme.theme, Puzzle.stage)
        )
        counts = {(theme, stage): count for theme, stage, count in rows}
        for key, count in (await defense_drills.stage_counts(db)).items():
            counts[key] = counts.get(key, 0) + count
        _stage_counts = counts
    return _stage_counts


def reset_stage_counts() -> None:
    """Resets the ``stage_counts`` cache of this process: after a puzzle import and in tests."""
    global _stage_counts
    _stage_counts = None


async def _progress(db: AsyncSession, user_id: int, theme: str) -> ThemeProgress | None:
    return await db.get(ThemeProgress, (user_id, theme))


def goal_clause(goal: str) -> ColumnElement[bool]:
    """
    Puzzles with this goal (27.8): the goal's theme is present and no themes of senior goals; "material" - none of the
    senior ones. Seniority is the order of themes.PUZZLE_GOALS, the themes of each goal are themes.GOAL_THEMES.
    """
    other = aliased(PuzzleTheme)

    def has(codes: tuple[str, ...]) -> ColumnElement[bool]:
        return exists().where(other.puzzle_id == Puzzle.id, other.theme.in_(codes))

    higher = PUZZLE_GOALS[:PUZZLE_GOALS.index(goal)]
    conditions = [~has(GOAL_THEMES[g]) for g in higher]
    if goal != "material":
        conditions.append(has(GOAL_THEMES[goal]))
    return and_(*conditions)


async def pick_training(
        db: AsyncSession, user: User, *, theme: str | None = None, section: str | None = None,
        stage: int | None = None, goal: str | None = None,
) -> tuple[Puzzle, int | None]:
    """
    A training puzzle: by theme (the stage - from progress, if not given) or mixed by section; goal - only
    puzzles with this goal ("deflection with a mating goal", 27.8). A goal alone without a theme and section is a mixed
    selection by the goal from all themes: this is how the "Save the Game" mode works (27.9, goal=draw).

    Returns the puzzle and the stage (None for a mixed selection). First a puzzle not among the recent ones is searched,
    then any: on a narrow theme a repeat is better than a refusal.
    """
    if theme is not None and section is not None:
        raise PuzzleError("training_target_required", 400)
    if theme is None and section is None and goal is None:
        raise PuzzleError("training_target_required", 400)
    if theme is not None and theme not in THEMES_BY_CODE:
        raise PuzzleError("unknown_theme", 400, theme=theme)
    if section is not None and section not in SECTIONS:
        raise PuzzleError("unknown_section", 400, section=section)
    if stage is not None and stage not in STAGES:
        raise PuzzleError("invalid_stage", 400, stage=stage)
    if goal is not None and goal not in PUZZLE_GOALS:
        raise PuzzleError("unknown_goal", 400, goal=goal)
    if theme is not None and stage is None:
        progress = await _progress(db, user.id, theme)
        stage = min(progress.stage, STAGES[-1]) if progress else 1
    codes = [theme] if theme is not None else [t.code for t in THEMES if section is None or t.section == section]
    recent = await _recent_ids(db, user.id)
    # A mixed selection is by the player's rating, the window widens; by theme the stage sets the difficulty.
    windows: tuple[int | None, ...] = (None,) if stage is not None else (300, 600, None)
    for exclude, window in ((e, w) for e in (True, False) for w in windows):
        query = select(Puzzle).join(PuzzleTheme).where(PuzzleTheme.theme.in_(codes))
        if goal is not None:
            query = query.where(goal_clause(goal))
        if stage is not None:
            query = query.where(Puzzle.stage == stage)
        elif window is not None:
            query = query.where(Puzzle.rating.between(user.puzzle_rating - window, user.puzzle_rating + window))
        if exclude and recent:
            query = query.where(Puzzle.id.not_in(recent))
        puzzle = await db.scalar(query.order_by(func.random()).limit(1))
        if puzzle is not None:
            return puzzle, stage
    raise PuzzleError("no_puzzles_available", 404)


async def update_theme_progress(db: AsyncSession, user_id: int, theme: str, stage: int, clean: bool) -> dict:
    """
    Credit the result to a theme stage (a training puzzle or a defensive exercise 13.6); the commit is up to the caller.
    theme_progress.recent is a string of "1" (clean) and "0" over the last STAGE_WINDOW puzzles of the current stage; at
    STAGE_PASS ones the stage is passed and the window is cleared; after the last stage the theme is mastered (mastered).
    solved is the counter of all cleanly solved puzzles of the theme, at any stage.
    """
    progress = await _progress(db, user_id, theme)
    if progress is None:
        progress = ThemeProgress(user_id=user_id, theme=theme, stage=1, recent="", solved=0, mastered=False)
        db.add(progress)
    advanced = False
    # The result is credited to the stage the player is currently passing (repeating a passed stage does not interfere).
    if stage == progress.stage and not progress.mastered:
        progress.recent = (progress.recent + ("1" if clean else "0"))[-STAGE_WINDOW:]
        if progress.recent.count("1") >= STAGE_PASS:
            advanced = True
            progress.recent = ""
            if progress.stage >= STAGES[-1]:
                progress.mastered = True
            else:
                progress.stage += 1
    if clean:
        progress.solved += 1
    return {"theme": theme, "stage": progress.stage, "recent": progress.recent, "mastered": progress.mastered,
            "advanced": advanced, "window": STAGE_WINDOW, "pass": STAGE_PASS}


async def demo_puzzles(db: AsyncSession, theme: str, count: int = 2) -> list[dict]:
    """
    Showing a technique on the board: the most popular puzzles of the theme from the easiest stage - together with the
    solution. This is not an attempt: no session is created, rating and history do not change.
    """
    if theme not in THEMES_BY_CODE:
        raise PuzzleError("unknown_theme", 400, theme=theme)
    rows = await db.execute(
        select(Puzzle).join(PuzzleTheme).where(PuzzleTheme.theme == theme)
        .order_by(Puzzle.stage, Puzzle.popularity.desc(), Puzzle.plays.desc(), Puzzle.id).limit(count)
    )
    return [{"fen": p.fen, "moves": p.moves.split(), "color": solver_color(p)} for p in rows.scalars()]


async def training_overview(db: AsyncSession, user: User) -> dict:
    """
    Progress across all themes and how many puzzles exist at each stage (a theme is ready to be served when the minimums
    are met: at each stage at least as many puzzles as are set for the theme in the registry - themes.Theme.minimums).
    """
    counts = await stage_counts(db)
    rows = await db.execute(select(ThemeProgress).where(ThemeProgress.user_id == user.id))
    progress = {p.theme: p for p in rows.scalars()}
    themes = []
    for theme in THEMES:
        own = progress.get(theme.code)
        available = [counts.get((theme.code, stage), 0) for stage in STAGES]
        themes.append({
            "code": theme.code,
            "section": theme.section,
            "stage": own.stage if own else 1,
            "recent": own.recent if own else "",
            "solved": own.solved if own else 0,
            "mastered": bool(own and own.mastered),
            "available": available,
            "ready": all(n >= minimum for n, minimum in zip(available, theme.minimums, strict=True)),
        })
    return {"window": STAGE_WINDOW, "pass": STAGE_PASS, "themes": themes}


# --- timed mode ---------------------------------------------------------------------------------------------

def _run_key(user_id: int) -> str:
    return f"puzzle:run:{user_id}"


async def _load_run(user_id: int) -> dict | None:
    raw = await redis_module.redis_client.get(_run_key(user_id))
    return json.loads(raw) if raw else None


async def _save_run(user_id: int, run: dict) -> None:
    """Saves the run in Redis until its end plus 10 minutes (at least a minute): the result can be collected later too."""
    ttl = int(run["ends_at"] - time.time()) + 600
    await redis_module.redis_client.set(_run_key(user_id), json.dumps(run), ex=max(ttl, 60))


def _run_view(run: dict) -> dict:
    return {
        "run_id": run["id"], "minutes": run["minutes"], "solved": run["solved"], "mistakes": run["mistakes"],
        "seconds_left": max(0, round(run["ends_at"] - time.time())), "over": _run_over(run),
    }


def _run_over(run: dict) -> bool:
    """The run is over: TIMED_MISTAKES mistakes or time ran out (with grace TIMED_GRACE_S). The clock is the server's."""
    return run["mistakes"] >= TIMED_MISTAKES or time.time() > run["ends_at"] + TIMED_GRACE_S


async def start_run(user: User, minutes: int) -> dict:
    """
    Starts a timed run (minutes - from TIMED_MINUTES): the player's previous run and active puzzle are cancelled.
    The run remembers the starting difficulty - the solver's rating at the moment of start plus TIMED_START_OFFSET.
    """
    if minutes not in TIMED_MINUTES:
        raise PuzzleError("invalid_timed_minutes", 400, minutes=minutes)
    run = {"id": uuid.uuid4().hex, "minutes": minutes, "ends_at": time.time() + minutes * 60,
           "solved": 0, "mistakes": 0, "base": user.puzzle_rating + TIMED_START_OFFSET}
    await _save_run(user.id, run)
    await _drop_session(user.id)
    return _run_view(run)


async def next_in_run(db: AsyncSession, user: User) -> tuple[Puzzle, dict]:
    """
    The next puzzle of a timed run: its difficulty grows with the number solved (TIMED_STEP). No run or it has ended -
    refusal.
    """
    run = await _load_run(user.id)
    if run is None:
        raise PuzzleError("timed_run_not_active", 409)
    if _run_over(run):
        raise PuzzleError("timed_run_over", 409)
    target = max(600, run["base"] + TIMED_STEP * run["solved"])
    puzzle = await pick_puzzle(db, user, target_rating=target)
    await start(user, puzzle, run=run["id"])
    return puzzle, _run_view(run)


async def _count_in_run(user_id: int, run_id: str, solved: bool) -> dict | None:
    """
    Credits a puzzle to the run: solved - score, not - mistake. A puzzle finished after the end of the run is not
    counted. None - there is no run any more or the puzzle was started in another run.
    """
    run = await _load_run(user_id)
    if run is None or run["id"] != run_id:
        return None
    if not _run_over(run):
        run["solved" if solved else "mistakes"] += 1
        await _save_run(user_id, run)
    return _run_view(run)


async def finish_run(db: AsyncSession, user: User) -> dict:
    """
    Run result: score, record for these minutes, whether it is a new record. The run and the active puzzle are deleted; the
    record (users.puzzle_best_3 or puzzle_best_5) is updated only if the score is strictly greater than the previous one.
    Whether the run has ended is not checked: it can be finished early too.
    """
    run = await _load_run(user.id)
    if run is None:
        raise PuzzleError("timed_run_not_active", 409)
    await redis_module.redis_client.delete(_run_key(user.id))
    await _drop_session(user.id)
    field = f"puzzle_best_{run['minutes']}"
    best = getattr(user, field)
    record = run["solved"] > best
    if record:
        setattr(user, field, run["solved"])
    await puzzle_leaders.record_week(db, user.id, run["minutes"], run["solved"])
    await db.commit()
    return {"score": run["solved"], "mistakes": run["mistakes"], "minutes": run["minutes"],
            "best": max(best, run["solved"]), "new_record": record}


async def _active(db: AsyncSession, user: User, puzzle_id: int) -> tuple[PuzzleSession, Puzzle]:
    """The player's active puzzle and its record; a move on a puzzle that is not active now is a refusal puzzle_not_active."""
    session = await _load_session(user.id)
    if session is None or session.puzzle_id != puzzle_id:
        raise PuzzleError("puzzle_not_active", 409, puzzle_id=puzzle_id)
    puzzle = await db.get(Puzzle, puzzle_id)
    if puzzle is None:
        await _drop_session(user.id)
        raise PuzzleError("puzzle_not_found", 404, puzzle_id=puzzle_id)
    return session, puzzle


def _board_at(puzzle: Puzzle, index: int) -> chess.Board:
    """Position before the solution move number index: the initial position plus the first index moves from moves."""
    board = chess.Board(puzzle.fen)
    for uci in puzzle.moves.split()[:index]:
        board.push_uci(uci)
    return board


def rating_delta(user_rating: int, puzzle_rating: int, games: int, solved: bool, hints: int) -> int:
    """
    Change in the solver's rating by the Elo formula against the puzzle's rating: K x (result - expectation), K = 40 for
    the first PROVISIONAL_GAMES puzzles, then 20. For a solved puzzle the gain is multiplied by HINT_FACTORS by the number
    of hints; the deduction for an unsolved one does not depend on hints.
    """
    k = 40 if games < PROVISIONAL_GAMES else 20
    expected = 1 / (1 + 10 ** ((puzzle_rating - user_rating) / 400))
    delta = k * ((1 if solved else 0) - expected)
    if solved:
        delta *= HINT_FACTORS[min(hints, len(HINT_FACTORS) - 1)]
    return round(delta)


async def streak(db: AsyncSession, user_id: int) -> int:
    """Puzzles solved in a row without hints - from the last attempt backwards (no more than 500 attempts are scanned)."""
    rows = await db.execute(
        select(PuzzleAttempt.solved, PuzzleAttempt.hints_used).where(PuzzleAttempt.user_id == user_id)
        .order_by(PuzzleAttempt.created_at.desc(), PuzzleAttempt.id.desc()).limit(500)
    )
    count = 0
    for solved, hints in rows:
        if not solved or hints:
            break
        count += 1
    return count


async def _finish(db: AsyncSession, user: User, puzzle: Puzzle, session: PuzzleSession, solved: bool) -> dict:
    """
    Finishing a puzzle with one commit: the solver's rating (not in a run and not in a course; not below MIN_RATING), the
    attempt record in puzzle_attempts, theme progress in training (clean - solved without hints) and a product metrics event.
    After the commit the active puzzle is deleted from Redis, and a run puzzle is credited to its score.
    """
    before = user.puzzle_rating
    if session.run is None and session.course is None:
        delta = rating_delta(before, puzzle.rating, user.puzzle_games, solved, session.hints)
        user.puzzle_rating = max(MIN_RATING, before + delta)
        user.puzzle_games += 1
    db.add(PuzzleAttempt(user_id=user.id, puzzle_id=puzzle.id, solved=solved, hints_used=session.hints,
                         rating_before=before, rating_after=user.puzzle_rating))
    training = None
    if session.training and session.stage:
        training = await update_theme_progress(db, user.id, session.training, session.stage,
                                          clean=solved and session.hints == 0)
    await product_metrics.record_event(db, user.id, product_metrics.PUZZLE_ATTEMPT)
    await db.commit()
    await _drop_session(user.id)
    run = await _count_in_run(user.id, session.run, solved) if session.run else None
    return {
        "run": run,
        "training": training,
        "solved": solved,
        "rating_before": before,
        "rating_after": user.puzzle_rating,
        "delta": user.puzzle_rating - before,
        "streak": await streak(db, user.id),
        "themes": puzzle.theme_codes,
    }


async def play(db: AsyncSession, user: User, puzzle_id: int, uci: str) -> dict:
    """
    The solver's move: correct - the opponent's reply or the result; wrong - the result with the solution. A correct move
    is the database solution move or any move that gives mate. An illegal move is a refusal illegal_move, and the puzzle
    stays active.
    """
    session, puzzle = await _active(db, user, puzzle_id)
    moves = puzzle.moves.split()
    board = _board_at(puzzle, session.index)
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        raise DomainValueError("illegal_move", move=uci) from None
    if move not in board.legal_moves:
        raise DomainValueError("illegal_move", move=uci)

    board.push(move)
    correct = uci == moves[session.index] or board.is_checkmate()
    if not correct:
        solution = moves[session.index:]
        return {"correct": False, "done": True, "reply": None, "solution": solution,
                "result": await _finish(db, user, puzzle, session, solved=False)}

    session.index += 1
    if board.is_checkmate() or session.index >= len(moves):
        return {"correct": True, "done": True, "reply": None, "solution": None,
                "result": await _finish(db, user, puzzle, session, solved=True)}
    reply = moves[session.index]
    session.index += 1
    if session.index >= len(moves):
        # The database solution always ends with the solver's move; in case of a different record the puzzle is solved.
        return {"correct": True, "done": True, "reply": reply, "solution": None,
                "result": await _finish(db, user, puzzle, session, solved=True)}
    await _save_session(user.id, session)
    return {"correct": True, "done": False, "reply": reply, "solution": None, "result": None}


async def hint(db: AsyncSession, user: User, puzzle_id: int) -> dict:
    """Hint: the first - the square of the piece to move; the second - also the square where. Each reduces the gain."""
    session, puzzle = await _active(db, user, puzzle_id)
    expected = puzzle.moves.split()[session.index]
    session.hints = min(session.hints + 1, len(HINT_FACTORS) - 1)
    await _save_session(user.id, session)
    return {"from": expected[:2], "to": expected[2:4] if session.hints >= 2 else None, "hints_used": session.hints}


async def give_up(db: AsyncSession, user: User, puzzle_id: int) -> dict:
    """Show solution": the puzzle counts as unsolved, the solution in full."""
    session, puzzle = await _active(db, user, puzzle_id)
    solution = puzzle.moves.split()[session.index:]
    return {"solution": solution, "result": await _finish(db, user, puzzle, session, solved=False)}


async def profile(db: AsyncSession, user: User, limit: int = 30) -> dict:
    """
    The solver's rating, puzzle count, streak, run records for 3 and 5 minutes and the last limit attempts - newest first
    (for the chart and history).
    """
    rows = await db.execute(
        select(PuzzleAttempt, Puzzle.rating).join(Puzzle, Puzzle.id == PuzzleAttempt.puzzle_id)
        .where(PuzzleAttempt.user_id == user.id)
        .order_by(PuzzleAttempt.created_at.desc(), PuzzleAttempt.id.desc()).limit(limit)
    )
    history = [
        {"puzzle_id": attempt.puzzle_id, "puzzle_rating": rating, "solved": attempt.solved,
         "hints_used": attempt.hints_used, "rating_after": attempt.rating_after,
         "created_at": attempt.created_at.isoformat() if attempt.created_at else None}
        for attempt, rating in rows
    ]
    return {"rating": user.puzzle_rating, "games": user.puzzle_games, "streak": await streak(db, user.id),
            "best": {"3": user.puzzle_best_3, "5": user.puzzle_best_5}, "history": history}
