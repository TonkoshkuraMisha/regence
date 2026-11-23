# --- FILE: tests/test_game_state.py ---

import time

import pytest

from src.services.game_state import state_manager


class DummyManager:
    """WebSocket manager stub to isolate the state-logic tests."""
    async def send_personal_message(self, message: dict, user_id: int):
        pass


@pytest.mark.asyncio
async def test_game_state_initialization():
    await state_manager.initialize_game(
        game_id=1, white_id=10, black_id=20, base_time_ms=180000, increment_ms=0
    )
    state = await state_manager.get_game_state(1)

    assert state is not None
    assert state["white_id"] == 10
    assert state["black_id"] == 20
    assert state["white_time_ms"] == 180000
    assert state["status"] == "in_progress"


@pytest.mark.asyncio
async def test_disconnect_and_reconnect_keeps_clock_running():
    """
    A dropped connection neither stops nor shifts the clock: after reconnecting, White's remaining
    time equals base - (now - last_move_at), and last_move_at and the stored time do not change.
    """
    from src.services.game_state import live_clock_ms

    await state_manager.initialize_game(
        game_id=2, white_id=10, black_id=20, base_time_ms=180000, increment_ms=0
    )
    now_ms = int(time.time() * 1000)
    # White's move has been running for 5 seconds, 3 of which White was offline.
    await state_manager.update_game_state(2, {"last_move_at": now_ms - 5000})

    dummy_manager = DummyManager()
    await state_manager.handle_player_disconnect(10, dummy_manager)
    state_after_dc = await state_manager.get_game_state(2)
    assert state_after_dc["white_disconnected"] == "true"
    await state_manager.update_game_state(2, {"white_disconnect_started_at": now_ms - 3000})

    await state_manager.handle_player_reconnect(10, dummy_manager)

    state = await state_manager.get_game_state(2)
    assert state["white_disconnected"] == "false"
    assert state["white_time_ms"] == 180000
    assert state["last_move_at"] == now_ms - 5000
    assert 174000 <= live_clock_ms(state, "white", int(time.time() * 1000)) <= 175000


@pytest.mark.asyncio
async def test_abort_game_without_rating_change(db_session):
    """Checks that aborting a game on the first move (before 2 plies) does not change rating and sets status ABORTED."""
    from src.models.game import Game, GameStatus
    from src.models.user import User
    from src.services.game_state import state_manager

    u1 = User(
        username="abort_white_player", hashed_password="pw", bullet_rating=1500,
        blitz_rating=1500, rapid_rating=1500, classical_rating=1500
    )
    u2 = User(
        username="abort_black_player", hashed_password="pw", bullet_rating=1500,
        blitz_rating=1500, rapid_rating=1500, classical_rating=1500
    )
    db_session.add_all([u1, u2])
    await db_session.commit()
    await db_session.refresh(u1)
    await db_session.refresh(u2)

    game = Game(
        white_player_id=u1.id,
        black_player_id=u2.id,
        status=GameStatus.IN_PROGRESS,
        base_time_ms=180000,
        increment_ms=2000,
        is_rated=True,
    )
    db_session.add(game)
    await db_session.commit()
    await db_session.refresh(game)

    await state_manager.redis.hset(f"game:{game.id}:state", mapping={
        "white_id": str(u1.id),
        "black_id": str(u2.id),
        "status": "in_progress",
        "state_version": "1",
        "last_move_at": "1000",
    })

    res = await state_manager.abort_game(db_session, game.id)
    assert res["status"] == "aborted"
    assert res["result"] == "*"
    assert res["white_delta"] == 0
    assert res["black_delta"] == 0

    await db_session.refresh(u1)
    await db_session.refresh(u2)
    await db_session.refresh(game)
    assert u1.blitz_rating == 1500
    assert u2.blitz_rating == 1500
    assert game.status == GameStatus.ABORTED


@pytest.mark.asyncio
async def test_private_invite_create_and_redeem():
    """Checks creation of a private link challenge in Redis and its single-use redemption."""
    from src.services.matchmaker import matchmaker

    invite = await matchmaker.create_private_invite(
        user_id=101,
        username="teacher_misha",
        rating=2050,
        base_time_ms=600000,
        increment_ms=5000,
        color_pref="white",
    )
    code = invite["code"]
    assert len(code) >= 6

    # The creator cannot accept their own challenge
    self_accept = await matchmaker.accept_private_invite(code, acceptor_id=101)
    assert self_accept is None

    # The second player accepts the challenge successfully
    redeemed = await matchmaker.accept_private_invite(code, acceptor_id=202)
    assert redeemed is not None
    assert redeemed["white_id"] == 101
    assert redeemed["black_id"] == 202
    assert redeemed["base_time_ms"] == 600000
    assert redeemed["increment_ms"] == 5000

    # Redeeming the same code again is impossible
    second_try = await matchmaker.accept_private_invite(code, acceptor_id=303)
    assert second_try is None
