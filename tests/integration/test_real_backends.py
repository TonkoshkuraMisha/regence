# --- FILE: tests/integration/test_real_backends.py ---
"""
Races on real PostgreSQL and Redis.

Unit tests run on SQLite and an in-memory Redis mock, where SELECT ... FOR UPDATE is silently
ignored and WATCH/MULTI is emulated. Here we check that protection against double
game completion and lost rating updates works on real backends.

Run (requires an empty DB and Redis; their data will be deleted):
    TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/regence_test \
    TEST_REDIS_URL=redis://localhost:6379/15 \
    python -m pytest -m integration
Without these variables the tests are skipped. In CI they run with the postgres and redis services.
"""

import asyncio
import os

import pytest
import redis.asyncio as redis_asyncio
from sqlalchemy import func, select

from src.models.game import Game, GameStatus
from src.models.user import User
from src.services.game_state import state_manager
from src.services.matchmaker import MatchmakingError, matchmaker

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
REDIS_URL = os.getenv("TEST_REDIS_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (DATABASE_URL and REDIS_URL),
        reason="TEST_DATABASE_URL / TEST_REDIS_URL not set (real PostgreSQL and Redis required)",
    ),
]


@pytest.fixture
async def real_redis(monkeypatch):
    client = redis_asyncio.from_url(REDIS_URL, decode_responses=True)
    await client.flushdb()
    monkeypatch.setattr(state_manager, "redis", client)
    monkeypatch.setattr("src.db.redis.redis_client", client)
    # Publishing background analysis to the Celery broker is disabled by the shared no_celery_publish fixture (conftest).
    yield client
    await client.flushdb()
    await client.aclose()


async def _create_users(pg, *ratings: int) -> list[int]:
    async with pg() as db:
        users = [
            User(
                username=f"it_{i}_{r}", hashed_password="pw",
                bullet_rating=r, blitz_rating=r, rapid_rating=r, classical_rating=r,
            )
            for i, r in enumerate(ratings)
        ]
        db.add_all(users)
        await db.commit()
        return [u.id for u in users]


async def _create_game(pg, white_id: int, black_id: int) -> int:
    async with pg() as db:
        game = Game(
            white_player_id=white_id, black_player_id=black_id, status=GameStatus.IN_PROGRESS,
            base_time_ms=180000, increment_ms=0, is_rated=True,
        )
        db.add(game)
        await db.commit()
        game_id = game.id
    await state_manager.initialize_game(game_id, white_id, black_id, 180000, 0)
    return game_id


async def _finish(pg, game_id: int, result: str) -> dict:
    async with pg() as db:
        return await state_manager.finish_game(db, game_id, result, termination="resignation")


async def _rating(pg, user_id: int) -> int:
    # All games in this file are created with base_time_ms=180000/increment_ms=0 — that is blitz.
    async with pg() as db:
        return (await db.get(User, user_id)).blitz_rating


async def test_concurrent_finish_applies_rating_once(pg, real_redis):
    """Two handlers finish the same game at the same time in different sessions (FOR UPDATE)."""
    white, black = await _create_users(pg, 1500, 1500)
    game_id = await _create_game(pg, white, black)

    first, second = await asyncio.gather(_finish(pg, game_id, "1-0"), _finish(pg, game_id, "1-0"))

    delta = first["white_delta"] or second["white_delta"]
    assert delta > 0
    assert await _rating(pg, white) == 1500 + delta
    assert await _rating(pg, black) == 1500 - delta


async def test_two_games_of_one_player_do_not_lose_rating_update(pg, real_redis):
    """Two games of player A end simultaneously: both deltas must reach the rating."""
    a, b, c = await _create_users(pg, 1500, 1500, 1500)
    game_ab = await _create_game(pg, a, b)
    game_ac = await _create_game(pg, a, c)

    await asyncio.gather(_finish(pg, game_ab, "1-0"), _finish(pg, game_ac, "1-0"))

    async with pg() as db:
        deltas = [(await db.get(Game, gid)).white_rating_delta for gid in (game_ab, game_ac)]
    assert all(d > 0 for d in deltas)
    assert await _rating(pg, a) == 1500 + sum(deltas)


async def test_concurrent_claims_on_real_redis_have_single_winner(pg, real_redis):
    white, black = await _create_users(pg, 1500, 1500)
    game_id = await _create_game(pg, white, black)

    claims = await asyncio.gather(*(
        state_manager.claim_game_end(game_id, result, termination)
        for result, termination in [("0-1", "resignation"), ("1-0", "resignation"), ("1/2-1/2", "agreement"),
                                    ("0-1", "timeout"), ("1-0", "abandoned")] * 4
    ))

    assert sum(c is not None for c in claims) == 1


async def test_challenge_accepted_once_on_real_backends(pg, real_redis):
    challenger, acceptor_1, acceptor_2 = await _create_users(pg, 1500, 1500, 1500)
    async with pg() as db:
        await matchmaker.join_queue(challenger, "challenger", 1500, 180000, 0, db=db)

    async def accept(acceptor_id: int):
        async with pg() as db:
            return await matchmaker.accept_challenge(challenger, acceptor_id, None, db=db)

    results = await asyncio.gather(accept(acceptor_1), accept(acceptor_2), return_exceptions=True)

    assert sum(isinstance(r, int) for r in results) == 1
    assert all(isinstance(r, (int, MatchmakingError)) for r in results)
    async with pg() as db:
        games = (await db.execute(select(func.count(Game.id)))).scalar()
    assert games == 1
