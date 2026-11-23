# --- FILE: src/services/engine_pool.py ---
"""
A pool of long-lived Stockfish processes.

Previously every bot or analysis request started a new engine process (popen_uci) -- that is
hundreds of milliseconds to start and an unbounded number of parallel processes under load.
The pool keeps at most ENGINE_POOL_SIZE processes per binary, reuses them between
requests and limits the number of simultaneous calculations: when the pool is exhausted a waiting
call gets EngineBusyError on timeout rather than spawning a new process.

The pool is synchronous and thread-safe: it is used from asyncio.to_thread (API) and from Celery.

Settings (src/core/config.py): ENGINE_POOL_SIZE -- the process limit, ENGINE_ACQUIRE_TIMEOUT_S -- how many seconds to wait
for a
free engine. The pool lives in process memory: every API process and every Celery worker has its own pool, so
the limit applies per process, not to the whole server. The path to the binary is passed by the caller
(bots/base.resolve_stockfish_path). Prometheus metrics -- engine busy time, waiting and refusals by kind of work.
"""

import atexit
import logging
import os
import queue
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar

import chess.engine
from prometheus_client import Counter, Histogram

from src.core.config import settings

logger = logging.getLogger(__name__)

# Options that bots change for their own style. Before every engine hand-out they are reset
# to full-strength values so that the settings of one call do not "leak" into the next.
_DEFAULT_OPTIONS: dict[str, int | bool] = {
    "Skill Level": 20,
    "UCI_LimitStrength": False,
}


# --- Engine budget (task 23.3): time while the engine is busy, by kind of work ---------------------------------
# The main cost item is the Stockfish CPU. Every engine hand-out from the pool credits the time it was busy
# to the kind of work from the call context (engine_work). Labels come from the finite set ENGINE_WORK_KINDS.

ENGINE_WORK_KINDS = ("bot_move", "analysis", "coach", "simulation", "puzzles", "other")
_work_kind: ContextVar[str] = ContextVar("engine_work_kind", default="other")

ENGINE_SECONDS = Counter(
    "regence_engine_seconds_total", "Time Stockfish engines were held from the pool, by kind of work", ["kind"],
)
ENGINE_ACQUIRE_WAIT_SECONDS = Histogram(
    "regence_engine_acquire_wait_seconds", "Waiting for a free engine in the pool", ["kind"],
    buckets=(0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
ENGINE_BUSY = Counter("regence_engine_busy_total", "Requests refused because every engine was busy", ["kind"])


@contextmanager
def engine_work(kind: str) -> Iterator[None]:
    """
    The kind of work for engine time accounting inside a block. The outer kind matters more than the inner: a bot move in a
    tournament simulation
    is credited to the simulation. The context survives asyncio.to_thread (contextvars are copied into the thread).
    """
    if kind not in ENGINE_WORK_KINDS:
        kind = "other"
    if _work_kind.get() != "other":
        yield
        return
    token = _work_kind.set(kind)
    try:
        yield
    finally:
        _work_kind.reset(token)


def current_engine_work() -> str:
    """The kind of work of the current call context; outside an engine_work block -- "other"."""
    return _work_kind.get()


class EngineUnavailableError(RuntimeError):
    """The Stockfish binary is missing or does not start."""


class EngineBusyError(RuntimeError):
    """All the pool's engines have been busy longer than the allowed wait time."""


class EnginePool:
    """
    A pool of Stockfish processes of one binary: at most size processes, idle ones are reused. acquire hands out
    an engine for the duration of a calculation; if none is free for longer than acquire_timeout_s -- EngineBusyError.
    """
    def __init__(self, engine_path: str, size: int, acquire_timeout_s: float):
        self.engine_path = engine_path
        self.size = max(1, int(size))
        self.acquire_timeout_s = acquire_timeout_s
        # The semaphore limits the number of simultaneously handed-out engines; idle started processes sit in the queue
        # (the last one released is handed out first). A process is started only on hand-out, when there are no idle ones.
        self._slots = threading.BoundedSemaphore(self.size)
        self._idle: queue.LifoQueue[chess.engine.SimpleEngine] = queue.LifoQueue()
        self._closed = False

    def _spawn(self) -> chess.engine.SimpleEngine:
        if not os.path.exists(self.engine_path):
            raise EngineUnavailableError(f"Stockfish not found: {self.engine_path}")
        try:
            return chess.engine.SimpleEngine.popen_uci(self.engine_path)
        except Exception as exc:
            raise EngineUnavailableError(f"Cannot start Stockfish ({self.engine_path}): {exc}") from exc

    @staticmethod
    def _quit(engine: chess.engine.SimpleEngine) -> None:
        try:
            engine.quit()
        except Exception:
            try:
                engine.close()
            except Exception:
                pass

    @staticmethod
    def _is_alive(engine: chess.engine.SimpleEngine) -> bool:
        """The engine process is still running (the calling code may have swallowed EngineTerminatedError)."""
        try:
            return not engine.protocol.returncode.done()
        except Exception:
            return False

    @staticmethod
    def _configure(engine: chess.engine.SimpleEngine, options: dict) -> None:
        """
        Configures the engine before hand-out: full-strength values (_DEFAULT_OPTIONS), with the caller's options on top.
        Options that this engine build does not have are skipped; numeric ones are clamped to its allowed range
        (for example, UCI_Elo below the build's minimum becomes the minimum).
        """
        merged = {**_DEFAULT_OPTIONS, **options}
        supported: dict = {}
        for name, value in merged.items():
            option = engine.options.get(name)
            if option is None:
                continue
            # Numeric (spin) options are clamped to the range of the specific engine build.
            if option.type == "spin" and isinstance(value, (int, float)) and not isinstance(value, bool):
                if option.min is not None:
                    value = max(option.min, value)
                if option.max is not None:
                    value = min(option.max, value)
                value = int(value)
            supported[name] = value
        if supported:
            engine.configure(supported)

    @contextmanager
    def acquire(self, options: dict | None = None, timeout_s: float | None = None) -> Iterator[chess.engine.SimpleEngine]:
        """
        Hands out an engine for exclusive use for the duration of the with block.

        options -- UCI options on top of the defaults (full strength).
        An engine that failed with a protocol error or a timeout is not returned to the pool but
        terminated; a new process will be started instead on the next request.
        timeout_s -- how long to wait for a free engine (by default the pool's acquire_timeout_s); if it did not arrive --
        EngineBusyError. The wait time and the time the engine was handed out are written to the metrics by kind of work
        (current_engine_work).
        """
        if self._closed:
            raise EngineUnavailableError("Engine pool is closed")

        wait = self.acquire_timeout_s if timeout_s is None else timeout_s
        kind = current_engine_work()
        waiting_since = time.perf_counter()
        if not self._slots.acquire(timeout=wait):
            ENGINE_BUSY.labels(kind).inc()
            raise EngineBusyError("All chess engines are busy")
        held_since = time.perf_counter()
        ENGINE_ACQUIRE_WAIT_SECONDS.labels(kind).observe(held_since - waiting_since)

        engine: chess.engine.SimpleEngine | None = None
        healthy = True
        try:
            try:
                engine = self._idle.get_nowait()
            except queue.Empty:
                engine = self._spawn()

            self._configure(engine, options or {})
            yield engine
        except (chess.engine.EngineError, TimeoutError):
            healthy = False
            raise
        finally:
            if engine is not None:
                if healthy and not self._closed and self._is_alive(engine):
                    self._idle.put(engine)
                else:
                    self._quit(engine)
            self._slots.release()
            ENGINE_SECONDS.labels(kind).inc(time.perf_counter() - held_since)

    def close(self) -> None:
        """
        Closes the pool: terminates idle engines and forbids new hand-outs. An engine handed out at this moment
        terminates when it is returned.
        """
        self._closed = True
        while True:
            try:
                engine = self._idle.get_nowait()
            except queue.Empty:
                break
            self._quit(engine)


class EngineLease:
    """
    One pool engine for several calls in a row -- for example, for a bot move: MultiPV analysis, a reference move with
    strength limiting and the evaluation of that move. Without a lease every step queued up in the pool anew: under load a move
    waited for an engine 2-3 times and could get EngineBusyError in the middle.

    The engine is taken on the first use() (if the engine is never needed the pool is not touched) and held until close().
    UCI options are set anew on every use() on top of full strength, as in acquire(). A protocol error or a timeout
    inside use() immediately returns the engine to the pool as broken; the next use() takes a new one.
    """

    def __init__(self, engine_path: str | None):
        self.engine_path = engine_path
        self._stack: ExitStack | None = None
        self._engine: chess.engine.SimpleEngine | None = None

    @contextmanager
    def use(self, options: dict | None = None) -> Iterator[chess.engine.SimpleEngine]:
        """
        The lease's engine: on first access it is taken from the pool and stays with the lease until its end, on later ones
        it is only
        reconfigured. An engine error returns it to the pool.
        """
        fresh = self._engine is None
        if self._engine is None:
            stack = ExitStack()
            self._engine = stack.enter_context(get_engine_pool(self.engine_path).acquire(options))
            self._stack = stack
        try:
            if not fresh:
                EnginePool._configure(self._engine, options or {})
            yield self._engine
        except (chess.engine.EngineError, TimeoutError):
            self._release(*sys.exc_info())
            raise

    def _release(self, *exc_info) -> None:
        """
        Returns the lease's engine to the pool; exc_info -- the error with which it is returned (then the pool terminates
        it).
        """
        stack, self._stack, self._engine = self._stack, None, None
        if stack is not None:
            stack.__exit__(*exc_info)

    def close(self) -> None:
        self._release(None, None, None)

    def __enter__(self) -> EngineLease:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


_pools: dict[str, EnginePool] = {}
_pools_lock = threading.Lock()


def get_engine_pool(engine_path: str | None) -> EnginePool:
    """
    Returns the pool for the given binary (one pool per path, created lazily). Size and wait time --
    from the settings ENGINE_POOL_SIZE and ENGINE_ACQUIRE_TIMEOUT_S at the time of creation. An empty path --
    EngineUnavailableError.
    """
    if not engine_path:
        raise EngineUnavailableError("Stockfish path is not configured")
    key = os.path.abspath(engine_path)
    with _pools_lock:
        pool = _pools.get(key)
        if pool is None or pool._closed:
            pool = EnginePool(key, settings.ENGINE_POOL_SIZE, settings.ENGINE_ACQUIRE_TIMEOUT_S)
            _pools[key] = pool
        return pool


def close_all_engine_pools() -> None:
    """Closes all the process's pools and forgets them; the next get_engine_pool creates a new one. Called on exit."""
    with _pools_lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        pool.close()


# python-chess keeps a background NON-daemon thread for every SimpleEngine. The interpreter waits for
# such threads before calling ordinary atexit handlers, so a process (a Celery worker, pytest)
# with an open pool would hang on exit. threading._register_atexit fires before this
# wait (concurrent.futures terminates the same way); atexit is a fallback.
_register_early_exit_hook = getattr(threading, "_register_atexit", None)
if _register_early_exit_hook is not None:
    _register_early_exit_hook(close_all_engine_pools)
else:
    atexit.register(close_all_engine_pools)
