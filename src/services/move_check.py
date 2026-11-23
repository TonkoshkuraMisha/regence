# --- FILE: src/services/move_check.py ---
"""
Game with the mentor (task 11.3): checking a player's move and the shared cache of position evaluations.

`check_move` evaluates the position before and after the move (best move, best reply of the opponent), computes the loss in
centipawns and the classification - by the same rules as the full game review - and assembles the mentor's explanation
(src/services/coach.py). Whether to warn the player is decided by the client by the player's level: the server provides facts.

Engine economy: a position evaluation is cached in Redis by FEN (without move counters) for CACHE_TTL_S. Advice on a position,
the move check and the repeated check after a take-back do not compute the same position twice. The bot's move does not
belong here on purpose: the bot looks for a move with the engine at limited strength (UCI_Elo) and with its own style - a
full-strength evaluation would change its play.

Without Stockfish the check is unavailable (`available: false`): the static analyser's evaluation is unreliable, and
one cannot warn about "blunders" on it. Advice and a hint without the engine work, but without the best move and evaluation.

Data in Redis: ``engine:eval:{depth}:{position}`` - the evaluation cache (JSON PositionEval, lives CACHE_TTL_S);
``coach:disputes`` - the queue of disputed evaluations (a list of JSON, the last DISPUTES_KEEP). The
module writes nothing to the database. Routes - src/api/analysis.py; all are covered by the fair-play rule (unavailable
during one's own game with a human).
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass

import chess
import chess.engine

from src.core.errors import DomainValueError
from src.db import redis as redis_module
from src.services.bots.base import resolve_stockfish_path
from src.services.coach import HINT_STEPS, advice_for_position, comment_for_move, hint_for_position
from src.services.engine_pool import EngineUnavailableError, get_engine_pool
from src.services.game_engine import board_from_start_fen

logger = logging.getLogger(__name__)

CACHE_TTL_S = 600  # a position evaluation lives in the cache for 10 minutes - enough for a game with the mentor
# Limit of one calculation: depth 12 or 0.15 s, whichever comes first. The depth is part of the cache key: when it changes
# the old evaluations are not used.
ENGINE_DEPTH = 12
ENGINE_TIME_S = 0.15
# Evaluations are clamped to +-20 pawns before computing the loss: otherwise the difference between "mate in 3" and "mate
# in 5" or between +25 and +40 would look like a gross error.
EVAL_CLAMP_CP = 2000
MATE_CP = 10_000  # conventional mate evaluation in centipawns (after clamping - the same +-2000)

# Tactics that the best move created and the played one did not: a "missed shot" (the mentor warns even on a
# small loss). Captures and an "ordinary best move" are not included.
MISSED_TACTIC_PREFIXES = (
    "coach.missed.",
    "coach.best.mate.", "coach.best.fork.", "coach.best.skewer.", "coach.best.pin_absolute.",
    "coach.best.discovered_attack.", "coach.best.discovered_check.", "coach.best.double_check.",
    "coach.best.mate_threat.", "coach.best.trapped.",
)


@dataclass(frozen=True)
class PositionEval:
    """Evaluation of the position from White's point of view (mate - +-MATE_CP), mate in N (the sign says whose), best move."""
    cp_white: int
    mate: int | None
    best_uci: str | None


def _cache_key(board: chess.Board) -> str:
    # The position without half-move and move counters: the same position is one key.
    return f"engine:eval:{ENGINE_DEPTH}:{' '.join(board.fen().split()[:4])}"


def engine_evaluate(board: chess.Board) -> PositionEval | None:
    """
    Stockfish evaluation (synchronous, via the pool). None - no engine. A finished game is evaluated without the engine: mate -
    +-MATE_CP against the side that was mated, stalemate and other draws - 0.
    """
    if board.is_checkmate():
        return PositionEval(-MATE_CP if board.turn == chess.WHITE else MATE_CP, 0, None)
    if board.is_game_over():
        return PositionEval(0, None, None)
    sf_path = resolve_stockfish_path()
    if not sf_path:
        return None
    with get_engine_pool(sf_path).acquire() as engine:
        info = engine.analyse(board, chess.engine.Limit(depth=ENGINE_DEPTH, time=ENGINE_TIME_S))
    if isinstance(info, list):
        info = info[0]
    score = info["score"].white()
    pv = info.get("pv")
    return PositionEval(
        cp_white=int(score.score(mate_score=MATE_CP) or 0),
        mate=score.mate(),
        best_uci=pv[0].uci() if pv else None,
    )


async def evaluate_cached(board: chess.Board) -> PositionEval | None:
    """
    Evaluation from the cache or from the engine (written to the cache). Redis unavailable - just compute. None - no engine
    or the pool is busy (EngineUnavailableError); a refusal is not written to the cache. The calculation runs in a separate
    thread.
    """
    key = _cache_key(board)
    try:
        raw = await redis_module.redis_client.get(key)
        if raw:
            return PositionEval(**json.loads(raw))
    except Exception as exc:  # the cache is an optimisation, not a condition of operation
        logger.warning("Evaluation cache unavailable: %s", exc)
    try:
        result = await asyncio.to_thread(engine_evaluate, board.copy(stack=False))
    except EngineUnavailableError as exc:
        logger.warning("Stockfish unavailable for move check: %s", exc)
        return None
    if result is not None:
        try:
            await redis_module.redis_client.set(key, json.dumps(asdict(result)), ex=CACHE_TTL_S)
        except Exception as exc:
            logger.warning("Evaluation cache unavailable: %s", exc)
    return result


def _clamped(cp_white: int) -> int:
    return max(-EVAL_CLAMP_CP, min(EVAL_CLAMP_CP, cp_white))


def _parse_position(fen: str) -> chess.Board:
    """Board from the request FEN; an impossible position or an already finished game - refusal with a code."""
    board = board_from_start_fen(fen)  # invalid_fen / invalid_position
    if board.is_game_over():
        raise DomainValueError("game_already_over")
    return board


async def check_move(fen: str, move_uci: str) -> dict:
    """
    Check of a player's move: loss (cp, from the point of view of the mover), classification, evaluations before and after,
    best move, best reply of the opponent, "missed shot" and the mentor's explanation.

    The loss is the difference of the clamped (EVAL_CLAMP_CP) evaluations before and after the move, not less than 0; a
    move that matches the engine's best move always gets a loss of 0. The classification is given by
    analysis_service.classify_move_by_cp_loss - the same as in the game review. A "missed shot" is when the explanation
    keys include one of MISSED_TACTIC_PREFIXES.
    """
    from src.services.analysis_service import classify_move_by_cp_loss  # without an import cycle

    board = _parse_position(fen)
    try:
        move = chess.Move.from_uci(move_uci)
    except ValueError:
        raise DomainValueError("illegal_move", move=move_uci) from None
    if move not in board.legal_moves:
        raise DomainValueError("illegal_move", move=move_uci)

    before = await evaluate_cached(board)
    after_board = board.copy(stack=False)
    after_board.push(move)
    after = await evaluate_cached(after_board)
    if before is None or after is None:
        return {"available": False}

    mover_sign = 1 if board.turn == chess.WHITE else -1
    cp_loss = max(0, mover_sign * (_clamped(before.cp_white) - _clamped(after.cp_white)))
    is_best = before.best_uci == move.uci()
    if is_best:
        cp_loss = 0
    classification, symbol = classify_move_by_cp_loss(cp_loss, is_best_move=is_best)
    coach = comment_for_move(board, move, before.best_uci, after.best_uci, classification)
    keys = [sentence["key"] for sentence in (coach or {}).get("comment", [])]
    return {
        "available": True,
        "cp_loss": cp_loss,
        "classification": classification,
        "symbol": symbol,
        # Evaluations are from the mover's point of view: the client does not need to remember whose move it was.
        "eval_before": mover_sign * _clamped(before.cp_white),
        "eval_after": mover_sign * _clamped(after.cp_white),
        "best_move_uci": before.best_uci,
        "reply_uci": after.best_uci,
        "missed_tactic": any(key.startswith(MISSED_TACTIC_PREFIXES) for key in keys),
        "coach": coach,
    }


async def advise(fen: str) -> dict:
    """
    Advice on a position (task 11.2) - with the evaluation from the same cache as the move check. The evaluation is from
    White's point of view. Without the engine the advice is assembled only by rules (coach.advice_for_position), the best
    move and evaluation are None.
    """
    board = _parse_position(fen)
    evaluation = await evaluate_cached(board)
    best = evaluation.best_uci if evaluation else None
    return {
        "fen": board.fen(),
        "best_move_uci": best,
        "eval_cp": _clamped(evaluation.cp_white) if evaluation else None,
        **advice_for_position(board, best),
    }


async def hint(fen: str, step: int) -> dict:
    """
    Hint by steps (task 11.4), steps - coach.HINT_STEPS (3). The best move is revealed only on
    the last step. Without the engine the best move is unknown, so the second step is at once declared the last
    (``final``), and the move stays None.
    """
    board = _parse_position(fen)
    evaluation = await evaluate_cached(board)
    best = evaluation.best_uci if evaluation else None
    payload = hint_for_position(board, best, step)
    final = step >= HINT_STEPS or (step == 2 and best is None)
    return {
        "fen": board.fen(),
        "step": HINT_STEPS if final else step,
        "final": final,
        "best_move_uci": best if final else None,
        **payload,
    }


DISPUTES_KEY = "coach:disputes"  # Redis list: new entries go first
DISPUTES_KEEP = 2000  # how many of the latest disputed evaluations are kept; older ones are dropped on every write


async def record_dispute(fen: str, move_uci: str, cp_loss: int | None, user_id: int | None) -> None:
    """
    "Disagree" with the mentor's warning: the position and move go into the queue of disputed evaluations (Redis, the last
    DISPUTES_KEEP). They are reviewed by deep analysis (scripts/dev/review_disputes.py), which is how errors in
    explanations and thresholds are found. The move is checked for legality so that the queue is not polluted. The record:
    position, move, loss shown by the client, player id (None - guest) and time. Redis unavailable - the record is lost
    without a refusal.
    """
    board = _parse_position(fen)
    try:
        move = chess.Move.from_uci(move_uci)
    except ValueError:
        raise DomainValueError("illegal_move", move=move_uci) from None
    if move not in board.legal_moves:
        raise DomainValueError("illegal_move", move=move_uci)
    entry = {"fen": board.fen(), "move": move.uci(), "cp_loss": cp_loss, "user_id": user_id, "at": int(time.time())}
    try:
        await redis_module.redis_client.lpush(DISPUTES_KEY, json.dumps(entry))
        await redis_module.redis_client.ltrim(DISPUTES_KEY, 0, DISPUTES_KEEP - 1)
    except Exception as exc:
        logger.warning("Disputed evaluations queue unavailable: %s", exc)
