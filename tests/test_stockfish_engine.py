# --- FILE: tests/test_stockfish_engine.py ---

import chess

from src.services.bots import BOT_INSTANCES
from src.services.bots.base import analyse_with_stockfish, resolve_stockfish_path


def test_stockfish_binary_exists_and_works():
    sf_path = resolve_stockfish_path()
    assert sf_path is not None, "Stockfish binary found neither in bin/ nor in the system PATH"

    board = chess.Board()
    scores = analyse_with_stockfish(board, sf_path, depth=4, multipv=3)
    assert len(scores) > 0, "Stockfish must return candidate scores for the starting position"

    for bot_id, bot in BOT_INSTANCES.items():
        assert bot._get_active_engine_path() is not None, f"Bot {bot_id} has no Stockfish path configured"
