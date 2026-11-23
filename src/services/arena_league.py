# --- FILE: src/services/arena_league.py ---
"""
Monthly arena league (task 33.5, docs/research/arenas.md §7): a table of players by the sum of arena points in a season in one
time-control category. It does not affect the rating — it is only a monthly standing.

Rules:

* the season is a calendar month in UTC (league.season_bounds, as in the Conference Cup); an arena belongs to the season in
  which it
  started;
* only arenas (format "arena") count towards the league: a Swiss has different points (per game, without "fire" streaks), and
  adding them
  to arena points would be unfair;
* the category is classify_time_control of the arena's time control; league tabs are the categories in which the schedule
  (arena_schedule.DAY_PLAN and WEEK_PLAN) creates arenas at all, so a new scheduled arena gives its own league by itself;
* the player's points are the sum of arena_players.score over arenas (each division is its own arena); the table lists
  participants with at least
  one game played. Order: points, then best arena, then fewer arenas (the same points over fewer
  tournaments), then name.

Data source: tables arenas and arena_players; computed on request (GET /arenas/league), nothing is stored.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import get_args

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.arena import Arena, ArenaPlayer
from src.models.user import RatingCategory, User
from src.services.arena_schedule import DAY_PLAN, WEEK_PLAN
from src.services.league import season_bounds
from src.services.rating import classify_time_control

# Tournament format whose points count towards the league.
LEAGUE_FORMAT = "arena"
# How many table rows the server returns; the player's own row arrives separately, even if it is lower.
TABLE_SIZE = 50

# Categories in which the schedule creates arenas, in RatingCategory order (bullet, blitz, rapid, classical).
_SCHEDULED = {classify_time_control(slot.base_time_ms, slot.increment_ms)
              for slot in [s for _, s in DAY_PLAN] + [s for _, _, s in WEEK_PLAN] if slot.format == LEAGUE_FORMAT}
LEAGUE_CATEGORIES: tuple[RatingCategory, ...] = tuple(c for c in get_args(RatingCategory) if c in _SCHEDULED)


@dataclass(frozen=True)
class Entry:
    """A player's season result in one category: sum of points, best arena, number of arenas with games."""
    user_id: int
    username: str
    score: int
    best: int
    arenas: int


def rank(entries: list[Entry]) -> list[dict]:
    """League table by the module rules: rows {"place", "user_id", "username", "score", "best", "arenas"}."""
    ordered = sorted(entries, key=lambda e: (-e.score, -e.best, e.arenas, e.username))
    return [{"place": index + 1, "user_id": e.user_id, "username": e.username, "score": e.score, "best": e.best,
             "arenas": e.arenas} for index, e in enumerate(ordered)]


async def league(db: AsyncSession, category: RatingCategory, season: str | None = None,
                 user_id: int | None = None, now: datetime | None = None) -> dict:
    """
    Season league in a category: {"season", "category", "categories", "players", "table" (first TABLE_SIZE), "me"} —
    me: the row of the signed-in player (None — not signed in or no games in this season). season defaults to the current one.
    """
    key, start, end = season_bounds(season, now)
    arenas = (await db.execute(select(Arena.id, Arena.base_time_ms, Arena.increment_ms).where(
        Arena.format == LEAGUE_FORMAT, Arena.starts_at >= start, Arena.starts_at < end))).all()
    ids = [arena_id for arena_id, base, inc in arenas if classify_time_control(base, inc) == category]
    entries: list[Entry] = []
    if ids:
        rows = (await db.execute(
            select(ArenaPlayer.user_id, User.username, func.sum(ArenaPlayer.score), func.max(ArenaPlayer.score),
                   func.count(ArenaPlayer.id))
            .join(User, User.id == ArenaPlayer.user_id)
            .where(ArenaPlayer.arena_id.in_(ids), ArenaPlayer.games > 0)
            .group_by(ArenaPlayer.user_id, User.username)
        )).all()
        entries = [Entry(uid, name, int(score), int(best), int(count)) for uid, name, score, best, count in rows]
    table = rank(entries)
    me = next((row for row in table if row["user_id"] == user_id), None) if user_id is not None else None
    return {"season": key, "category": category, "categories": list(LEAGUE_CATEGORIES), "players": len(table),
            "table": table[:TABLE_SIZE], "me": me}
