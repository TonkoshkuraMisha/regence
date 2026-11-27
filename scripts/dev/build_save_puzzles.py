"""
"Save the game" puzzles from the full lichess database (27.11) -> appended to data/puzzles/lichess_themes_extra.csv.gz.

The database has no perpetual-check or stalemate tags, and the detector rule alone (src/services/theme_detectors.py: all
solver moves are checks and the puzzle is tagged ``equality``) also accepts puzzles where the solver is not in danger.
Here a puzzle counts as a save only if, after the opponent's first move, the solver is at least DEFICIT points of
material down and either every solver move is a check (with the ``equality`` tag) or the line ends in stalemate. Each
candidate is then checked by Stockfish: the first solver move must be the engine's best at |eval| <= DRAW_EVAL and every
other move at most -LOST_EVAL. Puzzles already in the main selection or the supplement are skipped; the rest are appended
to the supplement, keeping its rows. The soft quality filter is ``acceptable`` from build_puzzle_subset.py. Needs the
zstandard package and Stockfish; not run in CI.

    uv run --with zstandard python -m scripts.dev.build_save_puzzles path/to/lichess_db_puzzle.csv.zst
"""

import argparse
import csv
import gzip
import io
import pathlib

import chess
import chess.engine

from scripts.dev.build_puzzle_subset import FIELDS, acceptable
from scripts.dev.build_theme_extra import OUTPUT
from src.services.bots.base import resolve_stockfish_path
from src.services.puzzle_import import read_subset

DEFICIT = 3  # the solver is at least this many points down: otherwise a draw is not a "save"
DRAW_EVAL = 50  # cp: the saving move keeps the balance
LOST_EVAL = 250  # cp: every other move loses at least this much
MATE_SCORE = 10_000
VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def material(board: chess.Board, colour: chess.Color) -> int:
    """Material of one side in pawns."""
    return sum(VALUES[piece.piece_type] for piece in board.piece_map().values() if piece.color == colour)


def is_save(row: dict) -> bool:
    """A perpetual or stalemate save by the rules in the module docstring (without the engine)."""
    moves = row["Moves"].split()
    board = chess.Board(row["FEN"])
    board.push_uci(moves[0])
    solver = board.turn
    if material(board, not solver) - material(board, solver) < DEFICIT:
        return False
    all_checks = True
    for index, uci in enumerate(moves[1:]):
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            return False
        if index % 2 == 0 and not board.gives_check(move):
            all_checks = False
        board.push(move)
    if board.is_stalemate():
        return True
    return all_checks and "equality" in row["Themes"].split() and len(moves) >= 4


def engine_confirms(engine: chess.engine.SimpleEngine, row: dict, depth: int) -> bool:
    """The first solver move is the only one that keeps the balance."""
    moves = row["Moves"].split()
    board = chess.Board(row["FEN"])
    board.push_uci(moves[0])
    infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=2)
    if len(infos) < 2 or infos[0]["pv"][0].uci() != moves[1]:
        return False
    best, second = (info["score"].pov(board.turn).score(mate_score=MATE_SCORE) for info in infos[:2])
    return abs(best) <= DRAW_EVAL and second <= -LOST_EVAL


def main() -> None:
    """Scans the database, confirms the saves with the engine and appends the new ones to the supplement."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=pathlib.Path)
    parser.add_argument("--depth", type=int, default=20)
    args = parser.parse_args()
    import zstandard  # only for the build

    extra = list(read_subset(OUTPUT)) if OUTPUT.exists() else []
    known = {row["PuzzleId"] for row in read_subset()} | {row["PuzzleId"] for row in extra}
    candidates = []
    with args.source.open("rb") as raw:
        text = io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(raw), encoding="utf-8")
        for row in csv.DictReader(text):
            if row["PuzzleId"] not in known and acceptable(row) and is_save(row):
                candidates.append({field: row[field] for field in FIELDS})
    print(f"candidates: {len(candidates)}", flush=True)
    engine = chess.engine.SimpleEngine.popen_uci(resolve_stockfish_path())
    try:
        added = [row for row in candidates if engine_confirms(engine, row, args.depth)]
    finally:
        engine.quit()
    rows = sorted(extra + added, key=lambda r: r["PuzzleId"])
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: row[field] for field in FIELDS} for row in rows)
    print(f"confirmed and added: {len(added)} -> {OUTPUT} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
