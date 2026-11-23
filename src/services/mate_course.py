# --- FILE: src/services/mate_course.py ---
"""
The mating pattern course (task 14.6): 20 patterns of catalogue section F in teaching order. Each has an explanation and two
demonstrations (catalogue texts and /puzzles/demo) and TASKS theme puzzles of increasing difficulty: theme puzzles by rating,
taken
evenly from the easiest to the hardest -- the set is constant while the database does not change. The course result is a
mixed check:
EXAM_SIZE puzzles of different patterns from the harder half of their sets.

The course puzzles are solved by the ordinary /puzzles/{id}/move but do not change the solver's rating: they can be taken
repeatedly.
The attempt is recorded in the history (puzzle_attempts) as for an ordinary puzzle.

Data: the puzzles and puzzle_themes tables (puzzles of the open lichess database, loaded by scripts/import_puzzles.py); the
course has no
tables of its own. Routes are in src/api/puzzles.py.
"""

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.puzzle import Puzzle, PuzzleTheme
from src.models.user import User
from src.services import puzzles as puzzles_service
from src.services.themes import THEMES_BY_CODE

# Codes of section F themes of the registry src/services/themes.py in study order: from simple mates to named ones.
COURSE: tuple[str, ...] = (
    "back_rank_mate", "corridor_mate", "smothered_mate", "arabian_mate", "anastasia_mate", "hook_mate",
    "epaulette_mate", "dovetail_mate", "queen_kiss_mate", "opera_mate", "boden_mate", "double_bishop_mate",
    "legal_mate", "greco_mate", "damiano_mate", "lolli_mate", "pillsbury_mate", "morphy_mate", "blackburne_mate",
    "vukovic_mate",
)
TASKS = 10  # puzzles in the set of one pattern (fewer if the database does not have that many for the theme)
EXAM_SIZE = 10  # puzzles in the final check: one per pattern, no more than the number of patterns with puzzles
EXAM_MINUTES = 10  # time for the check; the server only reports it to the client, the countdown is kept by the client

# Protection against a typo and against moving a theme to another registry section: the module will not load.
assert all(THEMES_BY_CODE[code].section == "F" for code in COURSE)


async def task_ids(db: AsyncSession, theme: str) -> list[int]:
    """Pattern puzzles from easy to hard: TASKS of them, evenly by theme rating."""
    rows = (await db.execute(
        select(Puzzle.id).join(PuzzleTheme).where(PuzzleTheme.theme == theme).order_by(Puzzle.rating, Puzzle.id)
    )).scalars().all()
    if len(rows) <= TASKS:
        return list(rows)
    return [rows[round(i * (len(rows) - 1) / (TASKS - 1))] for i in range(TASKS)]


async def overview(db: AsyncSession) -> dict:
    """The course patterns in order and how many puzzles each has (0 -- the pattern has no puzzles yet)."""
    return {
        "tasks": TASKS, "exam_size": EXAM_SIZE, "exam_minutes": EXAM_MINUTES,
        "constructions": [{"code": code, "available": len(await task_ids(db, code))} for code in COURSE],
    }


async def start_task(db: AsyncSession, user: User, theme: str, index: int) -> Puzzle:
    """
    Opens a mating pattern course puzzle by its number in the theme set. It is solved by an ordinary puzzle move
    (/puzzles/{id}/move) but does not change the solver's rating.
    """
    if theme not in COURSE:
        raise puzzles_service.PuzzleError("unknown_theme", 400, theme=theme)
    ids = await task_ids(db, theme)
    if not 0 <= index < len(ids):
        raise puzzles_service.PuzzleError("no_puzzles_available", 404)
    puzzle = await db.get(Puzzle, ids[index])
    assert puzzle is not None
    await puzzles_service.start(user, puzzle, course=theme)
    return puzzle


async def exam_plan(db: AsyncSession, rng: random.Random | None = None) -> list[dict]:
    """
    A mixed check: puzzles of different patterns (one each), from the harder half of each set. Patterns
    are chosen at random; if some of them have no puzzles, the check is shorter than EXAM_SIZE. Returns pairs "theme, puzzle
    number in the set" -- the client opens the puzzle itself via ``start_task``.
    """
    rng = rng or random.Random()
    pool = []
    for code in COURSE:
        count = len(await task_ids(db, code))
        if count:
            pool.append((code, count))
    rng.shuffle(pool)
    return [{"theme": code, "index": rng.randrange(count // 2, count)} for code, count in pool[:EXAM_SIZE]]
