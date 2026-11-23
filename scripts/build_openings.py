# --- FILE: scripts/build_openings.py ---
"""
Openings table (task 16.1) from the open lichess-org/chess-openings set (CC0-1.0, see ATTRIBUTION.md):
files a.tsv ... e.tsv (eco, name, pgn) are turned into src/services/data/openings.tsv - ECO code, name, position (EPD
without counters), number of plies and the line's moves in UCI (for the favourite openings of workshop opponents, task 21.2).
An opening is identified by position, so transpositions are recognised.

    python scripts/build_openings.py <folder with a.tsv ... e.tsv>
"""

import csv
import io
import sys
from pathlib import Path

import chess.pgn

OUT = Path(__file__).resolve().parents[1] / "src" / "services" / "data" / "openings.tsv"


def main() -> None:
    """Builds the open openings table (ECO, names, FEN and UCI lines)."""
    source = Path(sys.argv[1])
    rows: dict[str, tuple[str, str, int, str]] = {}
    for name in "abcde":
        with (source / f"{name}.tsv").open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                game = chess.pgn.read_game(io.StringIO(row["pgn"]))
                assert game is not None, row
                board = game.board()
                line = []
                for move in game.mainline_moves():
                    board.push(move)
                    line.append(move.uci())
                # One position - one name: the shorter entry has priority (as in the source set).
                key = board.epd()
                if key not in rows or len(line) < rows[key][2]:
                    rows[key] = (row["eco"], row["name"], len(line), " ".join(line))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        handle.write("eco\tname\tepd\tplies\tuci\n")
        for epd, (eco, name, plies, line) in sorted(rows.items(), key=lambda item: (item[1][0], item[1][2], item[1][1])):
            handle.write(f"{eco}\t{name}\t{epd}\t{plies}\t{line}\n")
    print(f"{len(rows)} positions -> {OUT}")


if __name__ == "__main__":
    main()
