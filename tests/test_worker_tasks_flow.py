"""
Задачи Celery (src/worker/tasks.py) без Stockfish: службы подменены, проверяются порядок вызовов,
повтор при занятом пуле движков, поведение при сбоях и постановка следующих партий турнира.
Задачи вызываются напрямую (как функции) — каждая запускает свой asyncio.run, как в живом воркере;
база — файловая sqlite во временной папке теста.
"""

import asyncio
import logging

import pytest
from celery.exceptions import Retry
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.models.base import Base
from src.models.imported_game import ImportedGame
from src.models.user import User
from src.services.engine_pool import EngineBusyError
from src.worker import tasks


@pytest.fixture(autouse=True)
def task_db(tmp_path, monkeypatch):
    """Каждая задача получает файловую базу sqlite с созданными таблицами."""
    url = f"sqlite+aiosqlite:///{(tmp_path / 'flow.db').as_posix()}"

    async def create():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(create())
    monkeypatch.setattr(tasks, "_task_database_url", lambda: url)
    return url


def _recorder(calls: list, name: str, result=None, error: Exception | None = None):
    async def fake(*args, **kwargs):
        calls.append(name)
        if error:
            raise error
        return result

    return fake


def _patch_analysis(monkeypatch, calls, *, index_error=None, puzzles_error=None, rival_error=None, report=None):
    monkeypatch.setattr(tasks.position_index, "index_by_id", _recorder(calls, "index", error=index_error))
    monkeypatch.setattr(
        tasks.analysis_service, "analyze_full_game", _recorder(calls, "analyze", result=report or {"moves": []})
    )
    monkeypatch.setattr(tasks.personal_puzzles, "extract_for_game", _recorder(calls, "puzzles", error=puzzles_error))
    monkeypatch.setattr(tasks.bot_memory, "record_rival_errors", _recorder(calls, "rival", error=rival_error))


def test_analyze_game_runs_all_steps_in_order(monkeypatch):
    calls: list[str] = []
    _patch_analysis(monkeypatch, calls, report={"moves": [1]})
    assert tasks.analyze_game_task(5) == {"moves": [1]}
    assert calls == ["index", "analyze", "puzzles", "rival"]


def test_analyze_game_survives_side_step_failures(monkeypatch, caplog):
    calls: list[str] = []
    _patch_analysis(
        monkeypatch, calls, index_error=RuntimeError("i"), puzzles_error=RuntimeError("p"), rival_error=RuntimeError("r")
    )
    with caplog.at_level(logging.ERROR):
        assert tasks.analyze_game_task(5) == {"moves": []}
    assert calls == ["index", "analyze", "puzzles", "rival"]
    assert "Position indexing failed" in caplog.text
    assert "Personal puzzles extraction failed" in caplog.text
    assert "Bot rival errors update failed" in caplog.text


def test_analyze_game_returns_error_status_when_analysis_fails(monkeypatch):
    monkeypatch.setattr(tasks.position_index, "index_by_id", _recorder([], "index"))
    monkeypatch.setattr(tasks.analysis_service, "analyze_full_game", _recorder([], "a", error=RuntimeError("boom")))
    assert tasks.analyze_game_task(9) == {"game_id": 9, "status": "error"}


def test_analyze_game_retries_when_engine_busy_in_puzzles(monkeypatch):
    calls: list[str] = []
    _patch_analysis(monkeypatch, calls, puzzles_error=EngineBusyError("busy"))
    with pytest.raises((Retry, EngineBusyError)):
        tasks.analyze_game_task(5)


def test_analyze_imported_game_missing_row_gives_zero():
    assert tasks.analyze_imported_game_task(404) == 0


def test_analyze_imported_game_analyzes_and_extracts(monkeypatch, task_db):
    async def seed() -> int:
        engine = create_async_engine(task_db)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            user = User(username="imp_user", hashed_password="x")
            db.add(user)
            await db.flush()
            row = ImportedGame(user_id=user.id, source="pgn", external_id="x1", color="white", pgn="1. e4 *")
            db.add(row)
            await db.commit()
            row_id = row.id
        await engine.dispose()
        return row_id

    row_id = asyncio.run(seed())
    calls: list[str] = []
    monkeypatch.setattr(tasks.game_import, "analyze", _recorder(calls, "analyze"))
    monkeypatch.setattr(tasks.personal_puzzles, "extract_for_imported", _recorder(calls, "extract", result=3))
    assert tasks.analyze_imported_game_task(row_id) == 3
    assert calls == ["analyze", "extract"]


def test_analyze_imported_game_failure_gives_zero(monkeypatch):
    async def boom(_id):
        raise RuntimeError("x")

    monkeypatch.setattr(tasks, "_analyze_imported_game_async", boom)
    assert tasks.analyze_imported_game_task(1) == 0


def test_analyze_imported_game_retries_when_engine_busy(monkeypatch):
    async def busy(_id):
        raise EngineBusyError("busy")

    monkeypatch.setattr(tasks, "_analyze_imported_game_async", busy)
    with pytest.raises((Retry, EngineBusyError)):
        tasks.analyze_imported_game_task(1)


def test_simulate_tournament_game_queues_follow_ups(monkeypatch):
    monkeypatch.setattr(tasks.tournament_simulation, "simulate", _recorder([], "sim", result=[11, 12]))
    published: list[tuple] = []
    monkeypatch.setattr(
        tasks.simulate_tournament_game_task, "apply_async", lambda args=None, **kw: published.append((args, kw))
    )
    tasks.simulate_tournament_game_task(10)
    assert published == [((11,), {"retry": False}), ((12,), {"retry": False})]


def test_simulate_tournament_game_failure_is_logged_not_raised(monkeypatch, caplog):
    monkeypatch.setattr(tasks.tournament_simulation, "simulate", _recorder([], "sim", error=RuntimeError("x")))
    with caplog.at_level(logging.ERROR):
        assert tasks.simulate_tournament_game_task(10) is None
    assert "simulation failed" in caplog.text


def test_simulate_tournament_game_retries_when_engine_busy(monkeypatch):
    monkeypatch.setattr(tasks.tournament_simulation, "simulate", _recorder([], "sim", error=EngineBusyError("b")))
    with pytest.raises((Retry, EngineBusyError)):
        tasks.simulate_tournament_game_task(10)


def test_workout_reminders_returns_sent_count(monkeypatch, caplog):
    from src.services import workout

    monkeypatch.setattr(workout, "send_reminders", _recorder([], "w", result=4))
    with caplog.at_level(logging.INFO):
        assert tasks.workout_reminders() == 4
    assert "Workout reminders sent: 4" in caplog.text


@pytest.mark.parametrize("sent", [0, 2])
def test_arena_reminders(monkeypatch, sent):
    from src.services import arena

    monkeypatch.setattr(arena, "send_reminders", _recorder([], "a", result=sent))
    assert tasks.arena_reminders() == sent


def test_bot_selfplay_counts_games(monkeypatch):
    from src.services.bots import selfplay

    monkeypatch.setattr(selfplay, "run", _recorder([], "s", result=3))
    assert tasks.bot_selfplay() == 3


def test_bot_selfplay_skips_when_engine_busy(monkeypatch):
    from src.services.bots import selfplay

    monkeypatch.setattr(selfplay, "run", _recorder([], "s", error=EngineBusyError("b")))
    assert tasks.bot_selfplay() == 0


@pytest.mark.parametrize("count", [0, 5])
def test_archive_move_telemetry(monkeypatch, count):
    from src.services import telemetry_retention

    monkeypatch.setattr(telemetry_retention, "archive_old_moves", _recorder([], "t", result=count))
    assert tasks.archive_move_telemetry() == count


@pytest.mark.parametrize("count", [0, 2])
def test_review_cheater_flags(monkeypatch, count):
    from src.services import moderation

    monkeypatch.setattr(moderation, "periodic_flag_review", _recorder([], "m", result=count))
    assert tasks.review_cheater_flags() == count


@pytest.mark.parametrize("count", [0, 1])
def test_arena_awards(monkeypatch, count):
    from src.services import arena_awards

    monkeypatch.setattr(arena_awards, "award_finished", _recorder([], "w", result=count))
    assert tasks.arena_awards() == count


def test_task_database_url_comes_from_settings(monkeypatch):
    monkeypatch.undo()
    assert tasks._task_database_url() == tasks.settings.async_database_url
