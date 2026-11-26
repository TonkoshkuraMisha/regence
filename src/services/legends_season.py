# --- FILE: src/services/legends_season.py ---
"""
Season table of the weekly legends tournament (task 26.1): the weeks of a season add up.

A season is a calendar month, the same as the team league's (league.season_bounds). It contains the legends weeks whose
Monday falls inside the month (a week is never split between two seasons), up to the current week. Every week is ranked by
legends_week.week_ranking (the place of the player's best finished run of the week's event); the week then gives a player
WEEK_POINTS for their place in that week's table (first ten places, like motor racing) plus FINISH_POINTS for any finished
run, so taking part always counts. The season ranks players by the sum of points, then by the number of weeks won, then by
name; players equal on points and wins share the place.

No table of its own: everything is derived from tournaments (like the weekly table), so no migration. Violators, bots and
deleted accounts are already left out of the weekly tables. The texts are on the client (timeMachine.legendsSeason.*).
"""

import datetime as dt
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from src.services import legends_week
from src.services.league import season_bounds

# Points for places 1-10 of a weekly table; lower places get only the finish points.
WEEK_POINTS = (25, 18, 15, 12, 10, 8, 6, 4, 2, 1)
# Points for any finished run of the week's event: taking part counts even outside the top ten.
FINISH_POINTS = 1


def week_points(place: int) -> int:
    """Season points for a place in a weekly table: WEEK_POINTS for the top ten plus FINISH_POINTS for finishing."""
    return (WEEK_POINTS[place - 1] if 1 <= place <= len(WEEK_POINTS) else 0) + FINISH_POINTS


def season_mondays(start: dt.date, end: dt.date, today: dt.date) -> list[dt.date]:
    """Mondays in [start, end) that are not later than the current week's Monday: the weeks counted in the season."""
    last = min(end - dt.timedelta(days=1), legends_week.week_window(today)[0])
    monday = start + dt.timedelta(days=(-start.weekday()) % 7)  # the first Monday on or after the season start
    mondays = []
    while monday <= last:
        mondays.append(monday)
        monday += legends_week.WEEK
    return mondays


def season_table(weeks: Iterable[list[dict]]) -> list[dict]:
    """
    Sums the weekly tables ([{place, user_id, username}] each) into the season table: [{place, user_id, username, points,
    wins, weeks}] by points, then weeks won, then name; equal points and wins share the place (1, 2, 2, 4).
    """
    totals: dict[int, dict] = {}
    for week in weeks:
        for row in week:
            entry = totals.setdefault(row["user_id"], {"user_id": row["user_id"], "username": row["username"],
                                                       "points": 0, "wins": 0, "weeks": 0})
            entry["points"] += week_points(row["place"])
            entry["wins"] += row["place"] == 1
            entry["weeks"] += 1
    ordered = sorted(totals.values(), key=lambda e: (-e["points"], -e["wins"], e["username"]))
    for index, entry in enumerate(ordered):
        previous = ordered[index - 1]
        tied = index > 0 and (previous["points"], previous["wins"]) == (entry["points"], entry["wins"])
        entry["place"] = previous["place"] if tied else index + 1
    return ordered


async def standings(db: AsyncSession, user_id: int | None = None, season: str | None = None,
                    today: dt.date | None = None) -> dict:
    """
    The season table: {season, weeks: [Monday ISO dates counted], rows: [{place, username, points, wins, weeks, me}], me}.
    `rows` has the legends_week.TOP best; `me` is the player's own row even below the top (None without a finished run).
    """
    key, start, end = season_bounds(season)
    mondays = season_mondays(start.date(), end.date(), today or dt.datetime.now(dt.UTC).date())
    ranked = season_table([await legends_week.week_ranking(db, monday) for monday in mondays])

    def row(entry: dict) -> dict:
        return {"place": entry["place"], "username": entry["username"], "points": entry["points"], "wins": entry["wins"],
                "weeks": entry["weeks"], "me": entry["user_id"] == user_id}

    mine = next((e for e in ranked if e["user_id"] == user_id), None) if user_id is not None else None
    return {"season": key, "weeks": [m.isoformat() for m in mondays], "rows": [row(e) for e in ranked[:legends_week.TOP]],
            "me": row(mine) if mine else None}
