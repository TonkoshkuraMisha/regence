# --- FILE: src/services/weekly_legends.py ---
"""
The weekly tournament against legends (task 26.1): the week's line-up, starting a game, counting it and the standings.
The pure rules (the week, the choice of legends, points, ranking) are in src/services/weekly_legends_rules.py.

Fairness works like the club ladder and bot tournaments (src/services/ladder.py): POST /events/weekly-legends/start
opens a fair-game session in Redis with the scope SCOPE ("weekly"); while it is open the bot move and analysis endpoints
mark a hint, a takeback or a swapped opponent. The result is counted only from the saved game (POST /bots/save-game with
weekly=true, src/api/bots.py): check_save before the game is written, record_result in the same transaction. A game with
a hint, the coach, a wrong time control, or one abandoned by starting another legend counts as a loss - a weekly game
cannot be "not counted", otherwise a bad game could simply be dropped.

Data: the weekly_legend_games table (one row per player, week and legend); the week of a game is the week its session
was opened. Players with a closed account, bots and players flagged for unfair play do not enter the standings. Every
Monday the task weekly_legends_results (src/worker/tasks.py) sends last week's participants their place
(notification kind weekly_legends).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainError
from src.models.user import User
from src.models.weekly_legends import WeeklyLegendGame
from src.services import account_state, ladder, notifications
from src.services import weekly_legends_rules as rules

# The fair-game session scope of a weekly game (a key in ladder.SCOPES).
SCOPE = "weekly"
# Why a weekly game was counted as a loss: the ladder reasons plus the ones of this module.
FORFEIT_REASONS = (*ladder.LADDER_REASONS, "coach", "time_control", "abandoned")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def legends(start: dt.date) -> list[str]:
    """The week's legends: historical bots of the club ladder, one per strength band (rules.pick_legends)."""
    bots = [(rung.id, rung.rating) for rung in ladder.rungs() if rung.kind == "historical"]
    return rules.pick_legends(start, bots)


def _week_of(moment: float | dt.datetime) -> dt.date:
    when = moment if isinstance(moment, dt.datetime) else dt.datetime.fromtimestamp(moment, dt.UTC)
    return rules.week_start(when.astimezone(dt.UTC).date())


async def _played(db: AsyncSession, user_id: int, start: dt.date) -> dict[str, WeeklyLegendGame]:
    rows = (await db.execute(select(WeeklyLegendGame).where(
        WeeklyLegendGame.user_id == user_id, WeeklyLegendGame.week == start))).scalars().all()
    return {row.bot_id: row for row in rows}


async def _record(db: AsyncSession, user_id: int, start: dt.date, bot_id: str, half_points: int,
                  forfeit: str | None, game_id: int | None) -> WeeklyLegendGame | None:
    """Adds the counted game (without commit); a legend already counted this week is left as it is (None)."""
    if bot_id in await _played(db, user_id, start):
        return None
    row = WeeklyLegendGame(week=start, user_id=user_id, bot_id=bot_id, half_points=half_points, forfeit=forfeit,
                           game_id=game_id)
    db.add(row)
    return row


async def _forfeit_open_game(db: AsyncSession, user: User) -> str | None:
    """An open weekly game that was started (a move was requested) counts as a loss; returns its legend."""
    session = await ladder.get_session(user.id, SCOPE)
    if session is None or session.max_ply < 0:
        return None
    await _record(db, user.id, _week_of(session.started_at), session.rung_key, rules.HALF_POINTS["loss"], "abandoned",
                  None)
    return session.rung_key


async def start_game(db: AsyncSession, user: User, bot_id: str, color: str, now: dt.datetime | None = None) -> dict:
    """
    Opens a weekly game with a legend of this week: 404 weekly_legend_unknown for another bot, 409 weekly_legend_played
    for one already played. A previously started weekly game is counted as an abandoned loss first. Returns the opponent,
    the colour, the time control and the abandoned legend (if any).
    """
    start = rules.week_start((now or _now()).date())
    if bot_id not in legends(start):
        raise DomainError("weekly_legend_unknown")
    abandoned = await _forfeit_open_game(db, user)
    await db.commit()
    if bot_id in await _played(db, user.id, start):
        await ladder.clear_session(user.id, SCOPE)
        raise DomainError("weekly_legend_played")
    await ladder.open_session(user.id, bot_id, color, scope=SCOPE)
    return {"bot_id": bot_id, "color": color, "base_time_ms": rules.BASE_TIME_MS, "increment_ms": rules.INCREMENT_MS,
            "abandoned": abandoned}


async def check_save(user: User, bot_id: str) -> ladder.LadderSession:
    """Before a weekly game is saved: there must be an open weekly session with this legend (400 weekly_no_session)."""
    session = await ladder.get_session(user.id, SCOPE)
    if session is None or session.rung_key != bot_id:
        raise DomainError("weekly_no_session")
    return session


@dataclass
class WeeklyOutcome:
    """How a saved weekly game was counted: points (0, 0.5, 1), the forfeit reason and the player's week total."""
    points: float
    forfeit: str | None
    total: float

    def as_dict(self) -> dict:
        return asdict(self)


async def record_result(db: AsyncSession, user: User, session: ladder.LadderSession, result: str, color: str,
                        coach_used: bool, base_time_ms: int, increment_ms: int, game_id: int) -> WeeklyOutcome:
    """
    Counts a saved weekly game (without commit; the caller clears the session after it): the session's hint reason,
    the coach or a time control other than the weekly one turn it into a loss.
    """
    forfeit = session.assisted or ("coach" if coach_used else None)
    if forfeit is None and (base_time_ms, increment_ms) != (rules.BASE_TIME_MS, rules.INCREMENT_MS):
        forfeit = "time_control"
    half = rules.HALF_POINTS["loss"] if forfeit else rules.player_half_points(result, color)
    start = _week_of(session.started_at)
    row = await _record(db, user.id, start, session.rung_key, half, forfeit, game_id)
    await db.flush()
    total = sum(r.half_points for r in (await _played(db, user.id, start)).values())
    return WeeklyOutcome(points=(row.half_points if row else half) / 2, forfeit=forfeit, total=total / 2)


async def _entries(db: AsyncSession, start: dt.date) -> list[tuple[rules.Entry, User]]:
    """Every eligible player's week (open account, not a bot, not flagged), in standings order."""
    rows = (await db.execute(
        select(WeeklyLegendGame.user_id, func.sum(WeeklyLegendGame.half_points),
               func.sum(case((WeeklyLegendGame.half_points == rules.HALF_POINTS["win"], 1), else_=0)),
               func.count(WeeklyLegendGame.id), func.max(WeeklyLegendGame.created_at), User)
        .join(User, User.id == WeeklyLegendGame.user_id)
        .where(WeeklyLegendGame.week == start, User.is_bot.is_(False), User.is_cheater.is_(False),
               *account_state.open_account())
        .group_by(WeeklyLegendGame.user_id, User.id)
    )).all()
    users = {row[0]: row[5] for row in rows}
    entries = [rules.Entry(user_id=r[0], half_points=int(r[1] or 0), wins=int(r[2] or 0), games=int(r[3]),
                           reached_at=r[4]) for r in rows]
    return [(entry, users[entry.user_id]) for entry in rules.rank(entries)]


def _row(place: int, entry: rules.Entry, user: User) -> dict:
    return {"place": place, "username": user.username, "avatar": user.avatar, "points": entry.half_points / 2,
            "wins": entry.wins, "games": entry.games}


async def standings(db: AsyncSession, start: dt.date, user_id: int | None) -> dict:
    """The week's table: the first rules.TOP places, the player's own row and the number of participants."""
    ranked = await _entries(db, start)
    mine = next((_row(i + 1, e, u) for i, (e, u) in enumerate(ranked) if e.user_id == user_id), None)
    return {"top": [_row(i + 1, e, u) for i, (e, u) in enumerate(ranked[:rules.TOP])], "me": mine,
            "players": len(ranked)}


async def event(db: AsyncSession, user: User | None, now: dt.datetime | None = None) -> dict:
    """
    This week's event for the page and the lobby banner: the end, the time control, the legends (with the player's result
    for each), the open game, the standings and last week's winner.
    """
    moment = now or _now()
    start = rules.week_start(moment.date())
    played = await _played(db, user.id, start) if user else {}
    session = await ladder.get_session(user.id, SCOPE) if user else None
    last = await standings(db, start - dt.timedelta(days=7), None)
    strength = {rung.id: rung.rating for rung in ladder.rungs() if rung.kind == "historical"}
    return {
        "week": start.isoformat(), "ends_at": rules.week_end(start).isoformat(),
        "base_time_ms": rules.BASE_TIME_MS, "increment_ms": rules.INCREMENT_MS,
        "legends": [
            {"bot_id": bot_id, "rating": strength.get(bot_id),
             "points": played[bot_id].half_points / 2 if bot_id in played else None,
             "forfeit": played[bot_id].forfeit if bot_id in played else None}
            for bot_id in legends(start)
        ],
        "open_game": session.rung_key if session else None,
        "standings": await standings(db, start, user.id if user else None),
        "last_winner": last["top"][0] if last["top"] else None,
    }


async def notify_results(db: AsyncSession, now: dt.datetime | None = None) -> int:
    """
    Last week's places to its participants (the Monday task): a weekly_legends notification with the place, points and
    the number of players. Sent once: a participant who already has the notification for that week is skipped.
    """
    from src.models.social import Notification

    start = rules.week_start((now or _now()).date()) - dt.timedelta(days=7)
    ranked = await _entries(db, start)
    week = start.isoformat()
    sent_to = set((await db.execute(select(Notification.user_id).where(
        Notification.kind == "weekly_legends", Notification.payload["week"].as_string() == week))).scalars().all())
    sent = 0
    for place, (entry, _user) in enumerate(ranked, start=1):
        if entry.user_id in sent_to:
            continue
        await notifications.record(db, entry.user_id, "weekly_legends",
                                   {"week": week, "place": place, "points": entry.half_points / 2,
                                    "players": len(ranked)}, commit=False)
        sent += 1
    await db.commit()
    return sent
