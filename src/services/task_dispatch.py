# --- FILE: src/services/task_dispatch.py ---
"""
Queueing Celery background tasks from async code.

apply_async/delay is a synchronous network call to the broker. Made directly in the event loop, with a
slow or unavailable broker it hung the whole worker: moves, clocks and all WebSockets stood still
while kombu tried to connect (about 4 s for every finished game).

Here the publishing:
* goes in a thread (asyncio.to_thread) and is not awaited by the caller - the game result is broadcast at once;
* has no publish retries and uses a short connection timeout (see celery_app) so that the thread
  does not hang for long;
* after a broker failure is skipped for CELERY_BROKER_COOLDOWN_S: otherwise every finished
  game would spawn another hung thread. The game analysis is optional - it can still
  be computed on request on the game page.

Called by: src/services/game_state.py and src/api/bots.py (game analysis), src/api/bots.py and src/api/tournaments.py
(tournament bot games), src/api/game_import.py (review of imported games). The tasks themselves are in src/worker/tasks.py.
Settings: CELERY_PUBLISH_TIMEOUT_S, CELERY_BROKER_COOLDOWN_S (src/core/config.py).
"""

import asyncio
import logging
import time

from src.core.config import settings
from src.worker.tasks import analyze_game_task, analyze_imported_game_task, simulate_tournament_game_task

logger = logging.getLogger(__name__)

# Moment (time.monotonic) until which publishing is skipped after a broker failure; shared by all kinds of tasks.
_broker_down_until = 0.0
# Strong references to background tasks: without them the event loop may collect a task before it finishes.
_background_tasks: set[asyncio.Task] = set()


def _publish_analysis(game_id: int) -> None:
    """Synchronous publishing of a game analysis task; called in a thread, without retries."""
    analyze_game_task.apply_async(args=(game_id,), retry=False)


async def schedule_game_analysis(game_id: int) -> bool:
    """Queues a game's background analysis. Returns True if the task was published."""
    global _broker_down_until

    if time.monotonic() < _broker_down_until:
        logger.debug("Broker cooldown: skipping analysis task for game %s", game_id)
        return False

    try:
        await asyncio.wait_for(
            asyncio.to_thread(_publish_analysis, game_id),
            timeout=settings.CELERY_PUBLISH_TIMEOUT_S,
        )
        return True
    except Exception as exc:  # including asyncio.TimeoutError
        _broker_down_until = time.monotonic() + settings.CELERY_BROKER_COOLDOWN_S
        logger.error(
            "Could not schedule analysis task for game %s (%s); skipping publishes for %s s",
            game_id, exc.__class__.__name__, settings.CELERY_BROKER_COOLDOWN_S,
        )
        return False


def schedule_game_analysis_in_background(game_id: int) -> asyncio.Task:
    """Starts queueing a task without waiting for it. The reference to the task is kept until it finishes."""
    task = asyncio.create_task(schedule_game_analysis(game_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def reset_broker_cooldown() -> None:
    """Lifts the pause after a broker failure (needed by tests so that one test's failure does not silence the others)."""
    global _broker_down_until
    _broker_down_until = 0.0


def _publish_simulation(tournament_game_id: int) -> None:
    """Synchronous publishing of a tournament game simulation task; called in a thread, without retries."""
    simulate_tournament_game_task.apply_async(args=(tournament_game_id,), retry=False)


async def schedule_tournament_simulations(tournament_game_ids: list[int]) -> int:
    """
    Queues bot-vs-bot games (task 15.2). Returns the number published. With an unavailable broker
    the games are not lost: they stay without a result, and the next tournament state request will queue them again.
    """
    global _broker_down_until

    published = 0
    for game_id in tournament_game_ids:
        if time.monotonic() < _broker_down_until:
            break
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_publish_simulation, game_id), timeout=settings.CELERY_PUBLISH_TIMEOUT_S,
            )
            published += 1
        except Exception as exc:
            _broker_down_until = time.monotonic() + settings.CELERY_BROKER_COOLDOWN_S
            logger.error("Could not schedule tournament game %s (%s)", game_id, exc.__class__.__name__)
    return published


def schedule_tournament_simulations_in_background(tournament_game_ids: list[int]) -> asyncio.Task | None:
    """Starts queueing simulations without waiting for it; None - nothing to queue."""
    if not tournament_game_ids:
        return None
    task = asyncio.create_task(schedule_tournament_simulations(tournament_game_ids))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def _publish_imported_analysis(imported_id: int) -> None:
    """Synchronous publishing of an imported game review task; called in a thread, without retries."""
    analyze_imported_game_task.apply_async(args=(imported_id,), retry=False)


async def schedule_imported_analyses(imported_ids: list[int]) -> int:
    """
    Review of games from other sites (task 24.1). Returns the number published. With an unavailable broker games are not
    lost: the review can be started from the game page, and the import list will show "not reviewed".
    """
    global _broker_down_until

    published = 0
    for imported_id in imported_ids:
        if time.monotonic() < _broker_down_until:
            break
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_publish_imported_analysis, imported_id), timeout=settings.CELERY_PUBLISH_TIMEOUT_S,
            )
            published += 1
        except Exception as exc:
            _broker_down_until = time.monotonic() + settings.CELERY_BROKER_COOLDOWN_S
            logger.error("Could not schedule imported game %s (%s)", imported_id, exc.__class__.__name__)
    return published


def schedule_imported_analyses_in_background(imported_ids: list[int]) -> asyncio.Task | None:
    """Starts queueing import reviews without waiting for it; None - nothing to queue."""
    if not imported_ids:
        return None
    task = asyncio.create_task(schedule_imported_analyses(imported_ids))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
