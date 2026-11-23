# --- FILE: tests/test_anticheat.py ---

import pytest

from src.models.game import Game, GameStatus
from src.models.move import Move
from src.models.user import User
from src.services.anticheat import evaluate_game_telemetry
from src.services.game_state import state_manager


@pytest.mark.asyncio
async def test_human_telemetry_keeps_high_trust_factor(db_session):
    """On a series of "human" moves (varied time, no leaving the tab) trust_factor stays 100."""
    human = User(
        username="honest_gm", hashed_password="pw", bullet_rating=1850, blitz_rating=1850,
        rapid_rating=1850, classical_rating=1850, trust_factor=100, is_cheater=False
    )
    opponent = User(
        username="honest_opp", hashed_password="pw", bullet_rating=1840, blitz_rating=1840,
        rapid_rating=1840, classical_rating=1840, trust_factor=100, is_cheater=False
    )
    db_session.add_all([human, opponent])
    await db_session.commit()
    await db_session.refresh(human)
    await db_session.refresh(opponent)

    game = Game(
        white_player_id=human.id,
        black_player_id=opponent.id,
        status=GameStatus.COMPLETED,
        is_rated=True,
        result="1-0",
    )
    db_session.add(game)
    await db_session.commit()
    await db_session.refresh(game)

    human_times = [900, 1400, 3200, 8500, 2100, 14200, 1700, 6400, 950, 11800, 2800, 5100]
    moves = [
        Move(
            game_id=game.id,
            player_id=human.id if idx % 2 == 1 else opponent.id,
            move_number=idx + 4,
            notation="e2e4" if idx % 2 == 1 else "e7e5",
            san="e4" if idx % 2 == 1 else "e5",
            time_taken_ms=t_ms,
            window_blurred_before_move=False,
            is_premove=(idx == 9),
            network_lag_ms=15,
        )
        for idx, t_ms in enumerate(human_times, start=1)
    ]
    db_session.add_all(moves)
    await db_session.commit()

    report = await evaluate_game_telemetry(db_session, game.id)
    await db_session.refresh(human)

    assert report[human.id]["penalty"] == 0
    assert human.trust_factor == 100
    assert human.is_cheater is False


@pytest.mark.asyncio
async def test_robotic_blurred_telemetry_flags_cheater(db_session):
    """A constant window_blurred_before_move=True and a monotonic time of 4500 ms lower trust_factor below 30."""
    cheater = User(
        username="tab_switcher_bot", hashed_password="pw", bullet_rating=1500, blitz_rating=1500,
        rapid_rating=1500, classical_rating=1500, trust_factor=100, is_cheater=False
    )
    victim = User(
        username="fair_victim", hashed_password="pw", bullet_rating=1500, blitz_rating=1500,
        rapid_rating=1500, classical_rating=1500, trust_factor=100, is_cheater=False
    )
    db_session.add_all([cheater, victim])
    await db_session.commit()
    await db_session.refresh(cheater)
    await db_session.refresh(victim)

    game = Game(
        white_player_id=cheater.id,
        black_player_id=victim.id,
        status=GameStatus.COMPLETED,
        is_rated=True,
        result="1-0",
    )
    db_session.add(game)
    await db_session.commit()
    await db_session.refresh(game)

    cheater_moves = [
        Move(
            game_id=game.id,
            player_id=cheater.id if move_num % 2 == 1 else victim.id,
            move_number=move_num,
            notation="g1f3" if move_num % 2 == 1 else "g8f6",
            san="Nf3" if move_num % 2 == 1 else "Nf6",
            time_taken_ms=4500,
            window_blurred_before_move=True,
            is_premove=False,
            network_lag_ms=10,
        )
        for move_num in range(1, 16)
    ]
    db_session.add_all(cheater_moves)
    await db_session.commit()

    report = await evaluate_game_telemetry(db_session, game.id)
    await db_session.refresh(cheater)

    assert report[cheater.id]["blur_ratio"] == 1.0
    assert report[cheater.id]["timing_cv"] == 0.0
    assert cheater.trust_factor < 30
    assert cheater.is_cheater is True


@pytest.mark.asyncio
async def test_finish_game_triggers_telemetry_anticheat(db_session):
    """Checks the automatic launch of evaluate_game_telemetry inside state_manager.finish_game."""
    cheater = User(
        username="auto_ac_cheater", hashed_password="pw", bullet_rating=1400, blitz_rating=1400,
        rapid_rating=1400, classical_rating=1400, trust_factor=100, is_cheater=False
    )
    other = User(
        username="auto_ac_other", hashed_password="pw", bullet_rating=1400, blitz_rating=1400,
        rapid_rating=1400, classical_rating=1400, trust_factor=100, is_cheater=False
    )
    db_session.add_all([cheater, other])
    await db_session.commit()
    await db_session.refresh(cheater)
    await db_session.refresh(other)

    game = Game(
        white_player_id=cheater.id,
        black_player_id=other.id,
        status=GameStatus.IN_PROGRESS,
        base_time_ms=180000,
        increment_ms=0,
        is_rated=True,
    )
    db_session.add(game)
    await db_session.commit()
    await db_session.refresh(game)

    await state_manager.initialize_game(game.id, cheater.id, other.id, 180000, 0)

    # Use a valid sequence of short moves to build the PGN
    valid_uci_moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "d2d3", "g8f6", "b1c3", "d7d6"]
    for idx, uci in enumerate(valid_uci_moves, start=1):
        await state_manager.save_move_telemetry(game.id, {
            "player_id": cheater.id if idx % 2 == 1 else other.id,
            "move_number": idx,
            "notation": uci,
            "san": uci[:2] + "-" + uci[2:],
            "fen_after": "",
            "time_taken_ms": 4500,
            "window_blurred_before_move": True,
            "is_premove": False,
            "network_lag_ms": 5,
        })

    await state_manager.finish_game(db_session, game.id, "1-0", termination="checkmate")
    await db_session.refresh(cheater)

    assert cheater.trust_factor < 30
    assert cheater.is_cheater is True


# --- Pure rules and refusal branches (added for coverage) ---

def _move(num, ms, blurred=False, premove=False):
    """An in-memory move (no database) for testing pure functions."""
    return Move(
        game_id=1, player_id=1, move_number=num, notation="e2e4", san="e4",
        time_taken_ms=ms, window_blurred_before_move=blurred, is_premove=premove,
    )


def test_blur_ratio_empty_and_short_post_opening():
    from src.services.anticheat import calculate_blur_ratio

    assert calculate_blur_ratio([]) == 0.0
    # fewer than three moves after the opening — all of the player's moves count
    moves = [_move(1, 1000, blurred=True), _move(2, 1000), _move(3, 1000), _move(4, 1000)]
    assert calculate_blur_ratio(moves) == 0.25


def test_timing_cv_needs_three_timed_non_premove_moves():
    from src.services.anticheat import calculate_timing_cv

    assert calculate_timing_cv([_move(1, 1000), _move(2, 0), _move(3, 1000, premove=True)]) == (1.0, 0.0)
    cv, mean = calculate_timing_cv([_move(1, 1000), _move(2, 1000), _move(3, 1000)])
    assert (cv, mean) == (0.0, 1000.0)


def test_penalty_tiers_for_blur_and_rhythm():
    from src.services.anticheat import MIN_MOVES_FOR_ANALYSIS, compute_telemetry_penalty

    n = max(MIN_MOVES_FOR_ANALYSIS, 12)
    # steady 4 s rhythm without losing focus: only the rhythm penalty
    flat = [_move(i + 10, 4000) for i in range(n)]
    assert compute_telemetry_penalty(flat)["penalty"] == 40
    # a focus-loss share of 0.4 adds a penalty of 12
    some_blur = [_move(i + 10, 4000, blurred=(i % 5 < 2)) for i in range(10)]  # 4 of 10
    assert compute_telemetry_penalty(some_blur)["penalty"] == 40 + 12
    # share 0.5 -> +25
    half = [_move(i + 10, 4000, blurred=(i % 2 == 0)) for i in range(n)]
    assert compute_telemetry_penalty(half)["penalty"] == 40 + 25
    # too few moves — no penalty
    assert compute_telemetry_penalty(flat[:2])["penalty"] == 0


@pytest.mark.asyncio
async def test_claim_first_evaluation_without_redis_is_denied(monkeypatch):
    """Redis unavailable: the game is considered already evaluated, no penalty is applied."""
    from src.db import redis as redis_module
    from src.services.anticheat import _claim_first_evaluation

    async def boom(*args, **kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setattr(redis_module.redis_client, "set", boom)
    assert await _claim_first_evaluation(1) is False


@pytest.mark.asyncio
async def test_evaluate_missing_game_and_missing_user(db_session):
    # no game
    assert await evaluate_game_telemetry(db_session, 424242) == {}

    # the game's player was deleted: they are skipped without crashing
    keeper = User(username="ac_keeper", hashed_password="pw")
    db_session.add(keeper)
    await db_session.commit()
    game = Game(white_player_id=keeper.id, black_player_id=999_999, status=GameStatus.COMPLETED, result="1-0")
    db_session.add(game)
    await db_session.commit()
    db_session.add_all([
        Move(game_id=game.id, player_id=keeper.id, move_number=1, notation="e2e4", san="e4", time_taken_ms=900),
        Move(game_id=game.id, player_id=999_999, move_number=2, notation="e7e5", san="e5", time_taken_ms=900),
    ])
    await db_session.commit()
    report = await evaluate_game_telemetry(db_session, game.id, force=True)
    assert set(report) == {keeper.id}


def test_trusted_premove_requires_fast_server_side_move():
    from src.core.config import settings
    from src.services.anticheat import trusted_premove

    assert trusted_premove(True, 0) is True
    assert trusted_premove(True, settings.AC_PREMOVE_MAX_ELAPSED_MS + 1) is False
    assert trusted_premove(False, 0) is False


def test_penalty_for_moderately_regular_rhythm():
    from src.services.anticheat import compute_telemetry_penalty

    # CV between 0.12 and 0.22 at an "engine-like" mean: rhythm penalty 22
    times = [3000, 4000, 3500, 4500, 3200, 3800, 4200, 3600]
    moves = [_move(i + 10, t) for i, t in enumerate(times)]
    metrics = compute_telemetry_penalty(moves)
    assert 0.12 < metrics["timing_cv"] <= 0.22
    assert metrics["penalty"] == 22


@pytest.mark.asyncio
async def test_evaluate_game_without_moves_returns_empty(db_session):
    a = User(username="ac_a", hashed_password="pw")
    b = User(username="ac_b", hashed_password="pw")
    db_session.add_all([a, b])
    await db_session.commit()
    game = Game(white_player_id=a.id, black_player_id=b.id, status=GameStatus.COMPLETED, result="1-0")
    db_session.add(game)
    await db_session.commit()
    assert await evaluate_game_telemetry(db_session, game.id) == {}
