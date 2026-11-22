# --- FILE: tests/test_game_state_paths.py ---
"""
Состояние партии в Redis (src/services/game_state.py): редкие ветки — повтор при конфликте WATCH, лидерство цикла
таймаутов, сверка, отмена на первом ходу, берсерк, итог партии с нестандартными данными. Время и сон подменены,
движок не используется. Дополняет test_game_state.py, test_timeouts_loop.py и test_game_end_reconciliation.py.
"""

import time

import pytest
from redis.exceptions import WatchError

from src.core.instance import WORKER_ID
from src.models.game import Game, GameStatus
from src.models.user import User
from src.services import game_state as gs
from src.services.game_state import (
    ABANDON_TIMEOUT_MS,
    GAME_DEADLINES_KEY,
    PENDING_FINISH_KEY,
    evaluate_clock_expiry,
    state_manager,
)

KVK = "8/8/8/8/8/8/8/K1k5 w - - 0 1"  # голые короли: мата не поставить никому


class Recorder:
    """Менеджер соединений-заглушка: запоминает рассылку."""

    def __init__(self):
        self.sent: list[tuple[int, dict]] = []
        self.spectators: list[dict] = []

    async def send_personal_message(self, message, user_id):
        self.sent.append((user_id, message))

    async def broadcast_to_spectators(self, game_id, message):
        self.spectators.append(message)


async def _db_users(db_session, n=2) -> list[User]:
    users = [User(username=f"gsp_{i}", hashed_password="pw", bullet_rating=1500, blitz_rating=1500,
                  rapid_rating=1500, classical_rating=1500) for i in range(n)]
    db_session.add_all(users)
    await db_session.commit()
    return users


def _watch_error_once(monkeypatch):
    """Первый execute() транзакции WATCH/MULTI падает с WatchError — код обязан повторить попытку."""
    real = state_manager.redis.pipeline
    seen = {"failed": False}

    def pipeline(transaction=True):
        pipe = real(transaction)
        original = pipe.execute

        async def execute():
            if not seen["failed"]:
                seen["failed"] = True
                raise WatchError("changed")
            return await original()

        pipe.execute = execute
        return pipe

    monkeypatch.setattr(state_manager.redis, "pipeline", pipeline)
    return seen


# --- Чистые правила -----------------------------------------------------------------------

async def test_abandon_rules_for_white_and_for_dead_draw():
    await state_manager.initialize_game(8001, 1, 2, 600000, 0)
    now = int(time.time() * 1000)
    state = await state_manager.get_game_state(8001)
    state.update(white_disconnected="true", white_disconnect_started_at=str(now - ABANDON_TIMEOUT_MS - 1))
    assert evaluate_clock_expiry(state, now) == ("0-1", 2, "abandoned")

    state.update(white_disconnected="false", black_disconnected="true",
                 black_disconnect_started_at=str(now - ABANDON_TIMEOUT_MS - 1))
    assert evaluate_clock_expiry(state, now) == ("1-0", 1, "abandoned")

    state["board_fen"] = KVK  # у оставшегося нет материала для мата — ничья, а не победа
    result, winner, _ = evaluate_clock_expiry(state, now)
    assert (result, winner) == ("1/2-1/2", None)


# --- Конфликты WATCH ----------------------------------------------------------------------

async def test_update_if_in_progress_retries_and_refuses_finished(monkeypatch):
    await state_manager.initialize_game(8002, 1, 2, 600000, 0)
    seen = _watch_error_once(monkeypatch)
    before = await state_manager.update_if_in_progress(8002, {"draw_offer": "1"})
    assert seen["failed"] and before is not None
    assert (await state_manager.get_game_state(8002))["draw_offer"] == "1"

    await state_manager.update_game_state(8002, {"status": "completed"})
    assert await state_manager.update_if_in_progress(8002, {"draw_offer": ""}) is None
    assert await state_manager.update_if_in_progress(424242, {"draw_offer": ""}) is None


async def test_claim_game_end_retries_on_watch_error(monkeypatch):
    await state_manager.initialize_game(8003, 1, 2, 600000, 0)
    seen = _watch_error_once(monkeypatch)
    assert await state_manager.claim_game_end(8003, "1-0", "resignation") is not None
    assert seen["failed"]
    # повторный захват и захват с отказом guard — None
    assert await state_manager.claim_game_end(8003, "1-0", "resignation") is None
    await state_manager.initialize_game(8004, 1, 2, 600000, 0)
    assert await state_manager.claim_game_end(8004, "1-0", "x", guard=lambda fresh: False) is None


# --- Берсерк ------------------------------------------------------------------------------

async def test_apply_berserk_error_codes_and_retry(monkeypatch):
    assert (await state_manager.apply_berserk(404, 1))["code"] == "game_not_in_progress"

    await state_manager.initialize_game(8005, 1, 2, 600000, 0)
    assert (await state_manager.apply_berserk(8005, 1))["code"] == "berserk_unavailable"  # не партия арены

    await state_manager.update_game_state(8005, {"berserk_allowed": "1"})
    assert (await state_manager.apply_berserk(8005, 99))["code"] == "berserk_unavailable"  # не игрок партии

    seen = _watch_error_once(monkeypatch)
    ok = await state_manager.apply_berserk(8005, 1)
    assert seen["failed"] and ok["status"] == "ok" and ok["state"]["white_time_ms"] == 300000
    assert (await state_manager.apply_berserk(8005, 1))["status"] == "ignored"

    # чёрные после двух полуходов уже опоздали
    await state_manager.update_game_state(8005, {"state_version": "2"})
    assert (await state_manager.apply_berserk(8005, 2))["code"] == "berserk_too_late"


# --- Отключение и возвращение -------------------------------------------------------------

async def test_disconnect_reconnect_ignore_players_without_live_game():
    manager = Recorder()
    await state_manager.handle_player_disconnect(1, manager)  # нет партии
    await state_manager.handle_player_reconnect(1, manager)
    await state_manager.initialize_game(8006, 1, 2, 600000, 0)
    await state_manager.update_game_state(8006, {"status": "completed"})
    await state_manager.handle_player_disconnect(1, manager)
    await state_manager.handle_player_reconnect(1, manager)
    assert manager.sent == []

    # партия есть, но завершилась между чтением и записью: соперник не оповещается
    await state_manager.update_game_state(8006, {"status": "in_progress"})
    real = state_manager._update_if_in_progress

    async def gone(*args, **kwargs):
        return None

    state_manager._update_if_in_progress = gone  # type: ignore[method-assign]
    try:
        await state_manager.handle_player_disconnect(1, manager)
        await state_manager.update_game_state(8006, {"white_disconnected": "true"})
        await state_manager.handle_player_reconnect(1, manager)
    finally:
        state_manager._update_if_in_progress = real  # type: ignore[method-assign]
    assert manager.sent == []


# --- Лидерство и цикл таймаутов -----------------------------------------------------------

async def test_timeouts_leadership_variants(monkeypatch):
    redis = state_manager.redis
    assert await state_manager._hold_timeouts_leadership() is True  # свободно — берём
    assert await state_manager._hold_timeouts_leadership() is True  # уже наше — продлеваем

    await redis.set(gs.TIMEOUTS_LEADER_KEY, "other-worker")
    assert await state_manager._hold_timeouts_leadership() is False

    async def boom(*args, **kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setattr(redis, "set", boom)
    assert await state_manager._hold_timeouts_leadership() is True  # при сбое Redis проход всё равно идёт
    assert WORKER_ID


async def test_timeouts_loop_runs_pass_survives_errors_and_sleeps(monkeypatch):
    calls: list[str] = []

    async def leader():
        calls.append("leader")
        return True

    async def once(manager):
        calls.append("once")
        if calls.count("once") == 1:
            raise RuntimeError("redis down")  # сбой прохода не убивает цикл

    async def reconcile(manager):
        calls.append("reconcile")

    sleeps = {"n": 0}

    class Stop(BaseException):
        pass

    async def fake_sleep(seconds):
        sleeps["n"] += 1
        if sleeps["n"] >= 2:
            raise Stop

    monkeypatch.setattr(state_manager, "_hold_timeouts_leadership", leader)
    monkeypatch.setattr(state_manager, "check_timeouts_once", once)
    monkeypatch.setattr(state_manager, "_maybe_reconcile", reconcile)
    monkeypatch.setattr(gs.asyncio, "sleep", fake_sleep)
    with pytest.raises(Stop):
        await state_manager.check_timeouts_loop(Recorder())
    assert calls == ["leader", "once", "leader", "once", "reconcile"]


async def test_maybe_reconcile_is_throttled(monkeypatch):
    runs: list[int] = []

    async def fake_reconcile(now_ms, manager=None):
        runs.append(now_ms)

    monkeypatch.setattr(state_manager, "reconcile_unfinished_games", fake_reconcile)
    monkeypatch.setattr(state_manager, "_last_reconcile_ms", 0)
    await state_manager._maybe_reconcile(Recorder())
    await state_manager._maybe_reconcile(Recorder())  # слишком рано
    assert len(runs) == 1


# --- Проверка срока одной партии ----------------------------------------------------------

async def test_malformed_deadline_ids_and_vanished_games_are_cleaned():
    await state_manager.redis.zadd(GAME_DEADLINES_KEY, {"not-a-number": 1, "9999": 1})
    await state_manager.redis.sadd("active_games", "9999")
    await state_manager.check_timeouts_once(Recorder(), now_ms=10_000)
    assert await state_manager.redis.zcard(GAME_DEADLINES_KEY) == 0
    assert "9999" not in await state_manager.redis.smembers("active_games")


async def test_stale_failure_counters_are_dropped(monkeypatch):
    monkeypatch.setattr(state_manager, "_timeout_failures", {777: (3, 5)})
    await state_manager.check_timeouts_once(Recorder(), now_ms=10_000)
    assert state_manager._timeout_failures == {}


async def test_due_game_with_time_left_gets_new_deadline():
    await state_manager.initialize_game(8010, 1, 2, 600000, 0)
    await state_manager.update_game_state(8010, {"state_version": "4"})
    await state_manager.redis.zadd(GAME_DEADLINES_KEY, {"8010": 1})  # дедлайн «подошёл», а времени ещё много
    await state_manager.check_timeouts_once(Recorder(), now_ms=int(time.time() * 1000))
    assert await state_manager.redis.zscore(GAME_DEADLINES_KEY, "8010") > 1


async def test_flag_claim_lost_to_a_move_changes_nothing(monkeypatch):
    await state_manager.initialize_game(8011, 1, 2, 60000, 0)
    now = int(time.time() * 1000)
    await state_manager.update_game_state(8011, {"state_version": "4", "white_time_ms": "1000",
                                                 "last_move_at": str(now - 60000)})
    await state_manager.redis.zadd(GAME_DEADLINES_KEY, {"8011": 1})

    async def lost(*args, **kwargs):
        return None

    monkeypatch.setattr(state_manager, "claim_game_end", lost)
    manager = Recorder()
    await state_manager.check_timeouts_once(manager, now_ms=now)
    assert manager.sent == []


async def test_first_move_timeout_aborts_and_notifies(db_session):
    white, black = await _db_users(db_session)
    game = Game(id=8012, white_player_id=white.id, black_player_id=black.id, status=GameStatus.IN_PROGRESS,
                base_time_ms=180000, increment_ms=0)
    db_session.add(game)
    await db_session.commit()
    await state_manager.initialize_game(8012, white.id, black.id, 180000, 0)
    now = int(time.time() * 1000)
    await state_manager.update_game_state(8012, {"last_move_at": str(now - 31_000)})
    await state_manager.redis.zadd(GAME_DEADLINES_KEY, {"8012": 1})

    manager = Recorder()
    await state_manager.check_timeouts_once(manager, now_ms=now)
    assert {uid for uid, _ in manager.sent} == {white.id, black.id}
    assert manager.sent[0][1]["reason"] == "aborted" and manager.spectators
    await db_session.refresh(game)
    assert game.status == GameStatus.ABORTED


async def test_check_first_move_abort_guards(db_session):
    white, black = await _db_users(db_session)
    manager = Recorder()
    assert await state_manager.check_first_move_abort_timeout(db_session, 404, manager) is False  # нет партии

    await state_manager.initialize_game(8013, white.id, black.id, 180000, 0)
    assert await state_manager.check_first_move_abort_timeout(db_session, 8013, manager) is False  # рано
    await state_manager.update_game_state(8013, {"state_version": "2", "last_move_at": "0"})
    assert await state_manager.check_first_move_abort_timeout(db_session, 8013, manager) is False  # ходы уже были
    await state_manager.update_game_state(8013, {"state_version": "0"})
    # отмена без менеджера: результат тот же, рассылки нет
    assert await state_manager.check_first_move_abort_timeout(db_session, 8013, None) is True


async def test_abort_game_error_codes(db_session):
    white, black = await _db_users(db_session)
    assert (await state_manager.abort_game(db_session, 404))["code"] == "game_not_in_progress"

    await state_manager.initialize_game(8014, white.id, black.id, 180000, 0)
    await state_manager.update_game_state(8014, {"state_version": "2"})
    assert (await state_manager.abort_game(db_session, 8014))["code"] == "abort_too_late"

    await state_manager.update_game_state(8014, {"state_version": "0"})
    refused = await state_manager.abort_game(db_session, 8014, guard=lambda fresh: False)
    assert refused["code"] == "game_not_in_progress"

    # между чтением и захватом партия «доросла» до двух полуходов
    real = state_manager.claim_game_end

    async def claim_after_move(game_id, *args, **kwargs):
        await state_manager.update_game_state(game_id, {"state_version": "2"})
        return await real(game_id, *args, **kwargs)

    state_manager.claim_game_end = claim_after_move  # type: ignore[method-assign]
    try:
        late = await state_manager.abort_game(db_session, 8014)
    finally:
        del state_manager.claim_game_end
    assert late["code"] == "game_not_in_progress"


# --- Сверка -------------------------------------------------------------------------------

async def test_finish_pending_game_without_state_just_drops_registry_entry():
    await state_manager.redis.zadd(PENDING_FINISH_KEY, {"8020": 1})
    assert await state_manager._finish_pending_game(8020) is None
    assert await state_manager.redis.zcard(PENDING_FINISH_KEY) == 0


async def test_notify_reconciled_without_manager_is_silent():
    await state_manager._notify_reconciled(None, {"white_id": "1", "black_id": "2"}, {"game_id": 1})


# --- Восстановление из БД и итог партии ---------------------------------------------------

async def test_recover_finished_game_gets_ttl_and_db_failure_returns_none(db_session, monkeypatch):
    white, black = await _db_users(db_session)
    game = Game(id=8030, white_player_id=white.id, black_player_id=black.id, status=GameStatus.COMPLETED,
                base_time_ms=180000, increment_ms=0, result="1-0")
    db_session.add(game)
    await db_session.commit()

    state = await state_manager._recover_state_from_db(8030)
    assert state["status"] == "completed"

    class BrokenSession:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(gs, "AsyncSessionLocal", BrokenSession)
    assert await state_manager._recover_state_from_db(8031) is None


async def test_finish_game_missing_game_and_bad_moves_and_failures(db_session, monkeypatch):
    white, black = await _db_users(db_session)
    assert await state_manager.finish_game(db_session, 404, "1-0") == {}

    game = Game(id=8040, white_player_id=white.id, black_player_id=black.id, status=GameStatus.IN_PROGRESS,
                base_time_ms=180000, increment_ms=0, is_rated=True)
    db_session.add(game)
    await db_session.commit()
    await state_manager.initialize_game(8040, white.id, black.id, 180000, 0)

    # телеметрия с нелегальным и мусорным ходом: PGN обрывается на первом же
    for notation in ("e2e4", "e2e4", "zzzz"):
        await state_manager.save_move_telemetry(8040, {
            "player_id": white.id, "move_number": 1, "notation": notation, "san": notation, "fen_after": "",
            "time_taken_ms": 500, "window_blurred_before_move": False, "is_premove": False, "network_lag_ms": 0,
        })

    async def boom(*args, **kwargs):
        raise RuntimeError("anticheat down")

    monkeypatch.setattr(gs, "evaluate_game_telemetry", boom)
    from src.services import arena as arena_service
    monkeypatch.setattr(arena_service, "advance_after_game", boom)
    monkeypatch.setattr(gs, "schedule_game_analysis_in_background", lambda game_id: None)

    result = await state_manager.finish_game(db_session, 8040, "1-0", termination="resignation")
    assert "white_delta" in result
    await db_session.refresh(game)
    assert game.status == GameStatus.COMPLETED and "e4" in game.pgn


async def test_finish_game_with_final_pgn_copies_metadata(db_session, monkeypatch):
    white, black = await _db_users(db_session)
    game = Game(id=8041, white_player_id=white.id, black_player_id=black.id, status=GameStatus.IN_PROGRESS,
                base_time_ms=180000, increment_ms=0, is_rated=False)
    db_session.add(game)
    await db_session.commit()
    # состояния в Redis нет, ходов телеметрии нет: PGN берётся из final_pgn вместе с заголовками
    pgn = '[Event "x"]\n[Site "Somewhere"]\n[Date "2026.01.02"]\n[ECO "C20"]\n[Result "1-0"]\n\n1. e4 e5 1-0'
    monkeypatch.setattr(gs, "schedule_game_analysis_in_background", lambda game_id: None)
    await state_manager.finish_game(db_session, 8041, "1-0", termination="checkmate", final_pgn=pgn)
    await db_session.refresh(game)
    assert game.pgn == pgn
