"""
Thematic master game candidates (task 27.7): games of the champions' archive (the games table) where a positional idea of
a Big course module holds for a long stretch. The idea is recognised by the mentor's own rules (src/services/positional.py),
so the game shows exactly what the module's lesson names:

* outpost (S2.2) - the winner's knight stands on an outpost square of files c-f (is_outpost, CENTRAL_FILES);
* bad_bishop (S2.3) - the loser has a "bad" bishop (the bad_bishop feature);
* weak_pawn (S2.4) - the loser has an isolated or backward pawn that the winner presses (isolated_enemy / backward_enemy);
* king_center (O1.1) - the loser's king stays in the centre without castling while the winner has the pieces to attack it
  (king_center); short games only, counted from move 8.

A game is scored by the longest unbroken run of plies with the idea, counted from the theme's first move (the opening is
not the idea of a middlegame theme); for an outpost and a weak pawn the run lasts while the idea stays on the same square.
Each theme sets its move range and the shortest run that counts (Theme). Only decisive classical games are taken, without
simultaneous exhibitions and special-format events (SPECIAL), games already in the classics collection and with
one game per pair of players.
The output is a PGN file for scripts/build_classics.py --pgn and a list with the square and the move range of the idea -
the author checks the game and writes its intro and summary.

    python scripts/dev/theme_games.py outpost --count 4 --out outpost.pgn
"""

import argparse
import asyncio
import io
import re
import sys
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.pgn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.build_classics import NOT_CLASSICAL, OUT, _slug  # noqa: E402
from src.services import positional  # noqa: E402

# Events that slip past NOT_CLASSICAL: simultaneous exhibitions ("tour sim") and Casablanca chess (the game starts from a
# position of a historical game, not from the opening the lesson is about).
SPECIAL = re.compile(r"(?<![a-z])sim(?![a-z])|casablanca", re.IGNORECASE)


def _knight_outpost(board: chess.Board, winner: chess.Color, _loser: chess.Color) -> str | None:
    """The square of the winner's knight standing on an outpost, if any (the most central one)."""
    squares = [s for s in board.pieces(chess.KNIGHT, winner)
               if chess.square_file(s) in positional.CENTRAL_FILES and positional.is_outpost(board, s, winner)]
    return chess.square_name(min(squares, key=lambda s: abs(chess.square_file(s) - 3.5))) if squares else None


def _bad_bishop(board: chess.Board, _winner: chess.Color, loser: chess.Color) -> str | None:
    """The square of the loser's bad bishop, if any."""
    feature = positional._bad_bishop(board, loser)
    return feature.params["square"] if feature else None


def _weak_pawn(board: chess.Board, winner: chess.Color, _loser: chess.Color) -> str | None:
    """The square of the loser's isolated or backward pawn that the winner can press, if any."""
    feature = positional._isolated_enemy(board, winner) or positional._backward_enemy(board, winner)
    return feature.params["square"] if feature else None


def _king_center(board: chess.Board, _winner: chess.Color, loser: chess.Color) -> str | None:
    """The square of the loser's king stuck in the centre, if the mentor's king_center rule holds."""
    feature = positional._king_center(board, loser)
    return chess.square_name(feature.squares[0]) if feature else None


@dataclass(frozen=True)
class Theme:
    """How a theme is looked for: the detector, whether the run keeps one square, from which move, game length, run."""
    detect: Callable[[chess.Board, chess.Color, chess.Color], str | None]
    # A bad bishop moves about and stays bad; a knight leaving its outpost or a target pawn changing ends the idea.
    same_square: bool
    from_move: int = 15  # a middlegame idea is looked for after the opening
    min_moves: int = 25
    max_moves: int = 60
    min_run: int = 16  # plies: a shorter stretch is an episode, not the idea of the game


THEMES: dict[str, Theme] = {
    "outpost": Theme(_knight_outpost, same_square=True),
    "bad_bishop": Theme(_bad_bishop, same_square=False),
    "weak_pawn": Theme(_weak_pawn, same_square=True),
    # An opening lesson: the punishment comes soon, so short games, from move 8 (where king_center starts speaking).
    "king_center": Theme(_king_center, same_square=False, from_move=8, min_moves=18, max_moves=35, min_run=12),
}


def score(theme: str, pgn: str) -> dict | None:
    """The longest run of the idea in a game: {length, from_move, to_move, square, ...}; None - not a candidate."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    event = game.headers.get("Event", "") if game else ""
    if game is None or NOT_CLASSICAL.search(event) or SPECIAL.search(event):
        return None
    result = game.headers.get("Result")
    moves = list(game.mainline_moves())
    spec = THEMES[theme]
    if result not in ("1-0", "0-1") or not spec.min_moves * 2 <= len(moves) <= spec.max_moves * 2:
        return None
    winner = chess.WHITE if result == "1-0" else chess.BLACK
    board = game.board()
    best = run = (0, 0, "")  # (length, start ply, square)
    for ply, move in enumerate(moves):
        board.push(move)
        square = spec.detect(board, winner, not winner) if ply >= (spec.from_move - 1) * 2 else None
        if not square:
            run = (0, 0, "")
        elif run[0] and (square == run[2] or not spec.same_square):
            run = (run[0] + 1, run[1], square)
        else:
            run = (1, ply, square)
        best = max(best, run)
    if best[0] < spec.min_run:
        return None
    headers = game.headers
    return {"length": best[0], "from_move": best[1] // 2 + 1, "to_move": (best[1] + best[0]) // 2 + 1,
            "square": best[2], "white": headers.get("White", "?"), "black": headers.get("Black", "?"),
            "year": (headers.get("Date") or "????")[:4], "event": headers.get("Event", "?"), "result": result,
            "moves": len(moves) // 2, "pgn": str(game)}


async def _archive() -> list[str]:
    """PGN of every finished archive game."""
    from sqlalchemy import select

    from scripts.build_guess_positions import _sessions
    from src.models.game import Game

    engine, sessions = _sessions()
    async with sessions() as db:
        rows = (await db.execute(select(Game.pgn).where(Game.result.in_(("1-0", "0-1"))))).scalars().all()
    await engine.dispose()
    return [pgn for pgn in rows if pgn]


def main() -> None:
    """Entry point: scores the archive for a theme and writes the best candidates."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("theme", choices=sorted(THEMES))
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--out", type=Path, required=True, help="PGN file of the candidates")
    args = parser.parse_args()

    pgns = asyncio.run(_archive())
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        scored = [s for s in pool.map(score, [args.theme] * len(pgns), pgns, chunksize=200) if s]
    scored.sort(key=lambda s: -s["length"])
    taken, pairs = [], set()
    for item in scored:
        pair = frozenset((item["white"], item["black"]))
        if pair in pairs or (OUT / f"{_slug(item['white'], item['black'], item['year'])}.json").exists():
            continue
        pairs.add(pair)
        taken.append(item)
        if len(taken) >= args.count:
            break
    args.out.write_text("\n\n".join(item["pgn"] for item in taken) + "\n", encoding="utf-8")
    print(f"{len(scored)} games with the idea; written {len(taken)} to {args.out}")
    for item in taken:
        print(f"{item['white']} - {item['black']}, {item['event']} {item['year']} {item['result']} ({item['moves']} moves): "
              f"{item['square']}, moves {item['from_move']}-{item['to_move']} ({item['length']} plies)")


if __name__ == "__main__":
    main()
