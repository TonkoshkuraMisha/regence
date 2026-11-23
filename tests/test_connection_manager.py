# --- FILE: tests/test_connection_manager.py ---
"""
WebSocket connection manager (src/services/connection_manager.py): presence in Redis, delivery between workers,
session revocation, spectators and Redis failure branches. Sockets and Redis are stubs, clock and sleep are patched.
"""

import asyncio
import json

import pytest

from src.services import connection_manager as cm
from src.services.connection_manager import (
    SESSION_REVOKED_EVENT,
    WS_CLOSE_SESSION_REVOKED,
    ConnectionManager,
    _is_session_revoked,
)


class FakeSocket:
    """WebSocket stub: remembers what was sent and the close codes, can "break"."""

    def __init__(self, fail_send=False, fail_close=False):
        self.sent: list[str] = []
        self.closed_with: int | None = None
        self.accepted = False
        self.fail_send = fail_send
        self.fail_close = fail_close

    async def accept(self):
        self.accepted = True

    async def send_text(self, text):
        if self.fail_send:
            raise RuntimeError("closed")
        self.sent.append(text)

    async def close(self, code=1000):
        if self.fail_close:
            raise RuntimeError("already closed")
        self.closed_with = code


class FakePubSub:
    """Redis subscription: a queue of ready messages and failure flags."""

    def __init__(self):
        self.subscribed = True
        self.messages: list[dict] = []
        self.fail_unsubscribe = False
        self.fail_subscribe = False
        self.subscribe_calls = 0

    async def subscribe(self, *args):
        self.subscribe_calls += 1
        if self.fail_subscribe:
            raise RuntimeError("redis down")

    async def unsubscribe(self, *args):
        if self.fail_unsubscribe:
            raise RuntimeError("redis down")

    async def get_message(self, **kwargs):
        if self.messages:
            return self.messages.pop(0)
        raise asyncio.CancelledError


@pytest.fixture
def mgr(override_redis):
    """A fresh manager on mock Redis, without background tasks."""
    from src.db.redis import redis_client  # already patched by an autouse fixture
    m = ConnectionManager()
    m.redis = redis_client
    m.pubsub = FakePubSub()
    m._ensure_background_tasks = lambda: None  # type: ignore[method-assign]
    return m


@pytest.fixture(autouse=True)
def no_game_side_effects(monkeypatch):
    """Disconnect/connect touches games and the queue; only the manager is checked here."""
    from src.services.game_state import state_manager
    from src.services.matchmaker import matchmaker

    calls: dict[str, list] = {"reconnect": [], "disconnect": [], "leave": []}

    async def reconnect(uid, _mgr):
        calls["reconnect"].append(uid)

    async def disconnect(uid, _mgr):
        calls["disconnect"].append(uid)

    async def leave(uid):
        calls["leave"].append(uid)

    monkeypatch.setattr(state_manager, "handle_player_reconnect", reconnect)
    monkeypatch.setattr(state_manager, "handle_player_disconnect", disconnect)
    monkeypatch.setattr(matchmaker, "leave_queue", leave)
    return calls


def test_is_session_revoked_filters_garbage():
    assert _is_session_revoked(json.dumps({"event": SESSION_REVOKED_EVENT}))
    assert not _is_session_revoked("plain")
    assert not _is_session_revoked(f"{SESSION_REVOKED_EVENT} not json")
    assert not _is_session_revoked(f'["{SESSION_REVOKED_EVENT}"]')  # a list: AttributeError


@pytest.mark.asyncio
async def test_ensure_background_tasks_creates_and_survives_no_loop(override_redis):
    m = ConnectionManager()
    m.pubsub = FakePubSub()
    m._ensure_background_tasks()
    assert m._listener_task is not None and m._heartbeat_task is not None
    for task in (m._listener_task, m._heartbeat_task):
        task.cancel()

    def boom(coro):
        coro.close()
        raise RuntimeError("no loop")

    m2 = ConnectionManager()
    m2.pubsub = FakePubSub()
    import unittest.mock as mock
    with mock.patch.object(asyncio, "create_task", boom):
        m2._ensure_background_tasks()  # RuntimeError is swallowed
    assert m2._listener_task is None


@pytest.mark.asyncio
async def test_heartbeat_refreshes_presence_and_survives_errors(mgr, monkeypatch):
    ws = FakeSocket()
    mgr._connections[ws] = (7, "c1")
    sleeps = {"n": 0}

    async def fake_sleep(_):
        sleeps["n"] += 1
        if sleeps["n"] > 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(cm.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(cm, "_now_ms", lambda: 1000)
    await_failures = {"n": 0}
    real_zadd = mgr.redis.zadd

    async def flaky_zadd(*args, **kwargs):
        await_failures["n"] += 1
        if await_failures["n"] == 1:
            raise RuntimeError("redis down")  # the first heartbeat fails, the loop lives
        return await real_zadd(*args, **kwargs)

    mgr.redis.zadd = flaky_zadd
    with pytest.raises(asyncio.CancelledError):
        await mgr._heartbeat_loop()
    assert mgr.redis.zsets["presence:user:7"] == {"c1": 1000}


@pytest.mark.asyncio
async def test_listener_delivers_remote_messages_and_skips_own(mgr, monkeypatch):
    ws = FakeSocket()
    mgr._user_sockets[5] = {ws}
    other = json.dumps({"origin": "other-worker", "data": json.dumps({"x": 1})})
    own = json.dumps({"origin": mgr.worker_id, "data": json.dumps({"x": 2})})
    mgr.pubsub.messages = [
        {"type": "subscribe", "channel": "user:5", "data": 1},
        {"type": "message", "channel": "weird:5", "data": other},
        {"type": "message", "channel": "user:5", "data": own},
        {"type": "message", "channel": "user:5", "data": other},
        {"type": "message", "channel": "user:bad", "data": other},  # int() fails -> log and sleep
    ]
    sleeps = {"n": 0}

    async def fake_sleep(_):
        sleeps["n"] += 1

    monkeypatch.setattr(cm.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await mgr._listen_pubsub()
    assert ws.sent == [json.dumps({"x": 1})]
    assert sleeps["n"] == 1


@pytest.mark.asyncio
async def test_listener_waits_while_unsubscribed(mgr, monkeypatch):
    mgr.pubsub.subscribed = False

    async def fake_sleep(_):
        raise asyncio.CancelledError

    monkeypatch.setattr(cm.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await mgr._listen_pubsub()


@pytest.mark.asyncio
async def test_remote_session_revoked_closes_local_sockets(mgr):
    ws, dead = FakeSocket(), FakeSocket(fail_close=True)
    mgr._user_sockets[3] = {ws, dead}
    await mgr._on_remote_message(3, json.dumps({"event": SESSION_REVOKED_EVENT}))
    assert ws.closed_with == WS_CLOSE_SESSION_REVOKED
    assert ws.sent  # message delivered before closing


def test_unwrap_envelope_variants(mgr):
    assert mgr._unwrap_envelope("not json {") == "not json {"
    assert mgr._unwrap_envelope('{"a": 1}') == '{"a": 1}'  # not an envelope
    assert mgr._unwrap_envelope(json.dumps({"origin": mgr.worker_id, "data": "x"})) is None
    assert mgr._unwrap_envelope(json.dumps({"origin": "zz", "data": "x"})) == "x"


@pytest.mark.asyncio
async def test_presence_errors_are_logged_not_raised(mgr):
    async def boom(*a, **k):
        raise RuntimeError("redis down")

    mgr.redis.zadd = boom
    mgr.redis.zrem = boom
    mgr.redis.zremrangebyscore = boom
    await mgr._presence_add(1, "c")
    await mgr._presence_remove(1, "c")
    assert await mgr.is_user_online(1) is False


@pytest.mark.asyncio
async def test_is_user_online_uses_redis_presence_and_prunes_stale(mgr, monkeypatch):
    monkeypatch.setattr(cm, "_now_ms", lambda: 1_000_000)
    await mgr.redis.zadd("presence:user:9", {"fresh": 999_000, "stale": 1})
    assert await mgr.is_user_online(9) is True
    assert "stale" not in mgr.redis.zsets["presence:user:9"]
    await mgr.redis.zrem("presence:user:9", "fresh")
    assert await mgr.is_user_online(9) is False


@pytest.mark.asyncio
async def test_connect_registers_and_handles_subscribe_failure(mgr, no_game_side_effects):
    mgr.pubsub.fail_subscribe = True
    ws = FakeSocket()
    await mgr.connect(ws, 11)
    assert ws.accepted and mgr.active_connections[11] is ws
    assert no_game_side_effects["reconnect"] == [11]
    assert "presence:user:11" in mgr.redis.zsets


@pytest.mark.asyncio
async def test_disconnect_one_of_two_tabs_keeps_user_online(mgr, no_game_side_effects):
    a, b = FakeSocket(), FakeSocket()
    await mgr.connect(a, 4)
    await mgr.connect(b, 4)
    await mgr.disconnect(4, a)
    assert mgr.active_connections[4] is b
    assert no_game_side_effects["disconnect"] == []


@pytest.mark.asyncio
async def test_disconnect_last_tab_runs_full_cleanup(mgr, no_game_side_effects):
    ws = FakeSocket()
    await mgr.connect(ws, 4)
    await mgr.add_spectator(10, 4)
    await mgr.disconnect(4)  # websocket=None: close all local ones
    assert 4 not in mgr.active_connections
    assert no_game_side_effects["leave"] == [4]
    assert no_game_side_effects["disconnect"] == [4]
    assert await mgr.get_spectator_ids(10) == set()


@pytest.mark.asyncio
async def test_disconnect_unsubscribe_failure_is_ignored(mgr, no_game_side_effects):
    ws = FakeSocket()
    await mgr.connect(ws, 6)
    mgr.pubsub.fail_unsubscribe = True
    await mgr.disconnect(6, ws)
    assert no_game_side_effects["disconnect"] == [6]


@pytest.mark.asyncio
async def test_disconnect_resubscribes_when_user_reconnected_during_unsubscribe(mgr, no_game_side_effects):
    ws, new = FakeSocket(), FakeSocket()
    await mgr.connect(ws, 8)
    calls_before = mgr.pubsub.subscribe_calls

    async def unsubscribe_and_reconnect(*a):
        mgr._user_sockets.setdefault(8, set()).add(new)

    mgr.pubsub.unsubscribe = unsubscribe_and_reconnect
    await mgr.disconnect(8, ws)
    assert mgr.pubsub.subscribe_calls == calls_before + 1
    assert no_game_side_effects["disconnect"] == []

    # same, but re-subscribing fails: only a log
    mgr._user_sockets[8] = {ws}
    mgr._connections[ws] = (8, "x")
    mgr.pubsub.fail_subscribe = True
    await mgr.disconnect(8, ws)
    assert no_game_side_effects["disconnect"] == []


@pytest.mark.asyncio
async def test_disconnect_returns_early_if_online_on_other_worker(mgr, no_game_side_effects):
    ws = FakeSocket()
    await mgr.connect(ws, 12)
    await mgr.redis.zadd("presence:user:12", {"other-worker-conn": cm._now_ms()})
    await mgr.disconnect(12, ws)
    assert no_game_side_effects["leave"] == []
    assert no_game_side_effects["disconnect"] == []


@pytest.mark.asyncio
async def test_disconnect_online_after_queue_leave_and_after_game_disconnect(mgr, monkeypatch, no_game_side_effects):
    from src.services.game_state import state_manager
    from src.services.matchmaker import matchmaker

    # 1) the user appeared on another worker while leaving the queue
    ws = FakeSocket()
    await mgr.connect(ws, 13)

    async def leave_then_appear(uid):
        await mgr.redis.zadd(f"presence:user:{uid}", {"remote": cm._now_ms()})

    monkeypatch.setattr(matchmaker, "leave_queue", leave_then_appear)
    await mgr.disconnect(13, ws)
    assert no_game_side_effects["disconnect"] == []

    # 2) appeared while the game disconnect was being handled: the disconnect is rolled back
    ws2 = FakeSocket()
    await mgr.connect(ws2, 14)
    no_game_side_effects["reconnect"].clear()

    async def leave_noop(uid):
        pass

    async def disconnect_then_appear(uid, _m):
        await mgr.redis.zadd(f"presence:user:{uid}", {"remote": cm._now_ms()})

    monkeypatch.setattr(matchmaker, "leave_queue", leave_noop)
    monkeypatch.setattr(state_manager, "handle_player_disconnect", disconnect_then_appear)
    await mgr.disconnect(14, ws2)
    assert no_game_side_effects["reconnect"] == [14]


@pytest.mark.asyncio
async def test_deliver_local_drops_dead_sockets(mgr):
    good, dead = FakeSocket(), FakeSocket(fail_send=True)
    mgr._user_sockets[2] = {good, dead}
    mgr.active_connections[2] = dead
    assert await mgr._deliver_local(2, "hi") is True
    assert good.sent == ["hi"]
    assert dead not in mgr._user_sockets[2]
    assert 2 not in mgr.active_connections or mgr.active_connections[2] is not dead
    assert await mgr._deliver_local(99, "hi") is False


@pytest.mark.asyncio
async def test_revoke_sessions_notifies_and_closes(mgr):
    ws = FakeSocket()
    mgr._user_sockets[15] = {ws}
    await mgr.revoke_sessions(15)
    assert json.loads(ws.sent[0]) == {"event": SESSION_REVOKED_EVENT}
    assert ws.closed_with == WS_CLOSE_SESSION_REVOKED


@pytest.mark.asyncio
async def test_send_personal_message_survives_publish_failure(mgr):
    ws = FakeSocket()
    mgr._user_sockets[16] = {ws}

    async def boom(*a):
        raise RuntimeError("redis down")

    mgr.redis.publish = boom
    await mgr.send_personal_message({"k": 1}, 16)
    assert ws.sent == [json.dumps({"k": 1})]


@pytest.mark.asyncio
async def test_spectators_lifecycle(mgr):
    a, b = FakeSocket(), FakeSocket()
    mgr._user_sockets[1] = {a}
    mgr._user_sockets[2] = {b}
    await mgr.add_spectator(50, 1)
    await mgr.add_spectator(50, 2)
    assert await mgr.get_spectator_ids(50) == {1, 2}
    await mgr.broadcast_to_spectators(50, {"m": 1})
    assert a.sent and b.sent

    # one game can be watched at a time
    await mgr.add_spectator(51, 1)
    assert await mgr.get_spectator_ids(50) == {2}

    # detaching from someone else's game does not erase the back reference
    await mgr.remove_spectator(50, 1)
    assert await mgr.redis.get("user:1:spectating") == "51"
    await mgr.remove_spectator(51, 1)
    assert await mgr.redis.get("user:1:spectating") is None
