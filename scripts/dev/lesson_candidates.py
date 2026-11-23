"""
Lesson position candidates (task 27.7): database puzzles of a registry theme where each solver move is the only one
(the best engine move leading the second by >= --gap cp, or a mate). Prints the position after the opponent's move, the
solution in UCI and SAN and the rating - the author picks lesson positions and writes the texts; verify_lessons.py checks it.

    python scripts/dev/lesson_candidates.py intermezzo --min 1100 --max 1700 --count 6
    python scripts/dev/lesson_candidates.py clearance --csv data/puzzles/lichess_subset.csv.gz   # without the database

With --csv the puzzles are read from a Lichess-format file (PuzzleId, FEN, Moves, Rating, ..., Themes), the theme is a
Lichess name (clearance, interference, quietMove...); the database is not needed.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import chess
import chess.engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

MATE = 100_000


async def _puzzles(theme: str, low: int, high: int, max_plies: int) -> list[tuple[str, str, str, int]]:
    """Selects from the DB the puzzles of the given theme and rating range."""
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from src.core.config import settings
    from src.models.puzzle import Puzzle, PuzzleTheme

    engine = create_async_engine(settings.async_database_url, poolclass=NullPool)
    async with engine.connect() as db:
        rows = (await db.execute(
            select(Puzzle.source_id, Puzzle.fen, Puzzle.moves, Puzzle.rating).join(PuzzleTheme)
            .where(PuzzleTheme.theme == theme, Puzzle.rating.between(low, high))
            .order_by(func.random()).limit(200)
        )).all()
    await engine.dispose()
    return [tuple(r) for r in rows if len(r[2].split()) <= max_plies]  # type: ignore[misc]


def _puzzles_from_csv(path: Path, theme: str, low: int, high: int, max_plies: int,
                      seed: int) -> list[tuple[str, str, str, int]]:
    """Reads suitable puzzles directly from the local CSV archives of the selection."""
    import csv
    import gzip
    import random

    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[operator]
        rows = [
            (row["PuzzleId"], row["FEN"], row["Moves"], int(row["Rating"]))
            for row in csv.DictReader(handle)
            if theme in row["Themes"].split() and low <= int(row["Rating"]) <= high
            and len(row["Moves"].split()) <= max_plies
        ]
    random.Random(seed).shuffle(rows)
    return rows[:200]


def _unique_line(engine, fen: str, moves: list[str], limit, gap: int) -> bool:
    """Uses the engine to check that every solution move is unique with an evaluation margin."""
    board = chess.Board(fen)
    board.push_uci(moves[0])
    for index, uci in enumerate(moves[1:]):
        move = chess.Move.from_uci(uci)
        if index % 2 == 0:  # the solver's move
            infos = engine.analyse(board, limit, multipv=2)
            if not infos or infos[0]["pv"][0] != move:
                after = board.copy()
                after.push(move)
                if not after.is_checkmate():
                    return False
            elif len(infos) > 1:
                best = infos[0]["score"].pov(board.turn)
                second = infos[1]["score"].pov(board.turn)
                if not (best.is_mate() and (best.mate() or 0) > 0) and \
                        best.score(mate_score=MATE) - second.score(mate_score=MATE) < gap:
                    return False
        board.push(move)
    return True


def main() -> None:
    """Looks for puzzles with an unambiguous solution for composing new lessons."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("theme")
    parser.add_argument("--min", type=int, default=1000)
    parser.add_argument("--max", type=int, default=1800)
    parser.add_argument("--count", type=int, default=6)
    parser.add_argument("--plies", type=int, default=6, help="Solution length in the database (with opp. move), at most")
    parser.add_argument("--gap", type=int, default=150)
    parser.add_argument("--time", type=float, default=0.7)
    parser.add_argument("--csv", type=Path, default=None, help="Puzzle file in Lichess format instead of the database")
    parser.add_argument("--seed", type=int, default=1, help="Order of puzzles from the file (reproducible)")
    args = parser.parse_args()

    from src.services.bots.base import resolve_stockfish_path

    path = resolve_stockfish_path()
    if not path:
        raise SystemExit("Stockfish not found: python scripts/setup_stockfish.py")
    found = 0
    with chess.engine.SimpleEngine.popen_uci(path) as engine:
        puzzles = (_puzzles_from_csv(args.csv, args.theme, args.min, args.max, args.plies, args.seed) if args.csv
                   else asyncio.run(_puzzles(args.theme, args.min, args.max, args.plies)))
        for source_id, fen, moves, rating in puzzles:
            line = moves.split()
            if not _unique_line(engine, fen, line, chess.engine.Limit(time=args.time), args.gap):
                continue
            board = chess.Board(fen)
            board.push_uci(line[0])
            start = board.fen()
            sans = []
            for uci in line[1:]:
                sans.append(board.san(chess.Move.from_uci(uci)))
                board.push_uci(uci)
            print(f"{source_id}\t{rating}\t{start}\t{' '.join(line[1:])}\t{' '.join(sans)}", flush=True)
            found += 1
            if found >= args.count:
                break


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    main()
