"""
Level exams of the Grand Course (task 27.12) -> src/services/data/level_exams.json. Not for CI: needs the puzzle database and
Stockfish.

For each level 0-5 a fixed set of QUESTIONS positions across the course branches: tactics (T, catalog sections A-E),
mate and attack (M, F-G), endgame (E, J), strategy (S), calculation (C, K). Positions are database puzzles (CC0) near the
level's rank threshold (LEVEL_TARGETS, ±SPREAD); the strategy branch instead takes quiet moves from the public games of the
library (tagged by pawn structure, task 27.5), see QUIET_BRANCHES. A position is taken only if the answer is objectively
unique: the first move of the solution is the engine's best move leading the second by at least GAP_CP, or a mate (then any
mate counts). A library position must also be quiet (no capture, check, promotion; the evaluation stays within QUIET_CP).
The set is stored in full (position, answer, rating, source id) - after the build it does not depend on the database.
A library position has no puzzle rating: its rating is the aim of the level (the difficulty is set by the level, not measured).

    python scripts/build_level_exams.py --time 0.5
"""

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

import chess
import chess.engine

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "src" / "services" / "data" / "level_exams.json"
LEVEL_TARGETS = (800, 1000, 1200, 1400, 1600, 1800)
SPREAD = 250
# Branch -> theme catalog sections and number of questions (12 in total).
BRANCHES = {"T": ("ABCDE", 4), "M": ("FG", 3), "E": ("J", 2), "S": ("", 2), "C": ("K", 1)}
# Branches whose positions come from library games instead of puzzles (empty theme sections above).
QUIET_BRANCHES = frozenset("S")
GAP_CP = 150
QUIET_CP = 300  # a position with a bigger advantage is a tactical outcome, not a strategic choice
# Plies of a game from which quiet positions are taken: past the book, before the endgame.
QUIET_PLIES = range(14, 56)
LIBRARY_MIN_PLIES = 40
PER_GAME = 3  # positions tried per game, so that one game does not dominate the pool
LIBRARY_CANDIDATES = 150
MATE = 100_000
CANDIDATES = 40


async def _candidates(sections: str, low: int, high: int, used: set[str]) -> list[tuple[str, str, str, int]]:
    """Selects from the database the puzzles of the required branch and rating for a level exam."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from src.core.config import settings
    from src.models.puzzle import Puzzle, PuzzleTheme
    from src.services.themes import THEMES

    codes = [t.code for t in THEMES if t.section in sections]
    # The database's own engine for each asyncio.run: the shared pool is bound to an already closed event loop.
    engine = create_async_engine(settings.async_database_url, poolclass=NullPool)
    async with engine.connect() as db:
        rows = (await db.execute(
            select(Puzzle.source_id, Puzzle.fen, Puzzle.moves, Puzzle.rating).join(PuzzleTheme)
            .where(PuzzleTheme.theme.in_(codes), Puzzle.rating.between(low, high)).distinct()
        )).all()
    await engine.dispose()
    return [tuple(r) for r in rows if r[0] not in used]  # type: ignore[misc]


def quiet_positions(moves: list[str], rng: random.Random, count: int = PER_GAME) -> list[tuple[str, str]]:
    """Picks up to `count` quiet positions of a game: (FEN before the previous ply, "previous answer" in UCI).

    The answer (the move played from the position) must not capture, give check or promote, and the side to move must not
    be in check: such a choice is positional, not a tactic. The pair is shaped like a puzzle row, so `_verified` takes it.
    """
    board = chess.Board()
    found: list[tuple[str, str]] = []
    for ply, uci in enumerate(moves):
        move = chess.Move.from_uci(uci)
        if ply + 1 in QUIET_PLIES and ply >= 1 and not board.is_check() and not (
                board.is_capture(move) or board.gives_check(move) or move.promotion):
            previous = board.copy()
            previous.pop()  # Position before the previous ply: the puzzle format starts with the opponent's move.
            found.append((previous.fen(), f"{board.peek().uci()} {uci}"))
        board.push(move)
    rng.shuffle(found)
    return found[:count]


async def _library_candidates(rng: random.Random, used: set[str]) -> list[tuple[str, str, str]]:
    """Quiet positions from the tagged public library games: (source id, FEN, "previous answer")."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from src.core.config import settings
    from src.models.library import LibraryGame

    engine = create_async_engine(settings.async_database_url, poolclass=NullPool)
    async with engine.connect() as db:
        rows = (await db.execute(
            select(LibraryGame.id, LibraryGame.moves).where(
                LibraryGame.structure.is_not(None), LibraryGame.start_fen.is_(None),
                LibraryGame.plies >= LIBRARY_MIN_PLIES)
        )).all()
    await engine.dispose()
    pool = []
    for game_id, moves in rows:
        for fen, line in quiet_positions(moves.split(), rng):
            source_id = f"lib{game_id}:{line.split()[1]}"
            if source_id not in used:
                pool.append((source_id, fen, line))
    return pool


def _verified(engine: chess.engine.SimpleEngine, fen: str, moves: str, limit: chess.engine.Limit,
              quiet: bool = False) -> dict | None:
    """Uses the engine to check that the best move is unique and the full solution of the puzzle.

    With `quiet` (library positions) a mate, or an evaluation beyond QUIET_CP either way, rejects the position."""
    board = chess.Board(fen)
    first, *rest = moves.split()
    board.push_uci(first)
    answer = chess.Move.from_uci(rest[0])
    infos = engine.analyse(board, limit, multipv=2)
    if not infos or not infos[0].get("pv") or infos[0]["pv"][0] != answer:
        return None
    best = infos[0]["score"].pov(board.turn)
    after = board.copy()
    after.push(answer)
    mate = best.is_mate() and (best.mate() or 0) > 0
    if quiet and (best.is_mate() or abs(best.score() or 0) > QUIET_CP):
        return None
    if not mate:
        if len(infos) < 2:
            return None
        gap = best.score(mate_score=MATE) - infos[1]["score"].pov(board.turn).score(mate_score=MATE)
        if gap < GAP_CP:
            return None
    # moves - the whole solution (player's move, opponent's reply, ...): in the test it is played out to the end.
    return {"fen": board.fen(), "previous_move": first, "answer": answer.uci(), "moves": rest, "mate": bool(mate)}


def main() -> None:
    """Builds and saves position sets for the course level exams."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--time", type=float, default=0.5, help="Engine seconds per position")
    parser.add_argument("--seed", type=int, default=2712)
    args = parser.parse_args()

    from src.services.bots.base import resolve_stockfish_path

    path = resolve_stockfish_path()
    if not path:
        raise SystemExit("Stockfish not found: python scripts/setup_stockfish.py")
    rng = random.Random(args.seed)
    library_rng = random.Random(args.seed + 1)  # separate stream: the other branches' positions stay as they were
    limit = chess.engine.Limit(time=args.time)
    used: set[str] = set()
    levels = []
    with chess.engine.SimpleEngine.popen_uci(path) as engine:
        for level, target in enumerate(LEVEL_TARGETS):
            questions = []
            for branch, (sections, count) in BRANCHES.items():
                # Ratings of the branch's questions - evenly over the window around the level threshold.
                aims = [target - SPREAD + round(i * 2 * SPREAD / max(1, count - 1)) if count > 1 else target
                        for i in range(count)]
                quiet = branch in QUIET_BRANCHES
                if quiet:
                    # Library positions carry no rating: the level's aim is the rating, the order is random.
                    pool = [(sid, fen, moves, 0) for sid, fen, moves in asyncio.run(_library_candidates(library_rng, used))]
                else:
                    pool = asyncio.run(_candidates(sections, max(400, target - SPREAD - 150), target + SPREAD + 150, used))
                for aim in aims:
                    pool.sort(key=lambda row: (0 if quiet else abs(row[3] - aim), rng.random()))
                    for source_id, fen, moves, rating in pool[:LIBRARY_CANDIDATES if quiet else CANDIDATES]:
                        if source_id in used:
                            continue
                        checked = _verified(engine, fen, moves, limit, quiet)
                        used.add(source_id)
                        if checked:
                            questions.append({"branch": branch, "rating": aim if quiet else rating, "source_id": source_id,
                                              **checked})
                            break
                    else:
                        raise SystemExit(f"Level {level}, branch {branch}: no verified position near {aim}")
            questions.sort(key=lambda q: q["rating"])
            levels.append({"level": level, "target": target, "questions": questions})
            print(f"Level {level}: {len(questions)} positions, ratings {questions[0]['rating']}-{questions[-1]['rating']}",
                  flush=True)
    OUT.write_text(json.dumps(levels, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"→ {OUT}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    main()
