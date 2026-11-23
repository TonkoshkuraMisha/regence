# --- FILE: src/services/position_index.py ---
"""
Position index (task 16.1). Finding a position by scanning PGNs in a query is impossible - so for each finished
game the first MAX_PLIES plies are laid out into tables: position_stats (position + move -> White wins / draws /
Black wins) and position_games (position -> games). A game is indexed once (games.positions_indexed): the archive by
the script scripts/build_position_index.py, new games by a Celery task on completion (src/worker/tasks.py).

Not indexed: unfinished ones and ones without a result, tournament simulations (bots among themselves would skew the
statistics), games from a custom position (FEN header).

The position in the tables is a 64-bit Zobrist hash (placement, side to move, castling, en passant), not a FEN:
different positions may occasionally collide by hash, so the index reader checks the legality of the move
(src/services/opening_explorer.py). The index is read by the opening explorer and the repertoire.

Library games (8b) are laid out separately - in position_library_games, only "game <-> position", without
statistics: these are examples under a position in the explorer, and many of them are also in the archive (a duplicate
would be counted twice). New library games are indexed by import (src/services/library.py), those already loaded by
scripts/build_position_index.py --library. A game from a custom position (start_fen) is not indexed: its positions do not
occur in the opening.
"""

import io
from collections import Counter
from dataclasses import dataclass

import chess
import chess.pgn
import chess.polyglot
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.game import Game, GameStatus
from src.models.library import LibraryGame
from src.models.position import PositionGame, PositionLibraryGame, PositionStat

MAX_PLIES = 30  # how many first plies of a game go into the index (15 moves): there are no statistics deeper
# Game result -> increment to the counters (White wins, draws, Black wins). Another result ("*") is not indexed.
RESULTS = {"1-0": (1, 0, 0), "1/2-1/2": (0, 1, 0), "0-1": (0, 0, 1)}


def position_key(board: chess.Board) -> int:
    """Zobrist hash of the position with a sign (BIGINT in Postgres is signed)."""
    value = chess.polyglot.zobrist_hash(board)
    return value - (1 << 64) if value >= 1 << 63 else value


def _insert(db: AsyncSession, model):
    """INSERT with ON CONFLICT support for the session dialect: PostgreSQL in production, SQLite in tests."""
    return (postgresql.insert(model) if db.bind.dialect.name == "postgresql" else sqlite.insert(model))


def plies_of(pgn: str) -> tuple[str, list[tuple[int, str, int]]] | None:
    """(result, [(position hash before the move, move, ply number)]) or None if the game is not indexed."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None or "FEN" in game.headers:
        return None
    result = game.headers.get("Result")
    if result not in RESULTS:
        return None
    board = game.board()
    plies = []
    for ply, move in enumerate(game.mainline_moves()):
        if ply >= MAX_PLIES:
            break
        plies.append((position_key(board), move.uci(), ply))
        board.push(move)
    return result, plies


async def index_game(db: AsyncSession, game: Game) -> bool:
    """
    Adds a game to the index (without commit). True - added; a repeated call changes nothing. A finished game
    that cannot be indexed (custom position, no result, no moves) is still marked
    games.positions_indexed so as not to return to it. In position_games the first ply at which the
    position occurred in the game is recorded.
    """
    if game.positions_indexed or game.status != GameStatus.COMPLETED or game.is_simulation or not game.pgn:
        return False
    parsed = plies_of(game.pgn)
    game.positions_indexed = True
    if parsed is None or not parsed[1]:
        return False
    result, plies = parsed
    white, draw, black = RESULTS[result]
    # A move from a position is counted once per game, even if the position was repeated.
    moves = Counter((key, uci) for key, uci, _ in plies)
    stats = _insert(db, PositionStat).values([
        {"position_hash": key, "move_uci": uci, "white_wins": white, "draws": draw, "black_wins": black}
        for key, uci in moves
    ])
    excluded = stats.excluded
    await db.execute(stats.on_conflict_do_update(
        index_elements=["position_hash", "move_uci"],
        set_={"white_wins": PositionStat.white_wins + excluded.white_wins, "draws": PositionStat.draws + excluded.draws,
              "black_wins": PositionStat.black_wins + excluded.black_wins},
    ))
    first_ply: dict[int, int] = {}
    for key, _, ply in plies:
        first_ply.setdefault(key, ply)
    await db.execute(_insert(db, PositionGame).values([
        {"position_hash": key, "game_id": game.id, "ply": ply} for key, ply in first_ply.items()
    ]).on_conflict_do_nothing(index_elements=["position_hash", "game_id"]))
    return True


@dataclass(frozen=True)
class MoveStat:
    """Move statistics from a position: White wins, draws and Black wins; games - total games."""
    move_uci: str
    white_wins: int
    draws: int
    black_wins: int

    @property
    def games(self) -> int:
        return self.white_wins + self.draws + self.black_wins


async def moves_from(db: AsyncSession, board: chess.Board) -> list[MoveStat]:
    """Moves from a position by the index - from the most frequent."""
    rows = (await db.execute(
        select(PositionStat).where(PositionStat.position_hash == position_key(board))
    )).scalars().all()
    stats = [MoveStat(r.move_uci, r.white_wins, r.draws, r.black_wins) for r in rows]
    return sorted(stats, key=lambda s: (-s.games, s.move_uci))


async def games_through(db: AsyncSession, board: chess.Board, limit: int = 20) -> list[int]:
    """ids of games that passed through the position (new ids first)."""
    rows = await db.execute(
        select(PositionGame.game_id).where(PositionGame.position_hash == position_key(board))
        .order_by(PositionGame.game_id.desc()).limit(limit)
    )
    return list(rows.scalars())


async def index_by_id(db: AsyncSession, game_id: int) -> bool:
    """Indexes a game by number and commits - for the background task after a game finishes."""
    game = await db.get(Game, game_id)
    if game is None:
        return False
    added = await index_game(db, game)
    await db.commit()
    return added


def library_plies(moves: str) -> dict[int, int]:
    """
    {position hash: first ply} for the first MAX_PLIES plies of a library game (UCI moves separated by spaces, from
    the initial position). An illegal move breaks the parse: positions before it remain.
    """
    board = chess.Board()
    first_ply: dict[int, int] = {}
    for ply, uci in enumerate(moves.split()[:MAX_PLIES]):
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            break
        if move not in board.legal_moves:
            break
        first_ply.setdefault(position_key(board), ply)
        board.push(move)
    return first_ply


async def index_library_game(db: AsyncSession, game: LibraryGame) -> bool:
    """
    Adds a library game to position_library_games (without commit). True - added; a repeated call changes
    nothing. A game from a custom position or without moves is only marked positions_indexed.
    """
    if game.positions_indexed:
        return False
    game.positions_indexed = True
    if game.start_fen or not game.moves:
        return False
    first_ply = library_plies(game.moves)
    if not first_ply:
        return False
    await db.execute(_insert(db, PositionLibraryGame).values([
        {"position_hash": key, "library_game_id": game.id, "ply": ply} for key, ply in first_ply.items()
    ]).on_conflict_do_nothing(index_elements=["position_hash", "library_game_id"]))
    return True
