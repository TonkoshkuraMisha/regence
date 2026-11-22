# --- FILE: tests/test_arena_edges.py ---
"""Арена: крайние случаи служебных функций — чужая или неизвестная партия, устаревшие записи ожидания пары."""

import time

import pytest

from src.core.errors import DomainError
from src.db import redis as redis_module
from src.services import arena


async def test_waiting_ids_drops_stale_entries():
    key = arena._wait_key(77)
    now = time.time()
    await redis_module.redis_client.hset(key, mapping={"1": str(now), "2": str(now - arena.WAIT_TTL_S - 5)})
    assert await arena.waiting_ids(77) == {1}
    assert set(await redis_module.redis_client.hgetall(key)) == {"1"}


async def test_leave_waiting_removes_the_player():
    await redis_module.redis_client.hset(arena._wait_key(78), mapping={"5": str(time.time())})
    await arena.leave_waiting(78, 5)
    assert await arena.waiting_ids(78) == set()


async def test_unknown_game_is_not_an_arena_game(db_session):
    assert await arena.is_arena_game(db_session, 999_999) is False
    assert await arena.game_state_fields(db_session, 999_999) == {}
    assert await arena.on_game_aborted(db_session, 999_999, None) is False


async def test_berserk_refused_outside_arena_games(db_session):
    with pytest.raises(DomainError) as error:
        await arena.berserk(db_session, 999_999, 1)
    assert error.value.code == "berserk_unavailable"


async def test_last_opponent_without_games_is_none(db_session):
    assert await arena._last_opponent(db_session, 1, 1) is None
