# --- FILE: src/services/arena_awards.py ---
"""
Arena awards (task 33.5, task 10 of the owner's plan of 18.11). When the results of an arena or Swiss are final
(arena.status == "finished": time is up and all games are finished; for a Swiss, the last round has been played), the top three
of the
results table (arena.ranked) receive podium places — table arena_awards, notification "arena_podium" to each winner.
A place goes only to a player who has played at least one game. Each arena division has its own table and its own winners.

From the arena_awards records the profile trophies (gold, silver, bronze) and the "arena podium" and
"arena winner" achievements are computed (src/services/achievements.py). Awards are handed out by the scheduled task
arena_awards
(src/worker/tasks.py, schedule — beat_schedule in celery_app.py); an arena is checked until LOOKBACK has passed after its
announced end, and awarded once (an arena that already has records is skipped). place_of is the player's place from
the same records: the arena page uses it to show the podium celebration.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.arena import Arena, ArenaAward
from src.services import arena as arena_service
from src.services import notifications
from src.services.rating import classify_time_control

# How many places are awarded.
PODIUM = 3
# How long after the announced end an arena is still checked: an unfinished game could delay the results.
LOOKBACK = timedelta(days=3)
# Profile trophy keys by place (arena_awards.place is stored as a string).
MEDALS = {"1": "gold", "2": "silver", "3": "bronze"}


async def award_finished(db: AsyncSession, now: datetime | None = None) -> int:
    """Awards all arenas with final results that have not been awarded yet; returns the number of new awards (with commit)."""
    now = now or datetime.now(UTC)
    candidates = (await db.execute(select(Arena).where(
        or_(Arena.ends_at <= now, Arena.finished_at.is_not(None)),
        Arena.ends_at > now - LOOKBACK,
        Arena.format != "match",  # conference match is a team format: no trophies for an individual place in it
        ~exists().where(ArenaAward.arena_id == Arena.id),
    ).order_by(Arena.id))).scalars().all()
    added = 0
    for arena in candidates:
        open_games = await arena_service.open_games(db, arena.id)
        if arena_service.status(arena, now, open_games) != "finished":
            continue
        category = classify_time_control(arena.base_time_ms, arena.increment_ms)
        winners = [p for p, _, _ in await arena_service.ranked(db, arena.id) if p.games > 0][:PODIUM]
        for place, player in enumerate(winners, 1):
            db.add(ArenaAward(arena_id=arena.id, place=str(place), user_id=player.user_id, category=category))
            await notifications.record(db, player.user_id, "arena_podium",
                                       {"arena_id": arena.id, "place": place, "category": category}, commit=False)
            added += 1
    await db.commit()
    return added


async def trophies(db: AsyncSession, user_id: int) -> dict[str, int]:
    """Player trophies: {gold, silver, bronze} — the number of first, second and third places in arenas."""
    rows = (await db.execute(select(ArenaAward.place, func.count()).where(ArenaAward.user_id == user_id)
                             .group_by(ArenaAward.place))).all()
    counts = {medal: 0 for medal in MEDALS.values()}
    for place, count in rows:
        counts[MEDALS[place]] = count
    return counts


async def place_of(db: AsyncSession, arena_id: int, user_id: int) -> int | None:
    """The player's podium place in an arena (1-3) from arena_awards; None — not a winner or results not yet final."""
    place = await db.scalar(select(ArenaAward.place).where(ArenaAward.arena_id == arena_id,
                                                          ArenaAward.user_id == user_id))
    return int(place) if place is not None else None
