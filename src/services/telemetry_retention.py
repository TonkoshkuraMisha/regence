# --- FILE: src/services/telemetry_retention.py ---
"""
Move telemetry retention (task 9 of the owner's 18.11 plan, task 29.2): the moves table is only a buffer for the anti-cheat
(move time, window focus loss, premove, network delay; src/services/anticheat.py). The moves of the game itself are in the PGN,
the review is in games.analysis_json, so the raw moves rows are needed while the game can be reviewed again: RETENTION_DAYS
is the appeal period for a fair-play decision.

A scheduled task (src/worker/tasks.py -> archive_move_telemetry, the schedule is beat_schedule in celery_app.py) once a
day takes games finished before the cutoff that still have moves rows: adds the summary
games.telemetry_summary if anti-cheat did not write it (for example, a friendly game - it does not evaluate it), and
deletes the rows. In batches of BATCH games with a commit after each: an interrupted run continues from the next one.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.game import Game
from src.models.move import Move
from src.services.anticheat import telemetry_summary

# How many days a game's raw moves are kept after it ends - the appeal period for a fair-play decision.
RETENTION_DAYS = 90
# Games per transaction (and one commit): an interrupted run does not lose the batches already processed.
BATCH = 200


def cutoff(now: datetime | None = None) -> datetime:
    """Games finished before this moment no longer keep their raw moves."""
    return (now or datetime.now(UTC)) - timedelta(days=RETENTION_DAYS)


async def archive_old_moves(db: AsyncSession, now: datetime | None = None) -> int:
    """Summary + deletion of moves for games older than the cutoff; returns the number of processed games."""
    limit = cutoff(now)
    done = 0
    while True:
        games = list((await db.execute(
            select(Game).where(Game.finished_at.is_not(None), Game.finished_at < limit,
                               exists().where(Move.game_id == Game.id))
            .order_by(Game.id).limit(BATCH)
        )).scalars())
        if not games:
            return done
        ids = [game.id for game in games]
        moves = list((await db.execute(select(Move).where(Move.game_id.in_(ids)).order_by(Move.id))).scalars())
        for game in games:
            if game.telemetry_summary is None:
                game.telemetry_summary = telemetry_summary(game, [m for m in moves if m.game_id == game.id])
        await db.execute(delete(Move).where(Move.game_id.in_(ids)))
        await db.commit()
        done += len(games)
