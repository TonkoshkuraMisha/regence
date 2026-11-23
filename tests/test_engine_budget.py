# --- FILE: tests/test_engine_budget.py ---
"""
Engine budget (task 23.3): engine time by kind of work, players per day for "CPU per player" and daily quotas
of the free tier on expensive work - disabled until FREE_TIER_LIMITS enables them.
"""

import asyncio

import pytest
from prometheus_client import REGISTRY

from src.api import analysis as analysis_api
from src.core import observability
from src.core.config import settings
from src.core.errors import DomainValueError
from src.services import engine_pool
from src.services.engine_pool import EngineBusyError, EnginePool, current_engine_work, engine_work

FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
HINT = {"fen": FEN, "step": 1, "final": False, "best_move_uci": None, "comment": [], "arrows": [], "highlights": []}


def sample(name: str, kind: str) -> float:
    return REGISTRY.get_sample_value(name, {"kind": kind}) or 0.0


def test_outer_kind_wins_and_unknown_is_other():
    assert current_engine_work() == "other"
    with engine_work("simulation"), engine_work("bot_move"):  # a bot move in a tournament simulation counts as simulation work
        assert current_engine_work() == "simulation"
    with engine_work("free-for-all"):
        assert current_engine_work() == "other"
    assert current_engine_work() == "other"


async def test_kind_reaches_the_engine_thread():
    with engine_work("coach"):
        assert await asyncio.to_thread(current_engine_work) == "coach"


class _Engine:
    options: dict = {}

    def quit(self):
        pass


def test_pool_accounts_held_time_and_refusals(monkeypatch):
    pool = EnginePool("stockfish", size=1, acquire_timeout_s=0.01)
    monkeypatch.setattr(pool, "_spawn", lambda: _Engine())
    held_before = sample("regence_engine_seconds_total", "coach")
    busy_before = sample("regence_engine_busy_total", "coach")

    with engine_work("coach"), pool.acquire(), pytest.raises(EngineBusyError), pool.acquire():  # the only engine is busy
        pass
    assert sample("regence_engine_seconds_total", "coach") > held_before
    assert sample("regence_engine_busy_total", "coach") == busy_before + 1


async def test_active_players_are_counted_once_per_day(client, token_user_1, token_user_2):
    for token in (token_user_1, token_user_1, token_user_2):
        assert client.get("/api/v1/profile/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    await observability.refresh_active_players()
    assert REGISTRY.get_sample_value("regence_active_players_today") == 2
    assert "regence_engine_seconds_total" in client.get("/metrics").text


async def test_celery_queue_length_is_exported(client):
    """The Celery queue length is taken from the broker list in Redis on every /metrics request (alerts 23.2)."""
    from src.db import redis as redis_module
    from src.worker.celery_app import ANALYSIS_QUEUE

    redis_module.redis_client.lists.pop(ANALYSIS_QUEUE, None)
    await redis_module.redis_client.rpush(ANALYSIS_QUEUE, "a", "b", "c")
    try:
        assert client.get("/metrics").status_code == 200
        assert REGISTRY.get_sample_value("regence_celery_queue_length", {"queue": ANALYSIS_QUEUE}) == 3
    finally:
        redis_module.redis_client.lists.pop(ANALYSIS_QUEUE, None)


@pytest.fixture
def stub_hint(monkeypatch):
    """A hint without an engine; level 3 is an input error (400)."""
    calls = []

    async def hint(fen, step):
        if step == 3:
            raise DomainValueError("invalid_fen")
        calls.append(step)
        return {**HINT, "step": step}

    monkeypatch.setattr(analysis_api.analysis_service, "hint", hint)
    return calls


def hint(client, step: int):
    return client.post("/api/v1/analysis/hint", json={"fen": FEN, "step": step})


def test_coach_quota_is_off_without_the_flag(client, stub_hint, monkeypatch, freeze_rate_limit_window):
    monkeypatch.setattr(settings, "FREE_COACH_REQUESTS_PER_DAY", 1)
    assert settings.FREE_TIER_LIMITS is False
    assert [hint(client, 1).status_code for _ in range(3)] == [200, 200, 200]


def test_coach_quota_counts_only_completed_work(client, stub_hint, monkeypatch, freeze_rate_limit_window):
    monkeypatch.setattr(settings, "FREE_TIER_LIMITS", True)
    monkeypatch.setattr(settings, "FREE_COACH_REQUESTS_PER_DAY", 2)

    assert hint(client, 1).status_code == 200
    assert hint(client, 3).status_code == 400  # an error does not consume the quota
    assert hint(client, 2).status_code == 200
    refused = hint(client, 1)
    assert refused.status_code == 429
    detail = refused.json()["detail"]
    assert detail["code"] == "daily_limit_reached" and detail["params"]["limit"] == 2
    assert 1 <= detail["params"]["hours"] <= 24 and refused.headers["Retry-After"]
    assert stub_hint == [1, 2]  # refusal comes before the engine work


def test_engine_seconds_label_set_is_bounded():
    assert set(engine_pool.ENGINE_WORK_KINDS) == {"bot_move", "analysis", "coach", "simulation", "puzzles", "other"}
