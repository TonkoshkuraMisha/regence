# --- FILE: scripts/dev/review_disputes.py ---
"""
Review of the "Disagree" queue (task 11.4): players dispute mentor warnings, the positions accumulate in Redis
(`coach:disputes`, the last 2000). The script re-checks each one with deep analysis and prints where the mentor
probably erred: the deep loss is noticeably smaller than the one it warned about (a false alarm - a threshold or
a miscount at low depth).

Needs Redis (REDIS_URL, as on the server) and Stockfish. Not run in CI.

    python -m scripts.dev.review_disputes --depth 20 --limit 100
"""

import argparse
import asyncio
import json

import chess
import chess.engine

from src.db import redis as redis_module
from src.services.bots.base import resolve_stockfish_path
from src.services.move_check import DISPUTES_KEY, EVAL_CLAMP_CP, MATE_CP

FALSE_ALARM_RATIO = 0.5


def deep_loss(engine: chess.engine.SimpleEngine, fen: str, move_uci: str, depth: int) -> int:
    """Computes the centipawn loss of a disputed move at a large Stockfish depth."""
    board = chess.Board(fen)
    sign = 1 if board.turn == chess.WHITE else -1

    def score(b: chess.Board) -> int:
        """Returns the engine evaluation of a position, clamped to the limit corridor."""
        info = engine.analyse(b, chess.engine.Limit(depth=depth))
        cp = info["score"].white().score(mate_score=MATE_CP) or 0
        return max(-EVAL_CLAMP_CP, min(EVAL_CLAMP_CP, cp))

    before = score(board)
    board.push_uci(move_uci)
    return max(0, sign * (before - score(board)))


async def main() -> None:
    """Re-checks the queue of disputed mentor warnings with deep analysis."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    raw = await redis_module.redis_client.lrange(DISPUTES_KEY, 0, args.limit - 1)
    entries = [json.loads(item) for item in raw]
    if not entries:
        print("The queue is empty.")
        return
    path = resolve_stockfish_path()
    if not path:
        raise SystemExit("Stockfish is required (bin/stockfish.exe or STOCKFISH_PATH).")
    engine = chess.engine.SimpleEngine.popen_uci(path)
    false_alarms = 0
    try:
        for entry in entries:
            loss = deep_loss(engine, entry["fen"], entry["move"], args.depth)
            claimed = entry.get("cp_loss")
            suspicious = claimed is not None and loss < claimed * FALSE_ALARM_RATIO
            false_alarms += suspicious
            mark = "FALSE ALARM?" if suspicious else "confirmed"
            print(f"{mark:16} was {claimed} cp, deep {loss} cp  {entry['move']}  {entry['fen']}")
    finally:
        engine.quit()
    print(f"\nTotal {len(entries)}, look like a false alarm: {false_alarms}")


if __name__ == "__main__":
    asyncio.run(main())
