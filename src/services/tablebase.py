# --- FILE: src/services/tablebase.py ---
"""
Endgame tablebases (task 14.4): the tablebase API at settings.TABLEBASE_URL - in development the open lichess server
(tablebase.lichess.ovh, up to 7 pieces), in production our own tablebase server with the same API (DEPLOY). Only the
position (FEN) goes to the third-party server - no player data; the client introduces itself with a generic name
(ATTRIBUTION, "External services"). The answer is cached in Redis: tablebases do not change.

The result is from the point of view of the side to move: category (win / draw / loss and their "cursed" variants by the
50 move rule), dtm and dtz in plies (lichess returns them that way), the best move is the first in the response list
(lichess sorts moves from best for the side to move).

Fallback path (task 1 of the 18.11 plan): the tablebase server did not answer within TIMEOUT_S or answered with an error -
the position is evaluated by Stockfish from the pool (engine_pool, depth FALLBACK_DEPTH), so that the trainer does not
fail. The answer is then marked source="engine": dtm and dtz are unknown (null), the category is by evaluation
(engine_category): mate or an advantage from ENGINE_WIN_CP - win / loss, no more than ENGINE_DRAW_CP - draw, between them -
maybe-win / maybe-loss (the client does not end the game in this corridor). The engine answer is not cached: the tablebases
may become available again. No engine either - the former refusal tablebase_unavailable.

Called by probe from POST /analysis/tablebase (src/api/analysis.py). The Redis key is "tablebase:<FEN>".
"""

import asyncio
import json
import logging

import chess
import chess.engine
import httpx

from src.core.config import settings
from src.core.errors import DomainError
from src.db import redis as redis_module
from src.services.bots.base import resolve_stockfish_path
from src.services.engine_pool import EngineUnavailableError, get_engine_pool

logger = logging.getLogger(__name__)

# How long to wait for the tablebase server: a player must not wait for an opponent's answer longer - after that the engine
# computes.
TIMEOUT_S = 1.5
# The tablebases do not cover more pieces on the board - refusal tablebase_too_many_pieces.
MAX_PIECES = 7
# Lifetime of a tablebase answer in Redis (30 days): tablebases do not change, the lifetime only keeps keys from piling up.
CACHE_TTL_S = 30 * 24 * 3600
# Generic client name for the third-party server (without player data).
USER_AGENT = "regence-endgame-trainer"
# Depth of the fallback calculation: in an endgame of up to seven pieces it is enough to find mate and tell a win from a draw.
FALLBACK_DEPTH = 18
# An engine evaluation (centipawns, for the side to move) of at least this is a win, of at most minus this is a loss.
ENGINE_WIN_CP = 400
# By absolute value no more than this - a draw. Between ENGINE_DRAW_CP and ENGINE_WIN_CP the verdict is unreliable -
# maybe-win / maybe-loss.
ENGINE_DRAW_CP = 50


async def _fetch(fen: str) -> dict:
    """
    A request to the tablebase API at settings.TABLEBASE_URL, the answer is JSON as in lichess. A network or status error -
    httpx.HTTPError (replaced in tests).
    """
    async with httpx.AsyncClient(timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT}) as client:
        response = await client.get(settings.TABLEBASE_URL, params={"fen": fen})
        response.raise_for_status()
        return response.json()


def engine_category(score: chess.engine.Score) -> str:
    """Category of a position for the side to move by the engine evaluation (thresholds - ENGINE_WIN_CP and ENGINE_DRAW_CP)."""
    mate = score.mate()
    if mate is not None:
        return "win" if mate > 0 else "loss"
    cp = score.score() or 0
    if cp >= ENGINE_WIN_CP:
        return "win"
    if cp <= -ENGINE_WIN_CP:
        return "loss"
    if abs(cp) <= ENGINE_DRAW_CP:
        return "draw"
    return "maybe-win" if cp > 0 else "maybe-loss"


def _engine_probe(board: chess.Board) -> dict:
    """Fallback engine answer in the probe format (synchronous - called in a thread). No binary - EngineUnavailableError."""
    path = resolve_stockfish_path()
    if not path:
        raise EngineUnavailableError("stockfish not found")
    with get_engine_pool(path).acquire() as engine:
        info = engine.analyse(board, chess.engine.Limit(depth=FALLBACK_DEPTH))
    if isinstance(info, list):
        info = info[0]
    pv = info.get("pv") or []
    best = None
    if pv and pv[0] in board.legal_moves:
        best = {"uci": pv[0].uci(), "san": board.san(pv[0]), "category": None, "dtm": None, "dtz": None}
    return {"category": engine_category(info["score"].relative), "dtm": None, "dtz": None, "best": best,
            "source": "engine"}


async def probe(board: chess.Board) -> dict:
    """
    {category, dtm, dtz, best: {uci, san, category, dtm, dtz} | None, source} for the side to move. source is
    "tablebase" (an exact tablebase answer) or "engine" (the tablebase server is unavailable, see the module description).
    """
    if len(board.piece_map()) > MAX_PIECES:
        raise DomainError("tablebase_too_many_pieces", max=MAX_PIECES)
    fen = board.fen()
    key = f"tablebase:{fen}"
    cached = await redis_module.redis_client.get(key)
    if cached:
        data = json.loads(cached)
    else:
        try:
            data = await _fetch(fen)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Tablebase request failed, falling back to the engine: %s", exc)
            try:
                return await asyncio.to_thread(_engine_probe, board.copy(stack=False))
            except EngineUnavailableError as engine_exc:
                raise DomainError("tablebase_unavailable") from engine_exc
        await redis_module.redis_client.set(key, json.dumps(data), ex=CACHE_TTL_S)
    moves = data.get("moves") or []
    best = None
    if moves:
        first = moves[0]
        move = chess.Move.from_uci(first["uci"])
        if move in board.legal_moves:
            best = {"uci": first["uci"], "san": board.san(move), "category": first.get("category"),
                    "dtm": first.get("dtm"), "dtz": first.get("dtz")}
    return {"category": data.get("category"), "dtm": data.get("dtm"), "dtz": data.get("dtz"), "best": best,
            "source": "tablebase"}
