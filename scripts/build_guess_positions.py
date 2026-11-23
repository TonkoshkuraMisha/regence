# --- FILE: scripts/build_guess_positions.py ---
"""
Selection of positions for "Guess the master's move" (task 14.3). Not for CI: needs Stockfish and time.

Games are the masters archive in the database (both players from the PGN archive). Two engine passes:
1. fast (MultiPV 2, --shallow-depth) over every move of the game after the book opening (table 16.1) and before the
   technical endgame: candidates - the master's move is best and the gap is close to the threshold; also the
   opponent's mistakes for breaking streaks;
2. deep (MultiPV 3, --deep-time s per position) over the candidates only: the rules of src/services/guess_selection.py,
   position themes - from the master's move and the engine continuation.
Positions and streaks that pass are written to guess_positions (a re-run skips games that were already selected).

    python scripts/build_guess_positions.py --games 300 --workers 8
    python scripts/build_guess_positions.py --refilter   # previously selected: drop the opening and technical endgame,
                                                         # set the themes (no engine, from the master's move)
"""

import argparse
import asyncio
import io
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import chess
import chess.engine
import chess.pgn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.services.guess_selection import (  # noqa: E402
    EQUAL_CP,
    GAP_CP,
    OPPONENT_ERROR_CP,
    WIN_CP,
    Line,
    book_plies,
    build_series,
    difficulty,
    in_opening,
    is_technical_endgame,
    position_themes,
    qualifies,
)

ARCHIVE_MARKER = "!historical_archive_no_login!"
CANDIDATE_SLACK_CP = 40  # the fast pass is lenient: the deep one decides finally
MATE = 100000
SAVE_EVERY = 25

def _open_engine() -> chess.engine.SimpleEngine:
    """One engine per game: closed in analyse_game - otherwise its background thread keeps the process from exiting."""
    from src.services.bots.base import resolve_stockfish_path

    path = resolve_stockfish_path()
    if not path:
        raise SystemExit("Stockfish not found: python scripts/setup_stockfish.py")
    engine = chess.engine.SimpleEngine.popen_uci(path)
    engine.configure({"Threads": 1, "Hash": 32})
    return engine


def _analyse(engine, board: chess.Board, limit: chess.engine.Limit, multipv: int) -> tuple[list[Line], list[chess.Move]]:
    """Engine lines (first move, evaluation) and the line of the best of them."""
    infos = engine.analyse(board, limit, multipv=min(multipv, board.legal_moves.count()))
    infos = [i for i in infos if i.get("pv")]
    lines = [(i["pv"][0], i["score"].pov(board.turn).score(mate_score=MATE)) for i in infos]
    return lines, list(infos[0]["pv"]) if infos else []


def _lines(engine, board: chess.Board, limit: chess.engine.Limit, multipv: int) -> list[Line]:
    """Asks the engine for several best lines (MultiPV) for a position."""
    return _analyse(engine, board, limit, multipv)[0]


def _move_cp(engine, board: chess.Board, move: chess.Move, limit: chess.engine.Limit) -> int:
    """Returns the evaluation of a specific move in centipawns for the side to move."""
    info = engine.analyse(board, limit, root_moves=[move])
    return info["score"].pov(board.turn).score(mate_score=MATE)


def _candidate(best: int, second: int) -> bool:
    """Fast pass: close to the selection rules with the CANDIDATE_SLACK_CP margin - the deep pass decides finally."""
    slack = CANDIDATE_SLACK_CP
    return (best - second >= GAP_CP - slack
            or (best >= WIN_CP - slack and second <= EQUAL_CP + slack)
            or (best >= -EQUAL_CP - slack and second <= -WIN_CP + slack))


def analyse_game(game_id: int, pgn: str, shallow_depth: int, deep_time: float) -> tuple[int, list[dict]]:
    """Positions of the game that passed selection: [{ply, fen, move, best_cp, gap_cp, lines, difficulty, side}] + streaks."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return game_id, []
    board = game.board()
    shallow = chess.engine.Limit(depth=shallow_depth)
    deep = chess.engine.Limit(time=deep_time)
    passing: dict[int, dict] = {}
    errors: set[int] = set()
    engine = _open_engine()
    try:
        _scan(engine, game, board, shallow, deep, passing, errors)
    finally:
        engine.quit()
    _mark_series(passing, errors)
    return game_id, list(passing.values())


def _scan(engine, game, board, shallow, deep, passing: dict[int, dict], errors: set[int]) -> None:
    """Finds objectively solvable positions and streaks in a game for "Guess the move"."""
    moves = list(game.mainline_moves())
    book = book_plies(moves)
    for ply, move in enumerate(moves):
        if is_technical_endgame(board):
            break  # pieces only leave the board: what follows is tablebase technique
        if not in_opening(board, book) and board.legal_moves.count() > 1:
            lines = _lines(engine, board, shallow, 2)
            if len(lines) == 2:
                (best_move, best), (_, second) = lines
                if move != best_move:
                    played = _move_cp(engine, board, move, shallow)
                    if best - played > OPPONENT_ERROR_CP:
                        errors.add(ply)
                elif _candidate(best, second):
                    deep_lines, pv = _analyse(engine, board, deep, 3)
                    verdict = qualifies(board, move, deep_lines, book)
                    if verdict is not None:
                        passing[ply] = {
                            "ply": ply, "fen": board.fen(), "move": move.uci(), "best_cp": verdict.best_cp,
                            "gap_cp": verdict.gap_cp, "lines": [[m.uci(), cp] for m, cp in deep_lines],
                            "difficulty": difficulty(board, move, verdict),
                            "themes": position_themes(board, move, pv),
                        }
        board.push(move)


def _mark_series(passing: dict[int, dict], errors: set[int]) -> None:
    """Streaks - separately for white (even plies) and black."""
    for parity in (0, 1):
        plies = [p for p in passing if p % 2 == parity]
        for number, run in enumerate(build_series(plies, errors)):
            for index, ply in enumerate(run):
                passing[ply]["series"] = (parity, number)
                passing[ply]["series_index"] = index
                passing[ply]["difficulty"] += 50 * (len(run) - 1)


def _sessions():
    """The base's own engine for each asyncio.run: the shared engine pool is bound to an event loop that is already closed."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from src.core.config import settings

    engine = create_async_engine(settings.async_database_url, poolclass=NullPool)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _load_games(limit: int, seed: int) -> list[tuple[int, str]]:
    """Loads master games from the database to look for key moments."""
    from sqlalchemy import select
    from sqlalchemy.orm import aliased

    from src.models.game import Game, GameStatus
    from src.models.guess import GuessPosition
    from src.models.user import User

    white, black = aliased(User), aliased(User)
    engine, sessions = _sessions()
    async with sessions() as db:
        done = set((await db.execute(select(GuessPosition.game_id).distinct())).scalars())
        rows = (await db.execute(
            select(Game.id, Game.pgn)
            .join(white, white.id == Game.white_player_id).join(black, black.id == Game.black_player_id)
            .where(white.hashed_password == ARCHIVE_MARKER, black.hashed_password == ARCHIVE_MARKER,
                   Game.status == GameStatus.COMPLETED, Game.pgn.is_not(None))
        )).all()
    await engine.dispose()
    games = [(gid, pgn) for gid, pgn in rows if gid not in done]
    random.Random(seed).shuffle(games)
    return games[:limit]


async def _save(results: list[tuple[int, list[dict]]]) -> tuple[int, int]:
    """Saves the selected positions and streaks into the guess_positions table."""
    from sqlalchemy import func, select

    from src.models.guess import GuessPosition

    positions = series_count = 0
    engine, sessions = _sessions()
    async with sessions() as db:
        next_series = ((await db.execute(select(func.max(GuessPosition.series_id)))).scalar() or 0) + 1
        for game_id, items in results:
            ids: dict[tuple, int] = {}
            for item in items:
                series_id = None
                if "series" in item:
                    if item["series"] not in ids:
                        ids[item["series"]] = next_series
                        next_series += 1
                        series_count += 1
                    series_id = ids[item["series"]]
                db.add(GuessPosition(
                    game_id=game_id, ply=item["ply"], fen=item["fen"], move_uci=item["move"],
                    best_cp=item["best_cp"], gap_cp=item["gap_cp"], lines=item["lines"],
                    series_id=series_id, series_index=item.get("series_index", 0), difficulty=item["difficulty"],
                    themes=item.get("themes", []),
                ))
                positions += 1
        await db.commit()
    await engine.dispose()
    return positions, series_count


async def _refilter() -> tuple[int, int]:
    """Re-checks stored positions against the opening/endgame filters and tags the themes."""
    from src.services.guess import refilter

    engine, sessions = _sessions()
    async with sessions() as db:
        result = await refilter(db)
    await engine.dispose()
    return result


def main() -> None:
    """Entry point of the generator and filter of "Guess the master's move" mode positions."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=200, help="How many new games to analyse")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--shallow-depth", type=int, default=10)
    parser.add_argument("--deep-time", type=float, default=1.0, help="Seconds per position in the second pass")
    parser.add_argument("--seed", type=int, default=20261115)
    parser.add_argument("--refilter", action="store_true",
                        help="Only bring the selected positions to the current rules (no engine)")
    args = parser.parse_args()
    if args.refilter:
        removed, tagged = asyncio.run(_refilter())
        print(f"Removed {removed} positions (opening, technical endgame), themes set for {tagged}", flush=True)
        return

    started = time.monotonic()
    games = asyncio.run(_load_games(args.games, args.seed))
    print(f"{len(games)} games, {args.workers} processes", flush=True)
    batch: list[tuple[int, list[dict]]] = []
    positions = series = 0

    def flush() -> None:
        """Writes the accumulated batch of selected positions into the database."""
        nonlocal positions, series
        if batch:
            saved, new_series = asyncio.run(_save(batch))
            positions, series = positions + saved, series + new_series
            batch.clear()

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(analyse_game, gid, pgn, args.shallow_depth, args.deep_time) for gid, pgn in games]
        for done, future in enumerate(as_completed(futures), 1):
            game_id, items = future.result()
            batch.append((game_id, items))
            print(f"[{done}/{len(games)}] game {game_id}: {len(items)} positions", flush=True)
            if len(batch) >= SAVE_EVERY:
                flush()  # a failure in the middle of a long run loses at most one batch
    flush()
    print(f"Saved {positions} positions, {series} streaks in {(time.monotonic() - started) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    main()
