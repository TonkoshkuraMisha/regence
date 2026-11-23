# --- FILE: src/services/game_state.py ---
"""
State of a running game between humans: position, clocks, completion. The source of truth during the game is Redis.

Where it lives (Redis): the hash game:{id}:state (position, move record, side times, the moment of the last move, state
version, draw and rematch offers, berserk, lag quota spending, disconnect marks), the log of processed
commands game:{id}:commands, the move log with telemetry game:{id}:moves, the player's link to the game
user:{id}:current_game, the set of running games active_games, the deadlines game_deadlines, the registry of games finished
in Redis but not
yet written to the DB games:pending_finish and the key of the timeout loop leader timeouts:leader. Into the games table
the state is copied after every move (sync_authoritative_state_to_db); if the hash is lost it is restored from
it (_recover_state_from_db).
Called by: src/api/websockets.py (moves, resignation, draw, berserk), src/api/profile.py and src/api/fair_play.py (reading
the state), src/services/connection_manager.py (player disconnect and return), src/services/arena.py (berserk),
src/main.py (starting the timeout loop).

A move (process_atomic_move) is one Redis transaction (WATCH/MULTI): move order, version, legality
(src/services/game_engine.py), time deduction, the new position. A repeat of the same command (command_id) is not applied.

Clocks: time runs for the side to move, from the moment of the last move by the server clock; a connection break does not
stop it. The lag quota is LAG_PER_MOVE_MS and LAG_PER_GAME_MS: network delay (server time minus the
thinking time stated by the client) is returned to the player within the quota, and the flag falls with a delay by its
remainder.

Completion: mate and draws -- on a move (the flag also falls there if the player managed to move after the deadline); a flag
without a move,
a no-show for the first move (30 s) and an abandoned game (ABANDON_TIMEOUT_MS) are handled by the
loop check_timeouts_loop, which is run by one leader process and checks only games whose deadline has come.
Only one claimant can finish a game (claim_game_end). finish_game records the result: rating
(src/services/rating.py), moves with telemetry into moves, the anti-cheat assessment, arena points, queuing the analysis in
the background.
If the process crashed between finishing in Redis and writing to the database, the game is completed by the reconciliation
(reconcile_unfinished_games).
"""

import asyncio
import datetime
import json
import logging
import time
from datetime import UTC

import chess
import chess.pgn
from redis.exceptions import WatchError
from sqlalchemy import select
from sqlalchemy.sql import func

from src.core.instance import WORKER_ID
from src.core.observability import GAMES_FINISHED, TIMEOUT_CHECK_FAILURES, bounded_label
from src.db.redis import redis_client
from src.db.session import AsyncSessionLocal
from src.models.game import Game, GameStatus
from src.models.move import Move
from src.models.user import User
from src.services import openings, product_metrics
from src.services.anticheat import evaluate_game_telemetry
from src.services.game_engine import (  # noqa: F401  (flag_outcome is re-exported for tests)
    FLAG_DRAW_TERMINATION,
    STARTING_FEN,
    board_from_fen,
    engine,
    flag_outcome,
    side_has_mating_material,
)
from src.services.odds import pgn_header
from src.services.rating import classify_time_control, elo_calculator
from src.services.task_dispatch import schedule_game_analysis_in_background

logger = logging.getLogger(__name__)


# Fields of the state hash that _coerce_state converts to int (in Redis everything is stored as strings).
_INT_STATE_KEYS = (
    "white_id", "black_id", "white_time_ms", "black_time_ms",
    "base_time_ms", "increment_ms", "last_move_at",
    "white_disconnect_started_at", "black_disconnect_started_at",
    "state_version", "white_lag_ms", "black_lag_ms",
)

# Lag quota (task 33.3, docs/research/arenas.md): time lost on sending a move over the network is returned to the player --
# no more than LAG_PER_MOVE_MS per move and LAG_PER_GAME_MS per game. Move lag = server clock time minus the
# thinking time stated by the client; the client is trusted only within the quota, so one cannot gain more than it.
LAG_PER_MOVE_MS = 300
LAG_PER_GAME_MS = 2000

# How many seconds the hash of an already finished game stays in Redis after restoration from the DB (for a rematch and chat).
FINISHED_STATE_TTL_S = 6 * 60 * 60
# How long a disconnected player may be absent before losing for an abandoned game (3 minutes).
ABANDON_TIMEOUT_MS = 3 * 60 * 1000
# The result code when a game is abandoned but the remaining player has no material to mate: a draw instead of a win.
ABANDON_DRAW_TERMINATION = "abandoned_vs_insufficient_material"

# The key of the timeout loop leader and its lifetime: the leader renews the key on every pass (every 0.5 s), so
# a crashed leader loses the role in no more than TIMEOUTS_LEADER_TTL_MS.
TIMEOUTS_LEADER_KEY = "timeouts:leader"
TIMEOUTS_LEADER_TTL_MS = 3000

# A game on which the timeout check fails is postponed: 1 s, 2 s, 4 s ... up to 30 s.
TIMEOUT_RETRY_BASE_MS = 1000
TIMEOUT_RETRY_MAX_MS = 30_000
# How often (every Nth failure in a row) to write the full stack to the log for the same game.
TIMEOUT_FAILURE_LOG_EVERY = 20

# Games finished in Redis but not yet written to the DB: id -> finish moment (ms).
# The entry is added in the same transaction as the status change and removed only after
# the result is committed to the DB. If the process crashed between these steps, the reconciliation completes the game.
PENDING_FINISH_KEY = "games:pending_finish"
# How long to wait for the regular handler before completing a game by reconciliation.
RECONCILE_GRACE_MS = 30_000
# How often the timeout loop leader runs the Redis/DB reconciliation.
RECONCILE_INTERVAL_MS = 30_000


def _coerce_state(raw: dict) -> dict:
    """Converts the numeric fields of a raw Redis hash to int (returns a new dict)."""
    state = dict(raw)
    for key in _INT_STATE_KEYS:
        value = state.get(key)
        if value is not None and str(value).lstrip("-").isdigit():
            state[key] = int(value)
    if not state.get("board_fen"):
        state["board_fen"] = STARTING_FEN
    return state


def is_rated_state(state: dict) -> bool:
    """Whether the game is rated. States created before friendly games appeared have no such field -- they are rated."""
    return str(state.get("is_rated", "1")) != "0"


def pending_draw_offer(state: dict) -> int | None:
    """The id of the player whose draw offer is currently in force, or None."""
    offer = str(state.get("draw_offer") or "")
    return int(offer) if offer.isdigit() else None


def _move_rejection(reason: str, raw_state: dict) -> dict:
    """
    A refusal of a move together with the current position. The client shows its own move at once without waiting for
    the server, so without the position in the response the rejected move would stay on its board.
    """
    version = str(raw_state.get("state_version", 0))
    return {
        "status": "error",
        "reason": reason,
        "state_version": int(version) if version.isdigit() else 0,
        "fen": raw_state.get("board_fen") or STARTING_FEN,
        "pgn": raw_state.get("pgn", ""),
    }


def side_to_move(state: dict) -> str:
    """Whose move: "white" or "black" (the turn field may also be "w"; White moves by default)."""
    return "white" if state.get("turn", "white") in ("white", "w") else "black"


def is_hourglass(state: dict) -> bool:
    """A game with an "hourglass" clock (odds, 21.1): the time spent by the mover is added to the opponent."""
    return str(state.get("hourglass") or "") == "1"


def live_clock_ms(state: dict, color: str, now_ms: int) -> int:
    """
    The player's actual remaining time. The clock runs only for the side to move and is always
    counted from last_move_at -- a connection break does not affect it. With an "hourglass" clock the waiting side's
    time grows by as much as the mover's decreases.
    """
    stored = int(state[f"{color}_time_ms"])
    elapsed = max(0, now_ms - int(state["last_move_at"]))
    if color != side_to_move(state):
        return stored + elapsed if is_hourglass(state) else stored
    return stored - elapsed


def clocks_after_move(
        mover_ms: int, waiting_ms: int, spent_ms: int, increment_ms: int, hourglass: bool,
) -> tuple[int, int]:
    """
    The clocks of the mover and the waiting side after a move (a pure rule). spent_ms is the time spent by the mover minus the
    returned lag; the mover gets the increment, and with an "hourglass" clock the waiting side gets the time spent by the
    mover.
    """
    return mover_ms - spent_ms + increment_ms, waiting_ms + (spent_ms if hourglass else 0)


def lag_allowance_ms(state: dict, color: str) -> int:
    """How much lag can still be returned to a side for one move: the remaining game quota, but no more than the move quota."""
    used = int(state.get(f"{color}_lag_ms") or 0)
    return max(0, min(LAG_PER_MOVE_MS, LAG_PER_GAME_MS - used))


def lag_credit_ms(state: dict, color: str, elapsed_ms: int, client_elapsed_ms: int | None) -> int:
    """Time refund for a move: lag (the server counted more than the client thought) within the quota; without data -- 0."""
    if client_elapsed_ms is None:
        return 0
    return max(0, min(elapsed_ms - max(0, client_elapsed_ms), lag_allowance_ms(state, color)))


def is_berserk(state: dict, color: str) -> bool:
    """The side played "berserk" (33.3): half the base time, no increment."""
    return str(state.get(f"{color}_berserk") or "") == "1"


def berserk_fields(state: dict) -> dict:
    """Game snapshot fields for the client: whether berserk is available in this game and who has already played it."""
    return {
        "berserk_allowed": state.get("berserk_allowed") == "1",
        "white_berserk": is_berserk(state, "white"),
        "black_berserk": is_berserk(state, "black"),
    }


def abandon_wait_ms(state: dict, color: str, now_ms: int) -> int:
    """How much longer a disconnected player may be absent before losing (for the opponent's countdown)."""
    wait = ABANDON_TIMEOUT_MS
    if color == side_to_move(state):
        wait = min(wait, max(0, live_clock_ms(state, color, now_ms)))
    return wait


def evaluate_clock_expiry(state: dict, now_ms: int) -> tuple[str, int | None, str] | None:
    """
    Pure check of a flag / abandoned game by state (already converted by _coerce_state).
    Returns (result, winner_id, reason) or None if the game continues.

    1. Flag: the side to move has run out of time -- regardless of whether it is connected.
       The flag falls with a delay by the available lag quota (33.3): a move sent in time but
       delayed in the network may still arrive and be counted (process_atomic_move).
    2. Abandoned game: a player disconnected for longer than ABANDON_TIMEOUT_MS (their clock may
       not even be running if it is currently the opponent's move).
    """
    white_id, black_id = int(state["white_id"]), int(state["black_id"])

    mover = side_to_move(state)
    if live_clock_ms(state, mover, now_ms) + lag_allowance_ms(state, mover) <= 0:
        result, termination = flag_outcome(state.get("board_fen"), mover)
        if result == "1/2-1/2":
            return result, None, termination
        return result, (black_id if mover == "white" else white_id), termination

    for color in ("white", "black"):
        if state.get(f"{color}_disconnected") != "true":
            continue
        started_at = int(state.get(f"{color}_disconnect_started_at") or 0)
        if started_at > 0 and now_ms - started_at >= ABANDON_TIMEOUT_MS:
            stayed = "black" if color == "white" else "white"
            # As with a flag: if the remaining player cannot deliver mate by any
            # sequence of moves, we do not award them a win -- a draw.
            if not side_has_mating_material(state.get("board_fen"), stayed):
                return "1/2-1/2", None, ABANDON_DRAW_TERMINATION
            if color == "white":
                return "0-1", black_id, "abandoned"
            return "1-0", white_id, "abandoned"
    return None


# A sorted set "game id -> the nearest clock check deadline (ms)"; maintained via next_timeout_deadline_ms.
GAME_DEADLINES_KEY = "game_deadlines"


def next_timeout_deadline_ms(state: dict) -> int:
    """
    The next moment (absolute ms) when a game may see a flag, abandonment or
    a first-move no-show -- the minimum of the applicable deadlines. Used only as the score in
    the sorted set GAME_DEADLINES_KEY so that check_timeouts_once does not iterate over all
    active games every 0.5 s but takes via ZRANGEBYSCORE only those whose deadline has come.
    It does not replace evaluate_clock_expiry -- that decides the outcome by the current state at the moment of
    the check itself, and this is only the planning of the next wake-up.
    """
    last_move_at = int(state.get("last_move_at", 0) or 0)
    mover = side_to_move(state)
    deadlines = [last_move_at + int(state.get(f"{mover}_time_ms", 0) or 0) + lag_allowance_ms(state, mover)]

    if int(state.get("state_version", 0) or 0) < 2:
        deadlines.append(last_move_at + 30000)

    for color in ("white", "black"):
        if state.get(f"{color}_disconnected") == "true":
            started_at = int(state.get(f"{color}_disconnect_started_at", 0) or 0)
            if started_at > 0:
                deadlines.append(started_at + ABANDON_TIMEOUT_MS)

    return min(deadlines)


class GameStateManager:
    """
    The state of running games in Redis and their completion (details in the module description). The only instance --
    state_manager.
    """
    def __init__(self):
        self.redis = redis_client
        # game_id -> (failures in a row, do not check before, ms) -- for the timeout check
        self._timeout_failures: dict[int, tuple[int, int]] = {}
        # Redis/DB reconciliation (leader of the timeout loop only): 0 -- the first pass right at start.
        self._last_reconcile_ms = 0
        self._missing_state_seen: set[int] = set()

    def _get_key(self, game_id: int) -> str:
        return f"game:{game_id}:state"

    async def initialize_game(
            self, game_id: int, white_id: int, black_id: int, base_time_ms: int, increment_ms: int,
            is_rated: bool = True, start_fen: str | None = None, white_time_ms: int | None = None,
            black_time_ms: int | None = None, arena: dict | None = None, hourglass: bool = False,
    ):
        """
        Creates the state of a new game in Redis, adds it to active_games, game_deadlines and sets the players'
        user:{id}:current_game. Clocks -- base_time_ms for each side unless a custom time is passed (odds).
        arena -- an arena game (33.3): {"arena_id": ..., "berserk_allowed": bool} -- goes into the game state.
        hourglass -- an "hourglass" clock (odds, 21.1).
        """
        now_ms = int(time.time() * 1000)
        state = {
            "white_id": str(white_id),
            "black_id": str(black_id),
            "is_rated": "1" if is_rated else "0",
            "board_fen": start_fen or STARTING_FEN,
            # A game from a position (odds): the PGN starts with the SetUp/FEN headers.
            "pgn": pgn_header(start_fen) if start_fen else "",
            "state_version": "0",
            "white_time_ms": str(white_time_ms if white_time_ms is not None else base_time_ms),
            "black_time_ms": str(black_time_ms if black_time_ms is not None else base_time_ms),
            "base_time_ms": str(base_time_ms),
            "increment_ms": str(increment_ms),
            "last_move_at": str(now_ms),
            "turn": "white",
            "status": "in_progress",
            "white_disconnected": "false",
            "black_disconnected": "false",
            "white_disconnect_started_at": "0",
            "black_disconnect_started_at": "0",
            "draw_offer": "",
            "rematch_offer": "",
            "hourglass": "1" if hourglass else "0",
        }
        if arena:
            state["arena_id"] = str(arena["arena_id"])
            state["berserk_allowed"] = "1" if arena.get("berserk_allowed") else "0"
        await self.redis.hset(self._get_key(game_id), mapping=state)
        await self.redis.sadd("active_games", str(game_id))
        await self.redis.zadd(GAME_DEADLINES_KEY, {str(game_id): next_timeout_deadline_ms(state)})
        await self.redis.set(f"user:{white_id}:current_game", str(game_id))
        await self.redis.set(f"user:{black_id}:current_game", str(game_id))

    init_game = initialize_game  # the former method name, kept for compatibility (not used in src/)

    async def get_active_game_id(self, user_id: int) -> int | None:
        """
        The id of the game the player is playing now, or None. A stale link
        user:{id}:current_game (the game is already finished) is deleted along the way.
        """
        key = f"user:{int(user_id)}:current_game"
        raw = await self.redis.get(key)
        if not raw:
            return None
        game_id = int(raw)
        state = await self.get_game_state(game_id)
        if state and state.get("status") == "in_progress" and int(user_id) in (
                int(state["white_id"]), int(state["black_id"])):
            return game_id
        if await self.redis.get(key) == raw:
            await self.redis.delete(key)
        return None

    async def get_game_state(self, game_id: int) -> dict | None:
        """The game state from Redis (numbers converted to int); if the hash is missing -- restoration from the DB or None."""
        state = await self.redis.hgetall(self._get_key(game_id))
        if not state:
            return await self._recover_state_from_db(game_id)
        return _coerce_state(state)

    async def claim_game_end(
            self,
            game_id: int,
            result: str,
            termination: str,
            status: str = "completed",
            guard=None,
    ) -> dict | None:
        """
        Atomically moves a game from in_progress to a final status (WATCH/MULTI).

        This is the only point of "capturing" a game's completion: of several concurrent
        claimants (resignation, draw, flag, abort, abandoned game) exactly one succeeds,
        and only it should call finish_game / abort_game and broadcast game_over.
        On capture the game enters the PENDING_FINISH_KEY registry (for reconciliation) and leaves game_deadlines.

        guard(state) -> bool -- an additional condition rechecked on the fresh state
        inside the transaction (for example, that the flag has indeed fallen and the draw offer is still in force).

        Returns the game state at the moment of capture or None if the game was already finished by
        someone else or guard is not satisfied.
        """
        game_key = self._get_key(game_id)
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(game_key)
                    raw = await pipe.hgetall(game_key)
                    if not raw or raw.get("status") != "in_progress":
                        await pipe.unwatch()
                        return None

                    state = _coerce_state(raw)
                    if guard is not None and not guard(state):
                        await pipe.unwatch()
                        return None

                    ended_at = int(time.time() * 1000)
                    pipe.multi()
                    pipe.hset(game_key, mapping={
                        "status": status,
                        "result": result,
                        "termination": termination,
                        "ended_at": str(ended_at),
                    })
                    pipe.zadd(PENDING_FINISH_KEY, {str(game_id): ended_at})
                    pipe.zrem(GAME_DEADLINES_KEY, str(game_id))
                    await pipe.execute()
                    return state
                except WatchError:
                    continue

    async def _recover_state_from_db(self, game_id: int) -> dict | None:
        """
        Restores the game state hash in Redis from the games table (disconnects, draw and rematch offers are not
        saved). For a running game it sets active_games, the check deadline and the players' links anew; for
        a finished one -- the hash lifetime. Returns the state or None if the game is not in the DB or a failure occurred.
        """
        try:
            async with AsyncSessionLocal() as db:
                db_game = await db.get(Game, game_id)
                if not db_game:
                    return None

                now_ms = int(time.time() * 1000)
                turn_str = "white" if db_game.turn in ("w", "white") else "black"
                white_time = db_game.white_time_ms if db_game.white_time_ms is not None else db_game.base_time_ms
                black_time = db_game.black_time_ms if db_game.black_time_ms is not None else db_game.base_time_ms
                last_move = db_game.last_move_at if db_game.last_move_at is not None else now_ms

                status_map = {
                    GameStatus.IN_PROGRESS: "in_progress",
                    GameStatus.COMPLETED: "completed",
                    GameStatus.ABORTED: "aborted",
                    GameStatus.PENDING: "pending",
                }
                status_str = status_map.get(db_game.status, "completed")

                state = {
                    "white_id": str(db_game.white_player_id),
                    "black_id": str(db_game.black_player_id),
                    "is_rated": "1" if db_game.is_rated else "0",
                    "board_fen": db_game.board_fen or STARTING_FEN,
                    "pgn": db_game.pgn or (pgn_header(db_game.initial_fen) if db_game.initial_fen else ""),
                    "state_version": str(db_game.state_version or 0),
                    "white_time_ms": str(white_time),
                    "black_time_ms": str(black_time),
                    "base_time_ms": str(db_game.base_time_ms),
                    "increment_ms": str(db_game.increment_ms),
                    "last_move_at": str(last_move),
                    "turn": turn_str,
                    "status": status_str,
                    "white_disconnected": "false",
                    "black_disconnected": "false",
                    "white_disconnect_started_at": "0",
                    "black_disconnect_started_at": "0",
                    "hourglass": "1" if db_game.hourglass else "0",
                }
                if status_str == "in_progress":
                    # An arena game: without these fields berserk would get the increment again after restoration.
                    from src.services import arena as arena_service
                    state.update(await arena_service.game_state_fields(db, game_id))
                await self.redis.hset(self._get_key(game_id), mapping=state)
                if status_str != "in_progress":
                    # A finished game is restored for the rematch and post-game chat --
                    # without a lifetime such hashes would accumulate in Redis indefinitely.
                    await self.redis.expire(self._get_key(game_id), FINISHED_STATE_TTL_S)
                if status_str == "in_progress":
                    await self.redis.sadd("active_games", str(game_id))
                    await self.redis.zadd(GAME_DEADLINES_KEY, {str(game_id): next_timeout_deadline_ms(state)})
                    await self.redis.set(f"user:{db_game.white_player_id}:current_game", str(game_id))
                    await self.redis.set(f"user:{db_game.black_player_id}:current_game", str(game_id))
                return await self.get_game_state(game_id)
        except Exception as e:
            logger.error("Failed to recover game %s from DB: %s", game_id, e)
            return None

    async def update_game_state(self, game_id: int, updates: dict):
        """Writes fields into the game hash without checking the status; for a running game update_if_in_progress is better."""
        str_updates = {k: str(v) for k, v in updates.items()}
        await self.redis.hset(self._get_key(game_id), mapping=str_updates)

    async def clear_game_state(self, game_id: int):
        """
        Removes the game from Redis after the result is written: the state, the command and move logs, the "player in game"
        marks, the clock
        check deadline.
        """
        state = await self.redis.hgetall(self._get_key(game_id))
        if state:
            await self.redis.delete(f"user:{state.get('white_id')}:current_game")
            await self.redis.delete(f"user:{state.get('black_id')}:current_game")
        await self.redis.delete(self._get_key(game_id))
        await self.redis.delete(f"game:{game_id}:commands")
        await self.redis.delete(f"game:{game_id}:moves")
        await self.redis.srem("active_games", str(game_id))
        await self.redis.zrem(GAME_DEADLINES_KEY, str(game_id))

    async def save_move_telemetry(self, game_id: int, move_data: dict):
        """Appends move telemetry to the game:{id}:moves log; it reaches the moves table in finish_game."""
        key = f"game:{game_id}:moves"
        await self.redis.rpush(key, json.dumps(move_data))

    async def read_all_moves(self, game_id: int) -> list[dict]:
        """
        Game move telemetry. Does not delete it: deletion happens after the result is committed to the DB
        (clear_game_state), otherwise on a commit failure the retry would be left without moves.
        """
        moves_raw = await self.redis.lrange(f"game:{game_id}:moves", 0, -1)
        return [json.loads(m) for m in moves_raw]

    async def _mark_finished_in_db(self, game_id: int) -> None:
        """The game result is written to the DB -- reconciliation no longer needs to complete it."""
        await self.redis.zrem(PENDING_FINISH_KEY, str(game_id))

    async def process_atomic_move(
            self,
            game_id: int,
            user_id: int,
            command_id: str,
            move_str: str,
            expected_version: int | None = None,
            client_elapsed_ms: int | None = None,
    ) -> dict:
        """
        Atomically (WATCH/MULTI) applies a player's move: command_id repeat, version, move order, legality,
        time deduction and the lag quota, the position change, removal of the opponent's draw offer.
        Returns a dict with status: "success" (move accepted), "game_over" (mate, draw or flag, the game is already
        closed in Redis but not in the DB), "ignored" (a command repeat) or "error" with a code in reason; on a player refusal
        the current position is put into the response.
        client_elapsed_ms -- the move thinking time by the client's clock: the difference from the server clock is lag, which
        is returned to the player within the quota (lag_credit_ms). None -- no refund.
        """
        game_key = self._get_key(game_id)
        cmd_key = f"game:{game_id}:commands"

        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(game_key, cmd_key)

                    is_processed = await pipe.sismember(cmd_key, command_id)
                    if is_processed:
                        await pipe.unwatch()
                        return {"status": "ignored", "reason": "already_processed"}

                    state = await pipe.hgetall(game_key)
                    if not state or state.get("status") != "in_progress":
                        await pipe.unwatch()
                        return {"status": "error", "reason": "game_inactive"}

                    current_version = int(state.get("state_version", 0))
                    if expected_version is not None and int(expected_version) != current_version:
                        await pipe.unwatch()
                        return _move_rejection("version_mismatch", state)

                    turn = state.get("turn", "white")
                    white_id = int(state["white_id"])
                    black_id = int(state["black_id"])

                    is_white_turn = turn in ("white", "w")
                    expected_player_id = white_id if is_white_turn else black_id

                    if user_id != expected_player_id:
                        await pipe.unwatch()
                        if user_id not in (white_id, black_id):
                            # We do not return the position in the response to outsiders (spectators).
                            return {"status": "error", "reason": "not_your_turn"}
                        return _move_rejection("not_your_turn", state)

                    now_ms = int(time.time() * 1000)
                    last_move_at = int(state["last_move_at"])
                    elapsed_ms = max(0, now_ms - last_move_at)

                    mover = "white" if is_white_turn else "black"
                    # Berserk (33.3) plays without an increment.
                    increment = 0 if is_berserk(state, mover) else int(state["increment_ms"])
                    white_time = int(state["white_time_ms"])
                    black_time = int(state["black_time_ms"])

                    lag_credit = lag_credit_ms(state, mover, elapsed_ms, client_elapsed_ms)
                    lag_used = int(state.get(f"{mover}_lag_ms") or 0) + lag_credit
                    remaining_after_move = (white_time if is_white_turn else black_time) - elapsed_ms + lag_credit
                    if remaining_after_move <= 0:
                        # The flag fell before the move: finish the game in the same transaction so that
                        # check_timeouts_loop or another handler does not finish it again.
                        flag_result, flag_termination = flag_outcome(
                            state.get("board_fen"), "white" if is_white_turn else "black",
                        )
                        # With an "hourglass" clock all of the fallen side's time has already passed to the opponent.
                        gain = (white_time if is_white_turn else black_time) if is_hourglass(state) else 0
                        final_white = 0 if is_white_turn else white_time + gain
                        final_black = black_time + gain if is_white_turn else 0
                        pipe.multi()
                        pipe.hset(game_key, mapping={
                            "status": "completed",
                            "result": flag_result,
                            "termination": flag_termination,
                            "white_time_ms": str(final_white),
                            "black_time_ms": str(final_black),
                            "ended_at": str(now_ms),
                        })
                        pipe.zadd(PENDING_FINISH_KEY, {str(game_id): now_ms})
                        pipe.zrem(GAME_DEADLINES_KEY, str(game_id))
                        pipe.sadd(cmd_key, command_id)
                        await pipe.execute()
                        return {
                            "status": "game_over",
                            "result": flag_result,
                            "termination": flag_termination,
                            "white_id": white_id,
                            "black_id": black_id,
                            "white_time_ms": final_white,
                            "black_time_ms": final_black,
                            "elapsed_ms": elapsed_ms,
                        }

                    mover_time, waiting_time = clocks_after_move(
                        white_time if is_white_turn else black_time, black_time if is_white_turn else white_time,
                        elapsed_ms - lag_credit, increment, is_hourglass(state),
                    )
                    new_white_time, new_black_time = (
                        (mover_time, waiting_time) if is_white_turn else (waiting_time, mover_time)
                    )

                    current_fen = state.get("board_fen") or STARTING_FEN
                    current_pgn = state.get("pgn") or ""

                    is_valid, move_data = engine.process_move(current_fen, move_str, current_pgn)
                    if not is_valid or not move_data:
                        await pipe.unwatch()
                        return _move_rejection("illegal_move", state)

                    new_version = current_version + 1
                    new_turn = "black" if is_white_turn else "white"

                    pipe.multi()

                    if move_data["is_game_over"]:
                        updates = {
                            "status": "completed",
                            "result": move_data["result"],
                            "termination": move_data["termination"],
                            "state_version": str(new_version),
                            "board_fen": move_data["new_fen"],
                            "pgn": move_data["new_pgn"],
                            "last_move_at": str(now_ms),
                            "white_time_ms": str(new_white_time),
                            "black_time_ms": str(new_black_time),
                            "ended_at": str(now_ms),
                            f"{mover}_lag_ms": str(lag_used),
                        }
                        pipe.hset(game_key, mapping=updates)
                        pipe.zadd(PENDING_FINISH_KEY, {str(game_id): now_ms})
                        pipe.zrem(GAME_DEADLINES_KEY, str(game_id))
                        pipe.sadd(cmd_key, command_id)
                        await pipe.execute()
                        return {
                            "status": "game_over",
                            "result": move_data["result"],
                            "termination": move_data["termination"],
                            "move_data": move_data,
                            "state_version": new_version,
                            "white_time_ms": new_white_time,
                            "black_time_ms": new_black_time,
                            "white_id": white_id,
                            "black_id": black_id,
                            "elapsed_ms": elapsed_ms,
                            "now_ms": now_ms,
                        }

                    updates = {
                        "state_version": str(new_version),
                        "turn": new_turn,
                        "board_fen": move_data["new_fen"],
                        "pgn": move_data["new_pgn"],
                        "last_move_at": str(now_ms),
                        "white_time_ms": str(new_white_time),
                        "black_time_ms": str(new_black_time),
                        f"{mover}_lag_ms": str(lag_used),
                    }
                    # A draw offer stays in force until the opponent answers with a move (FIDE 9.1.2):
                    # the move of the one who was offered declines it; the offerer's own move does not.
                    draw_offer = str(state.get("draw_offer") or "")
                    if draw_offer and draw_offer != str(user_id):
                        updates["draw_offer"] = ""

                    pipe.hset(game_key, mapping=updates)
                    pipe.zadd(GAME_DEADLINES_KEY, {str(game_id): next_timeout_deadline_ms({**state, **updates})})
                    pipe.sadd(cmd_key, command_id)
                    pipe.expire(cmd_key, 86400)

                    await pipe.execute()

                    return {
                        "status": "success",
                        "move_data": move_data,
                        "state_version": new_version,
                        "turn": new_turn,
                        "white_time_ms": new_white_time,
                        "black_time_ms": new_black_time,
                        "white_id": white_id,
                        "black_id": black_id,
                        "elapsed_ms": elapsed_ms,
                        "lag_credit_ms": lag_credit,
                        "now_ms": now_ms,
                    }

                except WatchError:
                    continue

    async def apply_berserk(self, game_id: int, user_id: int) -> dict:
        """
        "Berserk" (33.3): before their first move a player of an arena game keeps half the base time and
        gives up the increment (for a win the arena gives an extra point -- src/services/arena.py). Atomic (WATCH/MULTI):
        a move made at the same moment either precedes berserk (then a refusal) or sees the new clocks already.

        Returns {"status": "ok", "color", "state"} with the fresh state or {"status": "error", "code"};
        a repeated berserk -- {"status": "ignored"}.
        """
        game_key = self._get_key(game_id)
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(game_key)
                    raw = await pipe.hgetall(game_key)
                    if not raw or raw.get("status") != "in_progress":
                        await pipe.unwatch()
                        return {"status": "error", "code": "game_not_in_progress"}
                    state = _coerce_state(raw)
                    if user_id not in (state["white_id"], state["black_id"]) or state.get("berserk_allowed") != "1":
                        await pipe.unwatch()
                        return {"status": "error", "code": "berserk_unavailable"}
                    color = "white" if user_id == state["white_id"] else "black"
                    if is_berserk(state, color):
                        await pipe.unwatch()
                        return {"status": "ignored"}
                    now_ms = int(time.time() * 1000)
                    half = int(state["base_time_ms"]) // 2
                    updates = {f"{color}_time_ms": str(half), f"{color}_berserk": "1"}
                    fresh = {**state, f"{color}_time_ms": half, f"{color}_berserk": "1"}
                    # White has not moved yet at version 0, Black at version no more than 1.
                    moved = int(state.get("state_version", 0)) > (0 if color == "white" else 1)
                    if moved or live_clock_ms(fresh, color, now_ms) <= 0:
                        await pipe.unwatch()
                        return {"status": "error", "code": "berserk_too_late"}
                    pipe.multi()
                    pipe.hset(game_key, mapping=updates)
                    pipe.zadd(GAME_DEADLINES_KEY, {str(game_id): next_timeout_deadline_ms(fresh)})
                    await pipe.execute()
                    return {"status": "ok", "color": color, "state": fresh}
                except WatchError:
                    continue

    async def sync_authoritative_state_to_db(self, db, game_id: int, res: dict):
        """
        Copies the state after a move into the games table (position, move record, version, move order, clocks): from it
        the game is restored if it disappears from Redis.
        """
        db_game = await db.get(Game, game_id)
        if not db_game:
            return

        move_data = res.get("move_data")
        if move_data:
            db_game.board_fen = move_data["new_fen"]
            db_game.pgn = move_data["new_pgn"]

        if "state_version" in res:
            db_game.state_version = res["state_version"]
        if "turn" in res:
            db_game.turn = "w" if res["turn"] == "white" else "b"
        if "white_time_ms" in res:
            db_game.white_time_ms = res["white_time_ms"]
        if "black_time_ms" in res:
            db_game.black_time_ms = res["black_time_ms"]
        if "now_ms" in res:
            db_game.last_move_at = res["now_ms"]

        await db.commit()

    async def finish_game(self, db, game_id: int, result: str, termination: str = "unknown",
                          final_pgn: str | None = None) -> dict:
        """
        Records the game result in the DB: ratings by time-control category (if the game is rated), moves with telemetry,
        PGN, ECO, product events, arena points, the anti-cheat assessment, Redis cleanup and queuing the analysis in the
        background.
        Returns the changes and the players' new ratings (for an already recorded game -- only the changes).

        Call only after a successful claim_game_end (or from the game_over branch of process_atomic_move,
        which captures completion in its own transaction). Additionally, in case of a race between
        processes or loss of the Redis state, the game and player rows are locked
        (SELECT ... FOR UPDATE) and re-read from the DB bypassing the session's identity map, so
        a repeated call will not credit the rating a second time.
        """
        db_game = await db.get(Game, game_id, with_for_update=True, populate_existing=True)
        if not db_game:
            return {}

        if db_game.status in (GameStatus.COMPLETED, GameStatus.ABORTED):
            await db.commit()  # release the lock
            # The result is already recorded (a repeated call or reconciliation after a failure between the commit and
            # the Redis cleanup) -- it is enough to remove the leftover state.
            await self._mark_finished_in_db(game_id)
            await self.clear_game_state(game_id)
            return {
                "white_delta": db_game.white_rating_delta or 0,
                "black_delta": db_game.black_rating_delta or 0
            }

        # We lock the players in a fixed order (by id) so that games of one player finishing in parallel
        # do not lose a rating update and do not deadlock.
        locked_users: dict[int, User] = {}
        for uid in sorted({db_game.white_player_id, db_game.black_player_id}):
            locked_users[uid] = await db.get(User, uid, with_for_update=True, populate_existing=True)
        white_user = locked_users[db_game.white_player_id]
        black_user = locked_users[db_game.black_player_id]

        # The rating and the number of games played -- separately per time-control category of this
        # game (bullet/blitz/rapid/classical), not one overall count.
        category = classify_time_control(db_game.base_time_ms, db_game.increment_ms)
        white_initial = white_user.rating_for(category)
        black_initial = black_user.rating_for(category)
        delta_w = delta_b = 0
        new_w = white_initial
        new_b = black_initial

        if db_game.is_rated:
            white_games_count = white_user.games_played_for(category)
            black_games_count = black_user.games_played_for(category)

            new_w, delta_w, new_b, delta_b = elo_calculator.calculate_new_ratings(
                white_initial,
                black_initial,
                result,
                white_games=white_games_count,
                black_games=black_games_count,
            )
            setattr(white_user, f"{category}_rating", new_w)
            setattr(black_user, f"{category}_rating", new_b)
            setattr(white_user, f"{category}_games_played", white_games_count + 1)
            setattr(black_user, f"{category}_games_played", black_games_count + 1)

        db_game.result = result
        db_game.termination = termination

        if result == "1-0":
            db_game.winner_id = white_user.id
        elif result == "0-1":
            db_game.winner_id = black_user.id

        db_game.white_initial_rating = white_initial
        db_game.black_initial_rating = black_initial
        db_game.white_rating_delta = delta_w
        db_game.black_rating_delta = delta_b

        state = await self.redis.hgetall(self._get_key(game_id))
        if state:
            if state.get("state_version"):
                db_game.state_version = int(state["state_version"])
            if state.get("board_fen"):
                db_game.board_fen = state["board_fen"]
            if state.get("white_time_ms"):
                db_game.white_time_ms = int(state["white_time_ms"])
            if state.get("black_time_ms"):
                db_game.black_time_ms = int(state["black_time_ms"])
            if not final_pgn:
                final_pgn = state.get("pgn")

        today_str = datetime.datetime.now(datetime.UTC).strftime("%Y.%m.%d")
        db_game.status = GameStatus.COMPLETED
        db_game.finished_at = func.now()
        db_game.pgn_date = today_str
        db_game.site = "Regence"

        moves_telemetry = await self.read_all_moves(game_id)
        if moves_telemetry:
            db_moves = [Move(game_id=game_id, **m) for m in moves_telemetry]
            db.add_all(db_moves)

            uci_seq = [m.get("notation", "") for m in moves_telemetry if m.get("notation")]
            eco_code = openings.eco_code(uci_seq)
            db_game.eco = eco_code

            pgn_game = chess.pgn.Game()
            pgn_game.headers["Event"] = "Regence Rated Game" if db_game.is_rated else "Regence Casual Game"
            pgn_game.headers["Site"] = "Regence"
            pgn_game.headers["Date"] = today_str
            pgn_game.headers["White"] = white_user.username
            pgn_game.headers["Black"] = black_user.username
            pgn_game.headers["WhiteElo"] = str(white_initial)
            pgn_game.headers["BlackElo"] = str(black_initial)
            pgn_game.headers["Result"] = result
            pgn_game.headers["ECO"] = eco_code
            pgn_game.headers["TimeControl"] = f"{db_game.base_time_ms // 1000}+{db_game.increment_ms // 1000}"
            pgn_game.headers["Termination"] = termination

            node: chess.pgn.GameNode = pgn_game
            if db_game.initial_fen:
                pgn_game.setup(board_from_fen(db_game.initial_fen))  # for a 960 game -- also the Variant header
            board_for_pgn = board_from_fen(db_game.initial_fen) if db_game.initial_fen else chess.Board()
            for m in moves_telemetry:
                try:
                    move_obj = chess.Move.from_uci(m["notation"])
                    if move_obj in board_for_pgn.legal_moves:
                        board_for_pgn.push(move_obj)
                        node = node.add_variation(move_obj)
                    else:
                        break
                except ValueError:
                    break
            db_game.pgn = str(pgn_game)
        elif final_pgn:
            db_game.pgn = final_pgn
            from src.db.seed import extract_pgn_metadata
            meta = extract_pgn_metadata(final_pgn, fallback_result=result)
            if meta["pgn_date"]:
                db_game.pgn_date = meta["pgn_date"]
            if meta["site"]:
                db_game.site = meta["site"]
            if meta["eco"]:
                db_game.eco = meta["eco"]

        for player in (white_user, black_user):
            if player is not None and not player.is_bot:
                await product_metrics.record_event(db, player.id, product_metrics.GAME_FINISHED)
        # An arena game (17.2): points and streaks of participants -- in the same transaction as the game result.
        from src.services import arena as arena_service
        await arena_service.on_game_finished(db, game_id, result, termination=termination,
                                             plies=len(moves_telemetry) if moves_telemetry else 0)
        await db.commit()
        await self._mark_finished_in_db(game_id)
        GAMES_FINISHED.labels(bounded_label(termination)).inc()

        if db_game.is_rated:
            try:
                await evaluate_game_telemetry(db, game_id)
            except Exception as ac_err:
                logger.error("Telemetry anti-cheat evaluation failed for game %s: %s", game_id, ac_err)

        await self.clear_game_state(game_id)

        # A Swiss between humans (17.2): the next round -- when the players are already free.
        try:
            await arena_service.advance_after_game(db, game_id)
        except Exception as arena_err:
            logger.error("Arena round advance failed after game %s: %s", game_id, arena_err)

        # We do not wait for the broker: publishing runs in a thread, the game result is broadcast at once.
        schedule_game_analysis_in_background(game_id)

        return {
            "white_delta": delta_w,
            "black_delta": delta_b,
            "white_new_rating": new_w,
            "black_new_rating": new_b
        }

    async def handle_player_disconnect(self, user_id: int, manager):
        """
        A player disconnected during the game: a mark and the disconnect moment are set in the state, the opponent is told
        how long remains to wait before the disconnected player loses. The clocks keep running.
        manager -- the connection manager (connection_manager) through which the message to the opponent goes.
        """
        game_id_str = await self.redis.get(f"user:{user_id}:current_game")
        if not game_id_str:
            return
        game_id = int(game_id_str)
        state = await self.get_game_state(game_id)
        if not state or state["status"] != "in_progress":
            return

        white_id, black_id = int(state["white_id"]), int(state["black_id"])
        color = "white" if user_id == white_id else "black"
        opponent_id = black_id if color == "white" else white_id

        now_ms = int(time.time() * 1000)
        fresh = await self._update_if_in_progress(game_id, {
            f"{color}_disconnected": "true",
            f"{color}_disconnect_started_at": str(now_ms),
        })
        if fresh is None:
            return

        await manager.send_personal_message(
            {
                "event": "opponent_disconnected",
                "game_id": game_id,
                "max_wait_ms": abandon_wait_ms(fresh, color, now_ms),
            },
            opponent_id,
        )

    async def handle_player_reconnect(self, user_id: int, manager):
        """
        A player returned to the game: the disconnect mark is cleared, the opponent gets a notification. The clocks are not
        touched -- they
        ran all this time.
        """
        game_id_str = await self.redis.get(f"user:{user_id}:current_game")
        if not game_id_str:
            return
        game_id = int(game_id_str)
        state = await self.get_game_state(game_id)
        if not state or state["status"] != "in_progress":
            return

        white_id, black_id = int(state["white_id"]), int(state["black_id"])
        color = "white" if user_id == white_id else "black"
        opponent_id = black_id if color == "white" else white_id

        if state.get(f"{color}_disconnected") == "true":
            # We do not touch the clocks: they have run from last_move_at anyway while the player was offline.
            # Previously last_move_at was shifted here, and if it was the opponent's move, their clock
            # effectively stood still for the whole time of the disconnect.
            fresh = await self._update_if_in_progress(game_id, {
                f"{color}_disconnected": "false",
                f"{color}_disconnect_started_at": "0",
            })
            if fresh is not None:
                await manager.send_personal_message(
                    {"event": "opponent_reconnected", "game_id": game_id}, opponent_id,
                )

    async def update_if_in_progress(self, game_id: int, updates: dict) -> dict | None:
        """Updates the fields of a running game; None if it is already finished (see _update_if_in_progress)."""
        return await self._update_if_in_progress(game_id, updates)

    async def _update_if_in_progress(self, game_id: int, updates: dict) -> dict | None:
        """
        Atomically (WATCH/MULTI) updates the game fields only while it is in_progress.
        A plain hset after clear_game_state would recreate a "stub" of the hash without white_id and so on.
        It also recalculates the deadline in game_deadlines (disconnect marks, berserk and so on change).
        Returns the state before the update or None if the game is no longer running.
        """
        game_key = self._get_key(game_id)
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(game_key)
                    raw = await pipe.hgetall(game_key)
                    if not raw or raw.get("status") != "in_progress":
                        await pipe.unwatch()
                        return None
                    str_updates = {k: str(v) for k, v in updates.items()}
                    pipe.multi()
                    pipe.hset(game_key, mapping=str_updates)
                    pipe.zadd(GAME_DEADLINES_KEY, {str(game_id): next_timeout_deadline_ms({**raw, **str_updates})})
                    await pipe.execute()
                    return _coerce_state(raw)
                except WatchError:
                    continue

    async def _hold_timeouts_leadership(self) -> bool:
        """
        The timeout loop is run by only one worker (the leader). Leadership is a key with a TTL; the leader
        renews it every iteration, and when the leader crashes the key expires and another takes it.
        Even if for a moment there are two leaders, there will be no double completion of a game:
        it is protected by claim_game_end. If Redis is unavailable, returns True: the pass is run anyway.
        """
        try:
            if await self.redis.set(TIMEOUTS_LEADER_KEY, WORKER_ID, nx=True, px=TIMEOUTS_LEADER_TTL_MS):
                return True
            if await self.redis.get(TIMEOUTS_LEADER_KEY) == WORKER_ID:
                await self.redis.pexpire(TIMEOUTS_LEADER_KEY, TIMEOUTS_LEADER_TTL_MS)
                return True
            return False
        except Exception as exc:
            logger.warning("Timeouts leadership check failed, running loop anyway: %s", exc)
            return True

    async def check_timeouts_loop(self, manager):
        """
        An endless loop, twice a second: if this process is the leader, it checks games whose deadline has come (flag,
        no-show, abandoned game) and periodically reconciles Redis with the database.
        """
        while True:
            try:
                if await self._hold_timeouts_leadership():
                    await self.check_timeouts_once(manager)
                    await self._maybe_reconcile(manager)
            except Exception:
                # Only failures of the pass itself get here (Redis unavailable and so on);
                # errors of individual games are isolated in check_timeouts_once.
                logger.exception("Error in check_timeouts_loop")

            await asyncio.sleep(0.5)

    async def check_timeouts_once(self, manager, now_ms: int | None = None) -> None:
        """
        One pass: flags, abandoned games, first-move no-shows -- but not over all active
        games, only those whose deadline (GAME_DEADLINES_KEY) has already come. With hundreds of
        simultaneous games most are not close to a flag, and a full iteration over active_games
        every 0.5 s does not scale; ZRANGEBYSCORE fetches exactly those whose time has come.

        Each game is processed in its own try: previously an exception on one "broken"
        game (a damaged state, a DB failure in finish_game) aborted the whole pass, and on every
        tick everything repeated -- flags and aborts stopped working in all games at once.
        A game that fails over and over is postponed with a growing pause, but not dropped:
        on a temporary DB failure otherwise all running games would be lost.
        """
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        due_game_ids = await self.redis.zrangebyscore(GAME_DEADLINES_KEY, 0, now_ms)

        # Failure counters of games that are no longer active (finished another way) are not needed.
        # active_games, not due_game_ids: a game with a deadline that has not come yet must not
        # lose its accumulated backoff just because it was not examined on this tick.
        for stale_id in list(self._timeout_failures):
            if not await self.redis.sismember("active_games", str(stale_id)):
                del self._timeout_failures[stale_id]

        for game_id_str in due_game_ids:
            try:
                game_id = int(game_id_str)
            except (TypeError, ValueError):
                logger.error("Removing malformed id %r from %s", game_id_str, GAME_DEADLINES_KEY)
                await self.redis.zrem(GAME_DEADLINES_KEY, game_id_str)
                continue

            failure = self._timeout_failures.get(game_id)
            if failure and now_ms < failure[1]:
                continue  # the pause after repeated failures has not passed yet

            try:
                await self._check_game_timeout(game_id, game_id_str, manager, now_ms)
            except Exception:
                self._record_timeout_failure(game_id, now_ms)
            else:
                self._timeout_failures.pop(game_id, None)

    async def _maybe_reconcile(self, manager) -> None:
        """Runs the Redis/DB reconciliation no more often than once per RECONCILE_INTERVAL_MS."""
        now_ms = int(time.time() * 1000)
        if now_ms - self._last_reconcile_ms < RECONCILE_INTERVAL_MS:
            return
        # We mark the time before the pass: a failed reconciliation must not repeat every half second.
        self._last_reconcile_ms = now_ms
        await self.reconcile_unfinished_games(now_ms, manager=manager)

    def _record_timeout_failure(self, game_id: int, now_ms: int) -> None:
        """Counts a game check failure and postpones the next attempt (exponentially, no longer than TIMEOUT_RETRY_MAX_MS)."""
        TIMEOUT_CHECK_FAILURES.inc()
        count = self._timeout_failures.get(game_id, (0, 0))[0] + 1
        delay_ms = min(TIMEOUT_RETRY_MAX_MS, TIMEOUT_RETRY_BASE_MS * 2 ** (count - 1))
        self._timeout_failures[game_id] = (count, now_ms + delay_ms)
        # The full stack -- on the first failure and then occasionally, so as not to flood the log every half second.
        if count == 1 or count % TIMEOUT_FAILURE_LOG_EVERY == 0:
            logger.exception(
                "Timeout check failed for game %s (%s in a row), next attempt in %s ms",
                game_id, count, delay_ms,
            )

    async def _check_game_timeout(self, game_id: int, game_id_str: str, manager, now_ms: int) -> None:
        """
        Check of one game whose deadline has come: a first-move no-show (30 s) -- abort, otherwise a flag or an abandoned
        game by evaluate_clock_expiry -- capture, writing the result and broadcasting game_over to players and spectators.
        """
        state = await self.get_game_state(game_id)
        if not state or state["status"] != "in_progress":
            await self.redis.srem("active_games", game_id_str)
            await self.redis.zrem(GAME_DEADLINES_KEY, game_id_str)
            return

        if int(state.get("state_version", 0)) < 2 and now_ms - int(state.get("last_move_at", now_ms)) >= 30000:
            async with AsyncSessionLocal() as db:
                await self.check_first_move_abort_timeout(db, game_id, manager=manager, timeout_ms=30000)
            return

        white_id, black_id = int(state["white_id"]), int(state["black_id"])
        decision = evaluate_clock_expiry(state, now_ms)
        if not decision:
            # The deadline in GAME_DEADLINES_KEY has come, but on the fresh state the outcome did not fire
            # (for example, a move and our tick crossed) -- we move it to a future moment,
            # otherwise this game would land in ZRANGEBYSCORE on every tick for nothing.
            await self.redis.zadd(GAME_DEADLINES_KEY, {game_id_str: next_timeout_deadline_ms(state)})
            return

        game_result, winner_id, reason = decision

        # The decision is rechecked on the fresh state inside the transaction: the player may
        # have managed to move, reconnect or resign while we were reading the state.
        claimed = await self.claim_game_end(
            game_id, game_result, reason,
            guard=lambda fresh, expected=decision: evaluate_clock_expiry(fresh, now_ms) == expected,
        )
        if not claimed:
            return

        logger.info("Game %s ended. Result: %s, Reason: %s", game_id, game_result, reason)

        async with AsyncSessionLocal() as db:
            rating_updates = await self.finish_game(db, game_id, game_result, termination=reason)

        game_over_payload = {
            "event": "game_over",
            "game_id": game_id,
            "reason": reason,
            "winner_id": winner_id,
            "result": game_result,
        }
        game_over_payload.update(rating_updates)

        await manager.send_personal_message(game_over_payload, white_id)
        await manager.send_personal_message(game_over_payload, black_id)
        if hasattr(manager, "broadcast_to_spectators"):
            await manager.broadcast_to_spectators(game_id, game_over_payload)

    async def abort_game(self, db, game_id: int, guard=None) -> dict:
        """
        Aborts a game on move 1 (up to 2 plies) without a rating change.
        guard(state) -> bool -- an additional condition atomically rechecked on capture.
        Returns {"status": "aborted", ...} with the players' ids and ratings or {"status": "error", "code"}.
        """
        state = await self.get_game_state(game_id)
        if not state or state.get("status") != "in_progress":
            return {"status": "error", "reason": "Game is not in progress", "code": "game_not_in_progress"}

        state_version = int(state.get("state_version", 0))
        if state_version >= 2:
            return {"status": "error", "reason": "Cannot abort game after move 1", "code": "abort_too_late"}

        white_id = int(state["white_id"])
        black_id = int(state["black_id"])

        def _abort_allowed(fresh: dict) -> bool:
            if int(fresh.get("state_version", 0)) >= 2:
                return False
            return guard(fresh) if guard is not None else True

        claimed = await self.claim_game_end(
            game_id, "*", "aborted", status="aborted", guard=_abort_allowed,
        )
        if not claimed:
            return {"status": "error", "reason": "Game is not in progress", "code": "game_not_in_progress"}

        await self.redis.srem("active_games", str(game_id))
        await self.redis.delete(f"user:{white_id}:current_game")
        await self.redis.delete(f"user:{black_id}:current_game")

        # An arena game (33.1): an abort before the first moves is a no-show by the one whose turn it was (voluntary abort in
        # an arena
        # is forbidden at entry, only the first-move timeout comes here).
        no_show = "white" if state_version == 0 else "black"
        w_rating, b_rating = await self._finalize_abort_in_db(db, game_id, white_id, black_id, no_show=no_show)

        return {
            "status": "aborted",
            "result": "*",
            "termination": "aborted",
            "white_id": white_id,
            "black_id": black_id,
            "white_delta": 0,
            "black_delta": 0,
            "white_new_rating": w_rating,
            "black_new_rating": b_rating,
        }

    async def _finalize_abort_in_db(self, db, game_id: int, white_id: int, black_id: int,
                                    no_show: str | None = None) -> tuple[int, int]:
        """
        Writes a game abort to the DB (idempotently). Called after a successful capture of
        completion with the status aborted -- from abort_game or from reconciliation after a failure.
        Returns the players' current ratings (an abort does not change them).
        """
        from datetime import datetime

        db_game = await db.get(Game, game_id, with_for_update=True, populate_existing=True)
        white_user = await db.get(User, white_id)
        black_user = await db.get(User, black_id)

        category = classify_time_control(db_game.base_time_ms, db_game.increment_ms) if db_game else "blitz"
        w_rating = white_user.rating_for(category) if white_user else 1200
        b_rating = black_user.rating_for(category) if black_user else 1200

        if db_game and db_game.status not in (GameStatus.COMPLETED, GameStatus.ABORTED):
            db_game.status = GameStatus.ABORTED
            db_game.result = "*"
            db_game.termination = "aborted"
            db_game.white_rating_delta = 0
            db_game.black_rating_delta = 0
            is_tz = getattr(Game.__table__.c.finished_at.type, "timezone", False)
            now_utc = datetime.now(UTC)
            db_game.finished_at = now_utc if is_tz else now_utc.replace(tzinfo=None)
            # Arena: a no-show -- a loss for the one who did not make the first move; the side is unknown (reconciliation) --
            # a game without points.
            from src.services import arena as arena_service
            await arena_service.on_game_aborted(db, game_id, no_show)
        await db.commit()  # and releases the lock if the game was already finished
        await self._mark_finished_in_db(game_id)
        return w_rating, b_rating

    # --- Redis and DB reconciliation ------------------------------------------------------------

    async def reconcile_unfinished_games(self, now_ms: int | None = None, manager=None) -> dict:
        """
        Completes games stuck between Redis and the DB.

        1. A game finished in Redis (claim_game_end / mate / flag on a move) but the result is not written
           to the DB: the process crashed or the DB was unavailable between these steps. Without reconciliation the game
           would stay in_progress in the DB forever with no rating, and the timeout loop no longer sees it.
           Such games lie in PENDING_FINISH_KEY; we take those that hang longer than RECONCILE_GRACE_MS
           (the regular handler would have finished long before) and run them through the
           idempotent finish_game / _finalize_abort_in_db.
        2. A game in_progress in the DB but its state is missing in Redis (Redis restarted without
           persistence) or it dropped out of active_games: we restore the state so that
           moves and clocks work. The state must be absent on two passes in a row --
           otherwise one could catch a just-created game before initialize_game.
        """
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        report: dict[str, list[int]] = {"finished": [], "aborted": [], "restored": [], "failed": []}

        overdue = await self.redis.zrangebyscore(PENDING_FINISH_KEY, 0, now_ms - RECONCILE_GRACE_MS)
        for game_id_str in overdue:
            game_id = int(game_id_str)
            try:
                outcome = await self._finish_pending_game(game_id, manager)
            except Exception:
                logger.exception("Reconciliation could not finish game %s; will retry", game_id)
                report["failed"].append(game_id)
                continue
            if outcome:
                report[outcome].append(game_id)

        async with AsyncSessionLocal() as db:
            rows = await db.execute(select(Game.id).where(Game.status == GameStatus.IN_PROGRESS))
            db_in_progress = [row[0] for row in rows.all()]

        active = {str(gid) for gid in await self.redis.smembers("active_games")}
        missing_now: set[int] = set()
        for game_id in db_in_progress:
            raw = await self.redis.hgetall(self._get_key(game_id))
            if not raw:
                if game_id in self._missing_state_seen:
                    if await self._recover_state_from_db(game_id):
                        report["restored"].append(game_id)
                else:
                    missing_now.add(game_id)
            elif raw.get("status") == "in_progress":
                if str(game_id) not in active:
                    await self.redis.sadd("active_games", str(game_id))
                    report["restored"].append(game_id)
                # The game is active but has no deadline (deploying this scheme onto already running
                # games, or the deadline was lost for another reason) -- without it the flag would
                # never fire for it until the next move/disconnect.
                if await self.redis.zscore(GAME_DEADLINES_KEY, str(game_id)) is None:
                    await self.redis.zadd(GAME_DEADLINES_KEY, {str(game_id): next_timeout_deadline_ms(raw)})
            elif raw.get("status") in ("completed", "aborted"):
                # Finished in Redis but absent from the registry of unfinished ones (for example, captured
                # before the registry appeared) -- we put it into the reconciliation queue.
                ended_at = int(raw.get("ended_at") or now_ms)
                await self.redis.zadd(PENDING_FINISH_KEY, {str(game_id): ended_at}, nx=True)
        self._missing_state_seen = missing_now

        if any(report.values()):
            logger.warning("Reconciliation report: %s", report)
        return report

    async def _finish_pending_game(self, game_id: int, manager=None) -> str | None:
        """
        Completes one game from the reconciliation registry by its result in Redis and notifies the players.
        Returns "finished", "aborted" or None if there is nothing to complete (the registry entry was removed).
        """
        raw = await self.redis.hgetall(self._get_key(game_id))
        status = raw.get("status") if raw else None

        if status == "completed":
            result = raw.get("result") or "1/2-1/2"
            termination = raw.get("termination") or "unknown"
            async with AsyncSessionLocal() as db:
                rating_updates = await self.finish_game(db, game_id, result, termination=termination)
            # The regular handler did not manage to broadcast the result -- we tell the players ourselves
            # (the client survives a repeated game_over, but without it the game "hangs" on the screen).
            await self._notify_reconciled(manager, raw, {
                "event": "game_over", "game_id": game_id, "reason": termination, "result": result,
                **rating_updates,
            })
            return "finished"
        if status == "aborted":
            white_id, black_id = int(raw["white_id"]), int(raw["black_id"])
            async with AsyncSessionLocal() as db:
                w_rating, b_rating = await self._finalize_abort_in_db(db, game_id, white_id, black_id)
            await self.clear_game_state(game_id)
            await self._notify_reconciled(manager, raw, {
                "event": "game_over", "game_id": game_id, "reason": "aborted", "result": "*",
                "white_delta": 0, "black_delta": 0,
                "white_new_rating": w_rating, "black_new_rating": b_rating,
            })
            return "aborted"

        # No state (Redis lost) or the game is in_progress again -- nothing to complete:
        # the result is unknown, the game will be restored if necessary by the second part of the reconciliation.
        await self.redis.zrem(PENDING_FINISH_KEY, str(game_id))
        return None

    @staticmethod
    async def _notify_reconciled(manager, raw_state: dict, payload: dict) -> None:
        """
        Broadcasts the result to the players and spectators of a completed game; without a connection manager does nothing.
        """
        if manager is None:
            return
        for key in ("white_id", "black_id"):
            await manager.send_personal_message(payload, int(raw_state[key]))
        if hasattr(manager, "broadcast_to_spectators"):
            await manager.broadcast_to_spectators(payload["game_id"], payload)

    async def check_first_move_abort_timeout(self, db, game_id: int, manager=None, timeout_ms: int = 30000) -> bool:
        """
        Checks whether timeout_ms (30 s by default) has expired for the first 2 plies of a game; if it has --
        aborts the game (abort_game) and broadcasts game_over. Returns True if the game was aborted.
        """
        state = await self.get_game_state(game_id)
        if not state or state.get("status") != "in_progress":
            return False

        if int(state.get("state_version", 0)) >= 2:
            return False

        now_ms = int(time.time() * 1000)
        last_move_at = int(state.get("last_move_at", now_ms))
        if now_ms - last_move_at < timeout_ms:
            return False

        def _still_idle(fresh: dict) -> bool:
            return int(time.time() * 1000) - int(fresh.get("last_move_at", 0)) >= timeout_ms

        res = await self.abort_game(db, game_id, guard=_still_idle)
        if res.get("status") == "aborted" and manager is not None:
            payload = {
                "event": "game_over",
                "game_id": game_id,
                "reason": "aborted",
                "result": "*",
                "white_delta": 0,
                "black_delta": 0,
                "white_new_rating": res["white_new_rating"],
                "black_new_rating": res["black_new_rating"],
            }
            await manager.send_personal_message(payload, res["white_id"])
            await manager.send_personal_message(payload, res["black_id"])
            if hasattr(manager, "broadcast_to_spectators"):
                await manager.broadcast_to_spectators(game_id, payload)
        return res.get("status") == "aborted"


state_manager = GameStateManager()
