# --- FILE: tests/test_game_end_reconciliation.py ---
"""
Redis/DB reconciliation: a game finished in Redis but not recorded in the DB (the process crashed or the DB
was unavailable between claim_game_end and finish_game) must be completed, and a game
that lost its state in Redis must be restored.
"""

import asyncio
import time

import fakeredis.aioredis
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.models.game import Game, GameStatus
from src.models.user import User
from src.services import game_state as game_state_module
from src.services.game_state import GAME_DEADLINES_KEY, PENDING_FINISH_KEY, RECONCILE_GRACE_MS, state_manager


class DummyManager:
    def __init__(self):
        self.sent: list[tuple[int, dict]] = []

    async def send_personal_message(self, message: dict, user_id: int):
        self.sent.append((user_id, message))

    async def broadcast_to_spectators(self, game_id: int, message: dict):
        pass


@pytest.fixture
def real_redis(monkeypatch):
    """fakeredis: real WATCH/MULTI and sorted set semantics."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(state_manager, "redis", client)
    monkeypatch.setattr(state_manager, "_missing_state_seen", set())
    return client


@pytest.fixture
def session_factory(db_session, monkeypatch):
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(game_state_module, "AsyncSessionLocal", factory)
    return factory


async def _make_game(db_session, *, init_redis: bool = True) -> tuple[Game, User, User]:
    white = User(
        username="w_reconcile", hashed_password="pw", bullet_rating=1500,
        blitz_rating=1500, rapid_rating=1500, classical_rating=1500
    )
    black = User(
        username="b_reconcile", hashed_password="pw", bullet_rating=1500,
        blitz_rating=1500, rapid_rating=1500, classical_rating=1500
    )
    db_session.add_all([white, black])
    await db_session.commit()
    game = Game(
        white_player_id=white.id, black_player_id=black.id, status=GameStatus.IN_PROGRESS,
        base_time_ms=180000, increment_ms=0, is_rated=True,
    )
    db_session.add(game)
    await db_session.commit()
    if init_redis:
        await state_manager.initialize_game(game.id, white.id, black.id, 180000, 0)
    return game, white, black


async def _db_game(factory, game_id: int) -> Game:
    async with factory() as db:
        return await db.get(Game, game_id)


def _after_grace() -> int:
    return int(time.time() * 1000) + RECONCILE_GRACE_MS + 1


async def test_claim_registers_pending_finish_and_finish_game_clears_it(
        real_redis, session_factory, db_session, no_celery_publish):
    game, _, _ = await _make_game(db_session)

    await state_manager.claim_game_end(game.id, "0-1", "resignation")
    assert await real_redis.zscore(PENDING_FINISH_KEY, str(game.id)) is not None

    async with session_factory() as db:
        await state_manager.finish_game(db, game.id, "0-1", termination="resignation")
    assert await real_redis.zscore(PENDING_FINISH_KEY, str(game.id)) is None

    # Background analysis is queued without delaying finish_game.
    for _ in range(50):
        if no_celery_publish:
            break
        await asyncio.sleep(0.01)
    assert no_celery_publish == [game.id]


async def test_move_ending_the_game_registers_pending_finish(real_redis, session_factory, db_session):
    """A flag on a move finishes the game in the move transaction; it must also reach the registry."""
    game, white, _ = await _make_game(db_session)
    await state_manager.update_game_state(game.id, {"last_move_at": int(time.time() * 1000) - 200_000})

    res = await state_manager.process_atomic_move(game.id, white.id, "cmd-1", "e2e4")
    assert res["status"] == "game_over"
    assert await real_redis.zscore(PENDING_FINISH_KEY, str(game.id)) is not None


async def test_game_claimed_but_never_written_is_finished_after_grace(real_redis, session_factory, db_session):
    game, white, black = await _make_game(db_session)
    # The resignation was claimed in Redis, but the process died before finish_game.
    await state_manager.claim_game_end(game.id, "0-1", "resignation")
    manager = DummyManager()

    # Until the grace period has passed the regular handler may still be running; leave it alone.
    report = await state_manager.reconcile_unfinished_games(int(time.time() * 1000), manager=manager)
    assert report["finished"] == []
    assert (await _db_game(session_factory, game.id)).status == GameStatus.IN_PROGRESS

    report = await state_manager.reconcile_unfinished_games(_after_grace(), manager=manager)
    assert report["finished"] == [game.id]

    db_game = await _db_game(session_factory, game.id)
    assert db_game.status == GameStatus.COMPLETED
    assert (db_game.result, db_game.termination) == ("0-1", "resignation")
    async with session_factory() as db:
        assert (await db.get(User, black.id)).blitz_rating > 1500  # rating applied

    assert await real_redis.zscore(PENDING_FINISH_KEY, str(game.id)) is None
    assert not await real_redis.hgetall(f"game:{game.id}:state")
    assert {uid for uid, msg in manager.sent if msg["event"] == "game_over"} == {white.id, black.id}

    # A repeated reconciliation does nothing and does not apply rating a second time.
    report = await state_manager.reconcile_unfinished_games(_after_grace(), manager=manager)
    assert report["finished"] == []


async def test_failed_finish_stays_pending_and_is_retried(real_redis, session_factory, db_session, monkeypatch):
    game, _, _ = await _make_game(db_session)
    await state_manager.claim_game_end(game.id, "1-0", "resignation")

    original_finish = state_manager.finish_game

    async def broken_finish(*args, **kwargs):
        raise RuntimeError("database is down")

    monkeypatch.setattr(state_manager, "finish_game", broken_finish)
    report = await state_manager.reconcile_unfinished_games(_after_grace())
    assert report["failed"] == [game.id]
    assert await real_redis.zscore(PENDING_FINISH_KEY, str(game.id)) is not None

    monkeypatch.setattr(state_manager, "finish_game", original_finish)
    report = await state_manager.reconcile_unfinished_games(_after_grace())
    assert report["finished"] == [game.id]
    assert (await _db_game(session_factory, game.id)).status == GameStatus.COMPLETED


async def test_abort_claimed_but_never_written_is_aborted_in_db(real_redis, session_factory, db_session):
    game, white, black = await _make_game(db_session)
    await state_manager.claim_game_end(game.id, "*", "aborted", status="aborted")
    manager = DummyManager()

    report = await state_manager.reconcile_unfinished_games(_after_grace(), manager=manager)

    assert report["aborted"] == [game.id]
    db_game = await _db_game(session_factory, game.id)
    assert db_game.status == GameStatus.ABORTED
    assert db_game.white_rating_delta == 0
    assert {uid for uid, msg in manager.sent if msg["reason"] == "aborted"} == {white.id, black.id}


async def test_game_lost_from_redis_is_restored_on_second_pass(real_redis, session_factory, db_session):
    """Redis restarted without persistence: the game exists only in the DB."""
    game, _, _ = await _make_game(db_session, init_redis=False)

    report = await state_manager.reconcile_unfinished_games(_after_grace())
    assert report["restored"] == []  # could be a game just created before initialize_game

    report = await state_manager.reconcile_unfinished_games(_after_grace())
    assert report["restored"] == [game.id]
    state = await real_redis.hgetall(f"game:{game.id}:state")
    assert state["status"] == "in_progress"
    assert str(game.id) in await real_redis.smembers("active_games")


async def test_in_progress_game_missing_from_active_set_is_readded(real_redis, session_factory, db_session):
    game, _, _ = await _make_game(db_session)
    await real_redis.srem("active_games", str(game.id))

    report = await state_manager.reconcile_unfinished_games(_after_grace())

    assert report["restored"] == [game.id]
    assert str(game.id) in await real_redis.smembers("active_games")


async def test_in_progress_game_without_deadline_gets_one_backfilled(real_redis, session_factory, db_session):
    """
    A game in_progress but without an entry in GAME_DEADLINES_KEY (this scheme deployed over games already
    in progress, or the deadline was lost for another reason): reconciliation must restore it,
    otherwise its flag would not fire until the next move/disconnect.
    """
    game, _, _ = await _make_game(db_session)
    await real_redis.zrem(GAME_DEADLINES_KEY, str(game.id))
    assert await real_redis.zscore(GAME_DEADLINES_KEY, str(game.id)) is None

    await state_manager.reconcile_unfinished_games(_after_grace())

    assert await real_redis.zscore(GAME_DEADLINES_KEY, str(game.id)) is not None


async def test_move_telemetry_survives_until_result_is_committed(real_redis, session_factory, db_session):
    """Telemetry is not deleted before the commit: after a failure the retry will not be left without moves."""
    game, _, _ = await _make_game(db_session)
    await state_manager.save_move_telemetry(game.id, {"notation": "e2e4"})

    assert await state_manager.read_all_moves(game.id) == [{"notation": "e2e4"}]
    assert await state_manager.read_all_moves(game.id) == [{"notation": "e2e4"}]

    await state_manager.clear_game_state(game.id)
    assert await state_manager.read_all_moves(game.id) == []
