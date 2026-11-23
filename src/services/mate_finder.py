# --- FILE: src/services/mate_finder.py ---
"""
"Find the mate" (task 16.4): the player sets the depth (up to MAX_MOVES moves), the engine looks for a mate under a time
limit and returns
the line. The engine is used only through the pool (src/services/engine_pool.py); the search runs in a thread so as not to
hold the event loop.

The route is src/api/analysis.py (closed by the fair-play rule: unavailable during one's own game). Stores nothing.
"""

import asyncio

import chess
import chess.engine

from src.services.bots.base import resolve_stockfish_path
from src.services.engine_pool import EngineUnavailableError, get_engine_pool
from src.services.game_engine import board_from_start_fen

MAX_MOVES = 5  # the greatest depth that can be requested (checked by the request schema in src/api/analysis.py)
TIME_LIMIT_S = 3.0  # limit of one search: in this time a mate in MAX_MOVES may not be found -- then the answer is "not found"


def _search(board: chess.Board, moves: int) -> tuple[int | None, list[chess.Move]]:
    """(mate in N moves from the point of view of the side to move, or None; the main line)."""
    path = resolve_stockfish_path()
    if not path:
        raise EngineUnavailableError("stockfish not found")
    with get_engine_pool(path).acquire() as engine:
        info = engine.analyse(board, chess.engine.Limit(mate=moves, time=TIME_LIMIT_S))
    if isinstance(info, list):
        info = info[0]
    mate = info["score"].relative.mate()
    return mate, list(info.get("pv") or [])


async def find_mate(fen: str, moves: int) -> dict:
    """
    Looks for a mate no longer than moves moves: whether it is found, in how many moves and the line itself (in UCI and SAN
    notation). The search runs in a
    separate thread under a time limit. "Not found" is also when the opponent mates (mate <= 0), the mate is longer than
    requested or the game in the position is already over. The line is cut to the mating move: mate moves of the side and
    mate - 1 replies of the opponent.
    """
    board = board_from_start_fen(fen)  # InvalidStartPositionError -- an impossible position
    if board.is_game_over():
        return {"found": False, "mate_in": None, "line": [], "san": []}
    mate, pv = await asyncio.to_thread(_search, board, moves)
    if mate is None or mate <= 0 or mate > moves:
        return {"found": False, "mate_in": None, "line": [], "san": []}
    line = pv[: mate * 2 - 1]
    san = []
    probe = board.copy()
    for move in line:
        san.append(probe.san(move))
        probe.push(move)
    return {"found": True, "mate_in": mate, "line": [m.uci() for m in line], "san": san}
