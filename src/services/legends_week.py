# --- FILE: src/services/legends_week.py ---
"""
Weekly tournament against the legends (task 26.1, owner choice of 24.11.2026: each player plays their own run).

Every ISO week (Monday UTC -> Monday) has one "Time Machine" event, picked by a fixed rotation over time_machine.EVENTS, so the
whole community plays the same historical field that week. A player starts the tournament as usual (time_machine.start, the
`event_key` is the one announced for the week); nobody is paired with anybody else, so there is no waiting and no bot ever
enters the standings. The weekly table ranks players by the place they took in a finished run of this week's event
(`tournament_players.place`; the field is identical for everybody, so places are comparable). A player's best run of the week
counts. Runs are matched by `tournaments.created_at` inside the week, and only finished, not withdrawn runs count. Fair-play
violators, bots and deleted accounts are left out (as in puzzle_leaders). No table of its own: everything is derived from
tournaments, so no migration. The client shows the announcement and the table in the lobby; texts are on the client.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.tournament import Tournament, TournamentPlayer
from src.models.user import User
from src.services import account_state
from src.services.puzzle_leaders import week_start
from src.services.time_machine import EVENTS, Event

# How many places the weekly table shows.
TOP = 20
# Days in a week: the table is open from Monday 00:00 UTC to the next Monday.
WEEK = dt.timedelta(days=7)



def event_for_week(monday: dt.date) -> Event:
    """The legends event of the week starting on this Monday: a rotation over the registry, the same for everybody."""
    return EVENTS[monday.toordinal() // 7 % len(EVENTS)]


def week_window(today: dt.date | None = None) -> tuple[dt.date, dt.date]:
    """(Monday, next Monday) of the week of the given day (UTC today by default)."""
    monday = week_start(today or dt.datetime.now(dt.UTC).date())
    return monday, monday + WEEK


def _ranked(rows: list[tuple[int, str, int]]) -> list[dict]:
    """Places by ascending tournament place; players with the same place share it (1, 2, 2, 4)."""
    out: list[dict] = []
    for index, (user_id, username, place) in enumerate(rows):
        shared = out[-1]["place"] if out and out[-1]["score"] == place else index + 1
        out.append({"place": shared, "user_id": user_id, "username": username, "score": place})
    return out


async def standings(db: AsyncSession, user_id: int | None = None, today: dt.date | None = None) -> dict:
    """
    The announcement and the table of the week: {event_key, starts_on, ends_on, rows: [{place, username, tournament_place,
    me}], me: the player's own row or None}. `rows` has the TOP best; `me` is filled when the player has a finished run, even
    below the top.
    """
    monday, next_monday = week_window(today)
    event = event_for_week(monday)
    start = dt.datetime.combine(monday, dt.time.min, dt.UTC)
    end = dt.datetime.combine(next_monday, dt.time.min, dt.UTC)
    query = (select(User.id, User.username, TournamentPlayer.place)
             .join(TournamentPlayer, TournamentPlayer.user_id == User.id)
             .join(Tournament, Tournament.id == TournamentPlayer.tournament_id)
             .where(Tournament.event_key == event.key, Tournament.status == "finished", Tournament.withdrawn_at.is_(None),
                    Tournament.created_at >= start, Tournament.created_at < end, TournamentPlayer.place.is_not(None),
                    User.is_cheater == False, User.is_bot == False, *account_state.open_account()))  # noqa: E712
    everyone = (await db.execute(query.order_by(TournamentPlayer.place, User.username))).all()
    best: dict[int, tuple[int, str, int]] = {}
    for uid, username, place in everyone:
        best.setdefault(uid, (uid, username, place))
    ranked = _ranked(sorted(best.values(), key=lambda row: (row[2], row[1])))
    rows = [{"place": r["place"], "username": r["username"], "tournament_place": r["score"], "me": r["user_id"] == user_id}
            for r in ranked[:TOP]]
    mine = next((r for r in ranked if r["user_id"] == user_id), None) if user_id is not None else None
    me = None
    if mine:
        me = {"place": mine["place"], "username": mine["username"], "tournament_place": mine["score"], "me": True}
    return {"event_key": event.key, "starts_on": monday.isoformat(), "ends_on": next_monday.isoformat(), "rows": rows,
            "me": me}
