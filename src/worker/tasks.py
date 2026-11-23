# --- FILE: src/worker/tasks.py ---
"""
Celery background tasks.

* analyze_game - the engine review of a just-finished game (the result goes to games.analysis_json), personal puzzles
  from the players' mistakes (src/services/personal_puzzles.py) and laying the game out into the position index
  (src/services/position_index.py), and for a game with a historical bot - where the opponent makes mistakes
  (src/services/bots/memory.py, record_rival_errors). analyze_imported_game - review and puzzles for a game from another site.
* simulate_tournament_game - a bot-vs-bot game in a tournament; after it the next games are queued.
* workout_reminders, arena_reminders, arena_awards, bot_selfplay, archive_move_telemetry, review_cheater_flags - scheduled
  (the schedule is src/worker/celery_app.py).

Every task runs in its own event loop and creates its own database connection (asyncpg connections are bound
to the loop they were created in). Tasks with an engine need a free Stockfish process from the pool: if the pool is busy,
the review and the tournament game are postponed by ENGINE_BUSY_RETRY_S seconds and retried - at most five times
(max_retries), after which the task is dropped (the review can then be requested from the game page, and the tournament game
will be queued again by opening the tournament page). Self-play with a busy pool simply skips the run.
Tasks are queued by src/services/task_dispatch.py.
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.services import game_import, personal_puzzles, position_index, tournament_simulation
from src.services.analysis_service import analysis_service
from src.services.bots import memory as bot_memory
from src.services.engine_pool import EngineBusyError, engine_work

# The task is bound to our Celery application explicitly. With @shared_task an API process in which celery_app
# was never imported published via the default application - to amqp://localhost:5672
# instead of the Redis broker, and the background analysis never reached the worker.
from src.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

ENGINE_BUSY_RETRY_S = 15


def _task_database_url() -> str:
    """The database address for tasks. A separate function - so that tests can substitute their own database address."""
    return settings.async_database_url


async def _prewarm_game_analysis_async(game_id: int) -> dict:
    """
    Performs the background computation and caching of a full game analysis after it finishes: first lays the game out
    into the position index, then computes the review (saved to games.analysis_json; a ready one is not recomputed) and from
    it - personal puzzles from the players' mistakes. Returns the review report.

    Each Celery task runs in its own event loop (asyncio.run), and asyncpg connections
    are bound to the loop they were created in. The application's global engine with a connection
    pool cannot be used here: from the second task the worker would get
    "attached to a different loop". So each task gets its own engine without a pool, closed at the end.
    """
    engine = create_async_engine(_task_database_url(), poolclass=NullPool)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as db:
            # The position index (task 16.1) does not depend on the engine - before analysis: a busy engine does not postpone
            # it.
            try:
                await position_index.index_by_id(db, game_id)
            except Exception:
                await db.rollback()
                logger.exception("Position indexing failed for game %s", game_id)
            report = await analysis_service.analyze_full_game(db, game_id, force=False)
            # Puzzles from the player's mistakes (task 13.5) - from the ready review; a failure here does not cancel the
            # review.
            try:
                await personal_puzzles.extract_for_game(db, game_id)
            except EngineBusyError:
                raise
            except Exception:
                logger.exception("Personal puzzles extraction failed for game %s", game_id)
            # Where the opponent of a historical bot makes mistakes (32.2) - from the same review; a failure does not cancel
            # the review.
            try:
                await bot_memory.record_rival_errors(db, game_id)
            except Exception:
                await db.rollback()
                logger.exception("Bot rival errors update failed for game %s", game_id)
            return report
    finally:
        await engine.dispose()


# ignore_result: the result is written to the DB (Game.analysis_json), while the result backend, when publishing,
# subscribes to the reply - with Redis unavailable that is ~64 s of reconnections, after which
# the backend breaks until the process restarts ("The Celery application must be restarted").
@celery_app.task(name="analyze_game", bind=True, max_retries=5, ignore_result=True)
def analyze_game_task(self, game_id: int):
    """
    The Celery task "analyze_game": the background review of a finished game (with a human or with a bot). It is queued by
    game_state.finish_game and POST /bots/save-game via src/services/task_dispatch.py. Engine time goes into the metric
    regence_engine_seconds_total with the label analysis. Any other failure is only written to the log: the review
    is optional, it can be requested from the game page.
    """
    try:
        with engine_work("analysis"):
            return asyncio.run(_prewarm_game_analysis_async(game_id))
    except EngineBusyError as exc:
        # All engines are busy - we do not lose the analysis but postpone it: up to five attempts with a pause of
        # ENGINE_BUSY_RETRY_S.
        raise self.retry(exc=exc, countdown=ENGINE_BUSY_RETRY_S) from exc
    except Exception:
        logger.exception("Background analysis task failed for game %s", game_id)
        return {"game_id": game_id, "status": "error"}


async def _analyze_imported_game_async(imported_id: int) -> int:
    """A review of a game from another site (task 24.1) and personal puzzles from it; returns the number of new puzzles."""
    from src.models.imported_game import ImportedGame

    engine = create_async_engine(_task_database_url(), poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            game = await db.get(ImportedGame, imported_id)
            if game is None:
                return 0
            await game_import.analyze(db, game)
            return await personal_puzzles.extract_for_imported(db, imported_id)
    finally:
        await engine.dispose()


@celery_app.task(name="analyze_imported_game", bind=True, max_retries=5, ignore_result=True)
def analyze_imported_game_task(self, imported_id: int):
    """
    The Celery task: a review of an imported game. When the engine pool is busy it is postponed by ENGINE_BUSY_RETRY_S and
    retried.
    """
    try:
        with engine_work("analysis"):
            return asyncio.run(_analyze_imported_game_async(imported_id))
    except EngineBusyError as exc:
        raise self.retry(exc=exc, countdown=ENGINE_BUSY_RETRY_S) from exc
    except Exception:
        logger.exception("Imported game analysis failed for %s", imported_id)
        return 0


async def _simulate_tournament_game_async(tournament_game_id: int) -> list[int]:
    engine = create_async_engine(_task_database_url(), poolclass=NullPool)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as db:
            return await tournament_simulation.simulate(db, tournament_game_id)
    finally:
        await engine.dispose()


@celery_app.task(name="simulate_tournament_game", bind=True, max_retries=5, ignore_result=True)
def simulate_tournament_game_task(self, tournament_game_id: int):
    """A bot-vs-bot game in a tournament (task 15.2); the next games of the round are queued here too."""
    try:
        with engine_work("simulation"):
            follow_up = asyncio.run(_simulate_tournament_game_async(tournament_game_id))
    except EngineBusyError as exc:
        raise self.retry(exc=exc, countdown=ENGINE_BUSY_RETRY_S) from exc
    except Exception:
        logger.exception("Tournament game simulation failed for %s", tournament_game_id)
        return
    for game_id in follow_up:
        simulate_tournament_game_task.apply_async(args=(game_id,), retry=False)


async def _workout_reminders_async() -> int:
    engine = create_async_engine(_task_database_url(), poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            from src.services import workout

            return await workout.send_reminders(db, workout.utcnow())
    finally:
        await engine.dispose()


@celery_app.task(name="workout_reminders", ignore_result=True)
def workout_reminders() -> int:
    """Warm-up reminders (task 22.2) - on the celery beat schedule."""
    sent = asyncio.run(_workout_reminders_async())
    logger.info("Workout reminders sent: %s", sent)
    return sent


async def _arena_reminders_async() -> int:
    engine = create_async_engine(_task_database_url(), poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            from src.services import arena

            sent = await arena.send_reminders(db)
            await db.commit()
            return sent
    finally:
        await engine.dispose()


@celery_app.task(name="arena_reminders", ignore_result=True)
def arena_reminders() -> int:
    """Arena start reminders (task 33.4) - on the celery beat schedule, once a minute."""
    sent = asyncio.run(_arena_reminders_async())
    if sent:
        logger.info("Arena reminders sent: %s", sent)
    return sent


async def _bot_selfplay_async() -> int:
    engine = create_async_engine(_task_database_url(), poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            from src.services.bots import selfplay

            return await selfplay.run(db)
    finally:
        await engine.dispose()


@celery_app.task(name="bot_selfplay", ignore_result=True)
def bot_selfplay() -> int:
    """Archetype self-play (task 32.3) - on the celery beat schedule, in the simulation queue (CPU work)."""
    try:
        with engine_work("simulation"):
            played = asyncio.run(_bot_selfplay_async())
    except EngineBusyError:
        logger.info("Bot self-play skipped: the engine pool is busy")
        return 0
    logger.info("Bot self-play games: %s", played)
    return played


async def _archive_move_telemetry_async() -> int:
    engine = create_async_engine(_task_database_url(), poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            from src.services import telemetry_retention

            return await telemetry_retention.archive_old_moves(db)
    finally:
        await engine.dispose()


@celery_app.task(name="archive_move_telemetry", ignore_result=True)
def archive_move_telemetry() -> int:
    """
    Raw moves rows older than the appeal period - into the game summary and delete (src/services/telemetry_retention.py);
    on the celery beat schedule once a day.
    """
    archived = asyncio.run(_archive_move_telemetry_async())
    if archived:
        logger.info("Move telemetry archived for %s games", archived)
    return archived


async def _review_flags_async() -> int:
    engine = create_async_engine(_task_database_url(), poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            from src.services import moderation

            return await moderation.periodic_flag_review(db)
    finally:
        await engine.dispose()


@celery_app.task(name="review_cheater_flags", ignore_result=True)
def review_cheater_flags() -> int:
    """Review of old unfair-play flags (task 26.4, moderation.periodic_flag_review) - once a week."""
    created = asyncio.run(_review_flags_async())
    if created:
        logger.info("Periodic cheat-flag reviews queued: %s", created)
    return created


async def _arena_awards_async() -> int:
    engine = create_async_engine(_task_database_url(), poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            from src.services import arena_awards

            return await arena_awards.award_finished(db)
    finally:
        await engine.dispose()


@celery_app.task(name="arena_awards", ignore_result=True)
def arena_awards() -> int:
    """Prize places of finished arenas (task 33.5, src/services/arena_awards.py) - on the celery beat schedule."""
    awarded = asyncio.run(_arena_awards_async())
    if awarded:
        logger.info("Arena awards given: %s", awarded)
    return awarded
