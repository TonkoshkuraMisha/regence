# --- FILE: src/services/puzzle_leaders.py ---
"""
Leaderboard of timed runs (task 26.1, "puzzle competition"). Two standings for each run length (3 and 5 minutes):
"week" - the best scores of the current week (Monday UTC -> Monday; the puzzle_timed_scores table, which is filled by
record_week when a run finishes) and "all time" - players' records (users.puzzle_best_3 / puzzle_best_5). Fair-play
violators (is_cheater), bots and deleted accounts do not enter the table. A player also sees their own place if it is below
the top. Timed runs are played by the rules of puzzles.start_run; only accounting and output are here.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.puzzle import PuzzleTimedScore
from src.models.user import User
from src.services import account_state

# Run lengths the table is kept for (as puzzles.TIMED_MINUTES), and the standings.
MINUTES = (3, 5)
SCOPES = ("week", "all")
# How many places the table shows.
TOP = 20


def week_start(day: dt.date) -> dt.date:
    """Monday of the week the day falls into (UTC)."""
    return day - dt.timedelta(days=day.weekday())


def _eligible():
    """Who enters the table: live players without a violator mark."""
    return (User.is_cheater == False, User.is_bot == False, *account_state.open_account())  # noqa: E712


async def record_week(db: AsyncSession, user_id: int, minutes: int, score: int, today: dt.date | None = None) -> None:
    """
    Remembers a run's score in the weekly table: a player's row for the week keeps the best score. Without commit - the
    caller does it. One player's runs go one at a time (there is one run in Redis), so there is no race on the row.
    """
    if minutes not in MINUTES or score <= 0:
        return
    week = week_start(today or dt.datetime.now(dt.UTC).date())
    row = await db.scalar(select(PuzzleTimedScore).where(
        PuzzleTimedScore.user_id == user_id, PuzzleTimedScore.minutes == minutes, PuzzleTimedScore.week == week))
    if row is None:
        db.add(PuzzleTimedScore(user_id=user_id, minutes=minutes, week=week, score=score))
    elif score > row.score:
        row.score = score


def _ranked(rows: list[tuple[int, str, int]]) -> list[dict]:
    """Places by descending score; equal scores share a place (1, 2, 2, 4)."""
    out: list[dict] = []
    for index, (user_id, username, score) in enumerate(rows):
        place = out[-1]["place"] if out and out[-1]["score"] == score else index + 1
        out.append({"place": place, "user_id": user_id, "username": username, "score": score})
    return out


async def leaders(
        db: AsyncSession, minutes: int, scope: str, user_id: int | None = None, today: dt.date | None = None,
) -> dict:
    """
    Table {rows: [{place, username, score, me}], me: my row or None}. rows - the TOP top; me - the player's row,
    if they are in the standings (including below the top). An unknown length or standing gives an empty table.
    """
    if minutes not in MINUTES or scope not in SCOPES:
        return {"rows": [], "me": None}
    if scope == "week":
        week = week_start(today or dt.datetime.now(dt.UTC).date())
        query = (select(User.id, User.username, PuzzleTimedScore.score)
                 .join(PuzzleTimedScore, PuzzleTimedScore.user_id == User.id)
                 .where(PuzzleTimedScore.minutes == minutes, PuzzleTimedScore.week == week, *_eligible()))
        score_column = PuzzleTimedScore.score
    else:
        score_column = getattr(User, f"puzzle_best_{minutes}")
        query = select(User.id, User.username, score_column).where(score_column > 0, *_eligible())
    everyone = (await db.execute(query.order_by(score_column.desc(), User.username))).all()
    ranked = _ranked([(row[0], row[1], row[2]) for row in everyone])
    rows = [{"place": r["place"], "username": r["username"], "score": r["score"], "me": r["user_id"] == user_id}
            for r in ranked[:TOP]]
    mine = next((r for r in ranked if r["user_id"] == user_id), None) if user_id is not None else None
    me = {"place": mine["place"], "username": mine["username"], "score": mine["score"], "me": True} if mine else None
    return {"rows": rows, "me": me}
