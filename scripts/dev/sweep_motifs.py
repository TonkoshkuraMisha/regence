# --- FILE: scripts/dev/sweep_motifs.py ---
"""
A run of the mentor motif detector over PGN games: the frequency of each motif, time per ply and random
examples for manual checking. Needed when tuning the rules: the tests check hand-picked positions, while this run shows
how the detector behaves in real games (false positives are visible from the examples).

    python scripts/dev/sweep_motifs.py data/pgns/morphy_all_games.pgn 120 fork trapped skewer
"""

import collections
import random
import sys
import time
from pathlib import Path

import chess
import chess.pgn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.services.mentor_service import analyze_move  # noqa: E402


def main(path: str, games_limit: int, show: list[str]) -> None:
    """Measures the frequency and speed of the motif detector on PGN games."""
    random.seed(7)
    counts: collections.Counter[str] = collections.Counter()
    samples: dict[str, list[tuple[str, str, object]]] = collections.defaultdict(list)
    plies = 0
    started = time.perf_counter()
    with open(path, encoding="utf-8", errors="replace") as handle:
        for _ in range(games_limit):
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            board = game.board()
            for move in game.mainline_moves():
                if not board.is_valid() or move not in board.legal_moves:
                    break  # archives contain games with a handicap and with a skipped move
                facts = analyze_move(board, move)
                san = board.san(move)
                for motif in facts.created:
                    counts[motif.code] += 1
                    if len(samples[motif.code]) < 40:
                        samples[motif.code].append((board.fen(), san, motif))
                board.push(move)
                plies += 1
    elapsed = time.perf_counter() - started
    print(f"plies: {plies}, time: {elapsed:.1f} s, per ply: {elapsed / max(plies, 1) * 1000:.1f} ms")
    for code, count in counts.most_common():
        print(f"  {code:18} {count:6}  {count / max(plies, 1) * 100:5.1f} % of plies")
    for code in show:
        print(f"\n=== {code} (position before the move | move -> square and targets)")
        for fen, san, motif in random.sample(samples[code], min(6, len(samples[code]))):
            targets = [chess.square_name(t) for t in motif.targets]  # type: ignore[attr-defined]
            print(f"  {fen} | {san} -> {chess.square_name(motif.square)} {targets} {motif.value}")  # type: ignore[attr-defined]


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3:])
