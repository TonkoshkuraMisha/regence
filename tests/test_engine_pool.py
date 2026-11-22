# --- FILE: tests/test_engine_pool.py ---
"""
Пул процессов Stockfish (src/services/engine_pool.py) на поддельных движках: запуск, возврат в пул, отказы,
настройка опций, аренда EngineLease и реестр пулов. Настоящий бинарник не используется.
"""

import chess.engine
import pytest

from src.services import engine_pool
from src.services.engine_pool import (
    EngineBusyError,
    EngineLease,
    EnginePool,
    EngineUnavailableError,
    close_all_engine_pools,
    get_engine_pool,
)


class FakeOption:
    def __init__(self, type_, min_=None, max_=None):
        self.type, self.min, self.max = type_, min_, max_


class FakeReturncode:
    def __init__(self, done):
        self._done = done

    def done(self):
        return self._done


class FakeEngine:
    """Подобие SimpleEngine: опции, настройка, завершение."""

    def __init__(self, alive=True, quit_fails=False, close_fails=False):
        self.options = {"Skill Level": FakeOption("spin", 0, 20), "UCI_Elo": FakeOption("spin", 1320, 3190)}
        self.configured: list[dict] = []
        self.protocol = type("P", (), {"returncode": FakeReturncode(not alive)})()
        self.quit_fails, self.close_fails = quit_fails, close_fails
        self.quit_called = self.close_called = False

    def configure(self, opts):
        self.configured.append(opts)

    def quit(self):
        self.quit_called = True
        if self.quit_fails:
            raise RuntimeError("quit")

    def close(self):
        self.close_called = True
        if self.close_fails:
            raise RuntimeError("close")


@pytest.fixture
def pool(monkeypatch):
    p = EnginePool("fake-stockfish", size=1, acquire_timeout_s=0.05)
    spawned: list[FakeEngine] = []

    def spawn():
        e = FakeEngine()
        spawned.append(e)
        return e

    monkeypatch.setattr(p, "_spawn", spawn)
    p.spawned = spawned  # type: ignore[attr-defined]
    return p


def test_spawn_errors(monkeypatch, tmp_path):
    missing = EnginePool(str(tmp_path / "nope"), 1, 0.1)
    with pytest.raises(EngineUnavailableError):
        missing._spawn()

    exe = tmp_path / "sf"
    exe.write_text("x")
    p = EnginePool(str(exe), 1, 0.1)

    def boom(path):
        raise OSError("bad binary")

    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", staticmethod(boom))
    with pytest.raises(EngineUnavailableError, match="Cannot start"):
        p._spawn()

    sentinel = FakeEngine()
    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", staticmethod(lambda path: sentinel))
    assert p._spawn() is sentinel


def test_quit_falls_back_to_close_and_swallows():
    both_fail = FakeEngine(quit_fails=True, close_fails=True)
    EnginePool._quit(both_fail)  # type: ignore[arg-type]
    assert both_fail.quit_called and both_fail.close_called
    only_quit_fails = FakeEngine(quit_fails=True)
    EnginePool._quit(only_quit_fails)  # type: ignore[arg-type]
    assert only_quit_fails.close_called


def test_is_alive_handles_broken_engine():
    assert EnginePool._is_alive(FakeEngine(alive=True)) is True  # type: ignore[arg-type]
    assert EnginePool._is_alive(FakeEngine(alive=False)) is False  # type: ignore[arg-type]
    assert EnginePool._is_alive(object()) is False  # type: ignore[arg-type]


def test_configure_clamps_numeric_and_skips_unknown():
    e = FakeEngine()
    EnginePool._configure(e, {"UCI_Elo": 800, "Unknown": 1, "Skill Level": 99.0})  # type: ignore[arg-type]
    assert e.configured == [{"Skill Level": 20, "UCI_Elo": 1320}]
    e2 = FakeEngine()
    e2.options = {}
    EnginePool._configure(e2, {"Skill Level": 3})  # type: ignore[arg-type]
    assert e2.configured == []  # настраивать нечего


def test_engine_is_reused_after_healthy_release(pool):
    with pool.acquire() as first:
        pass
    with pool.acquire() as second:
        pass
    assert first is second and len(pool.spawned) == 1


def test_busy_pool_raises(pool):
    with pool.acquire():
        with pytest.raises(EngineBusyError), pool.acquire():
            pass
        with pytest.raises(EngineBusyError), pool.acquire(timeout_s=0.01):
            pass


def test_engine_error_discards_engine(pool):
    with pytest.raises(chess.engine.EngineError), pool.acquire():
        raise chess.engine.EngineError("protocol")
    assert pool.spawned[0].quit_called
    with pool.acquire() as fresh:
        pass
    assert fresh is not pool.spawned[0]


def test_dead_engine_is_not_returned_to_pool(pool):
    with pool.acquire() as e:
        e.protocol.returncode = FakeReturncode(True)
    assert e.quit_called


def test_close_pool_quits_idle_and_forbids_acquire(pool):
    with pool.acquire() as e:
        pass
    pool.close()
    assert e.quit_called
    with pytest.raises(EngineUnavailableError, match="closed"), pool.acquire():
        pass


def test_engine_returned_to_closed_pool_is_quit(pool):
    with pool.acquire() as e:
        pool.close()
    assert e.quit_called


def test_lease_holds_one_engine_across_uses(monkeypatch, pool):
    monkeypatch.setattr(engine_pool, "get_engine_pool", lambda path: pool)
    with EngineLease("x") as lease:
        with lease.use({"Skill Level": 5}) as a:
            pass
        with lease.use({"Skill Level": 7}) as b:
            pass
        assert a is b
    assert len(pool.spawned) == 1
    assert pool.spawned[0].configured[-1]["Skill Level"] == 7  # второй use() перенастроил движок
    # после закрытия аренды движок свободен
    with pool.acquire():
        pass


def test_lease_releases_broken_engine_and_takes_new_one(monkeypatch, pool):
    monkeypatch.setattr(engine_pool, "get_engine_pool", lambda path: pool)
    lease = EngineLease("x")
    with pytest.raises(TimeoutError), lease.use():
        raise TimeoutError
    assert pool.spawned[0].quit_called
    with lease.use() as fresh:
        pass
    lease.close()
    assert fresh is not pool.spawned[0]


def test_get_engine_pool_registry(monkeypatch):
    with pytest.raises(EngineUnavailableError):
        get_engine_pool(None)
    close_all_engine_pools()
    p1 = get_engine_pool("some/path/sf")
    assert get_engine_pool("some/path/sf") is p1
    p1.close()
    assert get_engine_pool("some/path/sf") is not p1  # закрытый пул заменяется
    close_all_engine_pools()
    assert engine_pool._pools == {}
