# --- FILE: src/services/product_metrics.py ---
"""
Product metrics without third-party trackers (task 23.5).

Events are written to their own table product_events (kind, player, UTC day) - at most once a day per kind and player.
The owner's report (scripts/product_metrics.py) computes from them:
* registrations by day;
* activation - the share of new players who played a first game within ACTIVATION_FAST_S of registration and on the first day;
* retention D1/D7/D30 - the share of the registration cohort active exactly 1, 7 and 30 days later;
* how many players reached puzzles, lessons and tournaments.

Who writes events: registration (src/api/auth.py), the end of a game with a human (game_state.py) and with a bot (api/bots.py),
a puzzle solution attempt (puzzles.py), a completed lesson (api/learn.py), tournament creation (tournaments.py); "was
seen today" - the request token check (src/api/deps.py). Redis: ``product:active:{date}:{user_id}`` -
a "already recorded today" mark so as not to hit the database on every request. The content of actions (moves, texts,
addresses) does not go into events.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.product_event import ProductEvent

logger = logging.getLogger(__name__)

REGISTERED = "registered"
ACTIVE = "active"
GAME_FINISHED = "game_finished"
PUZZLE_ATTEMPT = "puzzle_attempt"
LESSON_COMPLETED = "lesson_completed"
TOURNAMENT_CREATED = "tournament_created"
EVENT_KINDS = (REGISTERED, ACTIVE, GAME_FINISHED, PUZZLE_ATTEMPT, LESSON_COMPLETED, TOURNAMENT_CREATED)

ACTIVATION_FAST_S = 5 * 60  # "fast activation": the first finished game within the first 5 minutes after registration
RETENTION_DAYS = (1, 7, 30)  # retention days D1, D7, D30


def utc_today() -> date:
    """Current day in UTC - the unit of event accounting (the product_events.day column)."""
    return datetime.now(UTC).date()


async def record_event(db: AsyncSession, user_id: int | None, kind: str) -> None:
    """
    Records an event in the caller's transaction (savepoint: a repeat within a day rolls back only it). Does not commit -
    the event is saved together with the action that caused it. An accounting failure does not break the action. A guest
    (user_id None) and a kind not in EVENT_KINDS are silently skipped. A repeat within a day is rejected by the table's
    unique index.
    """
    if user_id is None or kind not in EVENT_KINDS:
        return
    try:
        async with db.begin_nested():
            db.add(ProductEvent(kind=kind, user_id=user_id, day=utc_today()))
    except IntegrityError:
        pass  # already recorded today
    except Exception as exc:
        logger.warning("Product event %s for user %s not recorded: %s", kind, user_id, exc)


ACTIVE_MARK_TTL_S = 2 * 86400  # the Redis mark lives two days: with a margin for the day it represents


async def mark_active(session_factory: async_sessionmaker[AsyncSession], user_id: int) -> None:
    """
    "Player was seen today" - for retention. Redis lets only the first mark of a day through (no extra DB writes);
    the write is in its own short session: a request that commits nothing (GET) would lose it.
    """
    from src.db import redis as redis_module

    try:
        first_today = await redis_module.redis_client.set(
            f"product:active:{utc_today().isoformat()}:{user_id}", "1", nx=True, ex=ACTIVE_MARK_TTL_S,
        )
    except Exception:
        first_today = True  # without Redis - we write: the unique index will prevent duplicates
    if not first_today:
        return
    try:
        async with session_factory() as db:
            await record_event(db, user_id, ACTIVE)
            await db.commit()
    except Exception as exc:
        logger.warning("Active mark for user %s failed: %s", user_id, exc)


@dataclass
class Cohort:
    """
    A cohort is the players registered on day day: how many there are, how many finished their first game within
    ACTIVATION_FAST_S and within the first 24 hours, how many were active exactly N days later (retained: N -> number of
    players).
    """

    day: date
    registered: int = 0
    activated_fast: int = 0
    activated_day: int = 0
    retained: dict[int, int] = field(default_factory=dict)


@dataclass
class Report:
    """Report: cohorts by day, players who reached each section, and the total of players with a registration event."""

    cohorts: list[Cohort]
    reached: dict[str, int]
    total_users: int


async def build_report(db: AsyncSession, since: date, until: date | None = None) -> Report:
    """
    Registration cohorts from since to until (inclusive) and how many players ever reached the sections.

    Reads the whole product_events table (the report is run by the owner with a script, not by a player's request). "First
    game" is the earliest game_finished event of the player; a day with any event other than registration counts as active.
    reached and total_users - over all time, not over the selected days. Players registered before accounting appeared
    have no registration event and do not enter the cohorts.
    """
    until = until or utc_today()
    rows = (await db.execute(
        select(ProductEvent.user_id, ProductEvent.kind, ProductEvent.day, ProductEvent.created_at)
    )).all()
    registered_at: dict[int, datetime] = {}
    first_game: dict[int, datetime] = {}
    active_days: dict[int, set[date]] = {}
    reached: dict[str, set[int]] = {k: set() for k in (GAME_FINISHED, PUZZLE_ATTEMPT, LESSON_COMPLETED, TOURNAMENT_CREATED)}
    for user_id, kind, day, created_at in rows:
        created_at = created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else created_at
        if kind == REGISTERED:
            registered_at[user_id] = created_at
        elif kind == ACTIVE:
            active_days.setdefault(user_id, set()).add(day)
        if kind in reached:
            reached[kind].add(user_id)
        if kind == GAME_FINISHED and (user_id not in first_game or created_at < first_game[user_id]):
            first_game[user_id] = created_at
        if kind != REGISTERED:
            active_days.setdefault(user_id, set()).add(day)  # any action - an active day

    cohorts: dict[date, Cohort] = {}
    day = since
    while day <= until:
        cohorts[day] = Cohort(day, retained={n: 0 for n in RETENTION_DAYS})
        day += timedelta(days=1)
    for user_id, at in registered_at.items():
        cohort = cohorts.get(at.date())
        if cohort is None:
            continue
        cohort.registered += 1
        game = first_game.get(user_id)
        if game is not None:
            delay = (game - at).total_seconds()
            cohort.activated_fast += delay <= ACTIVATION_FAST_S
            cohort.activated_day += delay <= 86400
        days = active_days.get(user_id, set())
        for n in RETENTION_DAYS:
            cohort.retained[n] += (at.date() + timedelta(days=n)) in days
    return Report(
        cohorts=list(cohorts.values()),
        reached={kind: len(users) for kind, users in reached.items()},
        total_users=len(registered_at),
    )
