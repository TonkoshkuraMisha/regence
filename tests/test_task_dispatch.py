# --- FILE: tests/test_task_dispatch.py ---
"""
Enqueueing Celery tasks from async code must not block the event loop: previously
analyze_game_task.delay() went straight into the loop and hung the whole worker when the broker was unavailable.
"""

import asyncio
import threading
import time

from src.services import task_dispatch
from src.worker.tasks import analyze_game_task


async def _max_loop_stall(coro) -> tuple[object, float]:
    """Runs coro and measures the longest pause the event loop stalled for."""
    ticks: list[float] = []
    done = asyncio.Event()

    async def ticker():
        while not done.is_set():
            ticks.append(time.monotonic())
            await asyncio.sleep(0.01)

    ticker_task = asyncio.create_task(ticker())
    try:
        result = await coro
    finally:
        done.set()
        await ticker_task
    gaps = [b - a for a, b in zip(ticks, ticks[1:], strict=False)] or [0.0]
    return result, max(gaps)


async def test_publish_runs_in_a_thread(no_celery_publish):
    assert await task_dispatch.schedule_game_analysis(7) is True
    assert no_celery_publish == [7]


async def test_slow_broker_does_not_block_event_loop(monkeypatch):
    release = threading.Event()

    def hanging_publish(game_id):
        release.wait(5)  # the broker "hangs" for longer than the publish timeout

    monkeypatch.setattr(task_dispatch, "_publish_analysis", hanging_publish)
    monkeypatch.setattr(task_dispatch.settings, "CELERY_PUBLISH_TIMEOUT_S", 0.3)

    published, stall = await _max_loop_stall(task_dispatch.schedule_game_analysis(8))
    release.set()

    assert published is False
    assert stall < 0.2  # the loop kept working while the thread waited for the broker


async def test_broker_failure_starts_cooldown(monkeypatch):
    calls: list[int] = []

    def failing_publish(game_id):
        calls.append(game_id)
        raise ConnectionError("broker is down")

    monkeypatch.setattr(task_dispatch, "_publish_analysis", failing_publish)

    assert await task_dispatch.schedule_game_analysis(1) is False
    # While the pause lasts, new publications do not try to reach the broker and do not spawn threads.
    assert await task_dispatch.schedule_game_analysis(2) is False
    assert calls == [1]

    task_dispatch.reset_broker_cooldown()
    assert await task_dispatch.schedule_game_analysis(3) is False
    assert calls == [1, 3]


async def test_background_scheduling_returns_immediately(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(task_dispatch, "_publish_analysis", lambda game_id: release.wait(5))

    started = time.monotonic()
    task = task_dispatch.schedule_game_analysis_in_background(9)
    assert time.monotonic() - started < 0.05
    assert task in task_dispatch._background_tasks  # the reference is held, so GC will not collect the task

    release.set()
    assert await task is True
    assert task not in task_dispatch._background_tasks


def test_task_is_bound_to_project_celery_app():
    """With @shared_task the API process published to amqp://localhost instead of the Redis broker."""
    assert analyze_game_task.app.main == "regence_worker"
    assert analyze_game_task.app.conf.broker_url.startswith("redis://")
    assert analyze_game_task.ignore_result is True
