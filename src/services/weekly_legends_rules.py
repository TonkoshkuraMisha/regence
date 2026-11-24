# --- FILE: src/services/weekly_legends_rules.py ---
"""
Rules of the weekly tournament against legends (task 26.1), without a database or network - so a plain test checks them.

Every week (Monday 00:00 UTC to the next Monday) the same LEGENDS_PER_WEEK historical bots are open to every registered
player - the openness rule: no rating thresholds. The legends are spread over strength: the historical bots are sorted by
their measured strength (the same order as the club ladder, src/services/ladder.py) and cut into LEGENDS_PER_WEEK bands;
the week picks one bot from each band by a hash of the week, so the line-up changes every week, is the same for everybody
and needs no stored schedule.

Each legend can be played once a week, at the fixed time control (BASE_TIME_MS + INCREMENT_MS). Points are counted in
half-points (win 2, draw 1, loss 0) so that sums stay integers. The standings order: more points, then more wins, then the
earlier moment of reaching the score (the one who got there first is higher).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

# How many legends a week offers (one from each strength band).
LEGENDS_PER_WEEK = 5
# The time control of every weekly game: rapid 10+5 - long enough to play a legend properly.
BASE_TIME_MS = 10 * 60 * 1000
INCREMENT_MS = 5 * 1000
# Half-points for the player's result.
HALF_POINTS = {"win": 2, "draw": 1, "loss": 0}
# How many places the standings show (plus the player's own row).
TOP = 20


def week_start(day: dt.date) -> dt.date:
    """Monday of the week the day falls into (UTC)."""
    return day - dt.timedelta(days=day.weekday())


def week_end(start: dt.date) -> dt.datetime:
    """The moment the week ends: the next Monday at 00:00 UTC."""
    return dt.datetime.combine(start + dt.timedelta(days=7), dt.time(), tzinfo=dt.UTC)


def pick_legends(start: dt.date, bots: Sequence[tuple[str, int]], count: int = LEGENDS_PER_WEEK) -> list[str]:
    """
    The week's legends from (bot id, strength) pairs: one from each of `count` strength bands, weakest band first. The
    choice inside a band depends only on the week and the bot ids, so every server process picks the same line-up.
    """
    ordered = sorted(bots, key=lambda b: (b[1], b[0]))
    if len(ordered) <= count:
        return [bot_id for bot_id, _ in ordered]
    picked = []
    for band in range(count):
        members = ordered[band * len(ordered) // count:(band + 1) * len(ordered) // count]
        seed = hashlib.sha256(f"{start.isoformat()}:{band}".encode()).digest()
        picked.append(members[int.from_bytes(seed[:4], "big") % len(members)][0])
    return picked


def player_half_points(result: str, color: str) -> int:
    """Half-points of the player with `color` for a PGN result ("1-0", "0-1", "1/2-1/2")."""
    if result == "1/2-1/2":
        return HALF_POINTS["draw"]
    won = (result == "1-0") == (color == "white")
    return HALF_POINTS["win" if won else "loss"]


@dataclass(frozen=True)
class Entry:
    """One player's week: half-points, wins, games and the moment the last game was counted."""
    user_id: int
    half_points: int
    wins: int
    games: int
    reached_at: dt.datetime


def rank(entries: Sequence[Entry]) -> list[Entry]:
    """The standings: more points, then more wins, then who reached the score earlier."""
    return sorted(entries, key=lambda e: (-e.half_points, -e.wins, e.reached_at, e.user_id))
