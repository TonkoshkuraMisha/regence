# --- FILE: src/services/opening_explorer.py ---
"""
Opening explorer (task 16.2): moves from a position with statistics from the position index (task 16.1), the opening name
(src/services/openings.py) and master games that passed through the position: from the champions archive and from public
collections of the library (8b, owner's decision of 18.11). A library example carries its marks (pawn structure and
tactical themes, task 27.5) so the client can link to the library search by them.

Duplicates between the archive and the library (the same game is often in both places): two games under one position count as
one if the surnames of both players and the year match. The library game is kept - it has markup and explanations;
the archive one is removed. Library games are not included in the move statistics at all (position_stats holds only site
games and archive games), so a game will not be counted twice.

Data: move statistics are the position_stats table, games through a position are position_games (both are filled by
src/services/position_index.py from the first 30 plies of each finished game, so there are no statistics deeper);
the games themselves and player names are games and users. Library games are position_library_games and library_games,
visibility is the collections (library_collections.visibility = public). Opening names - src/services/data/openings.tsv.
"""

import chess
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.core.errors import DomainValueError
from src.models.game import Game
from src.models.library import LibraryAnnotation, LibraryCollection, LibraryGame, LibraryGameCollection
from src.models.position import PositionGame, PositionLibraryGame
from src.models.user import User
from src.services import library, openings, position_index
from src.services.game_themes import decode as decode_themes

# Marker of a historical archive player: the archive loader (src/db/seed.py) writes this string instead of a password hash,
# and one cannot log in as such a player. The same string is duplicated in src/api/social.py and src/api/watch.py.
ARCHIVE_PASSWORD = "!historical_archive_no_login!"
MAX_MOVES = 60  # how many plies of the request are taken into account; the rest are silently dropped
MASTER_GAMES = 12  # how many master games (archive and library together) are shown under a position


def board_after(moves_uci: list[str]) -> tuple[chess.Board, list[chess.Move]]:
    """
    Board after a list of UCI moves from the starting position (no more than MAX_MOVES plies are taken into account); an
    illegal move is refused with illegal_move.
    """
    board = chess.Board()
    played = []
    for uci in moves_uci[:MAX_MOVES]:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            raise DomainValueError("illegal_move", move=uci) from None
        if move not in board.legal_moves:
            raise DomainValueError("illegal_move", move=uci)
        board.push(move)
        played.append(move)
    return board, played


async def master_games(db: AsyncSession, board: chess.Board, limit: int = MASTER_GAMES) -> list[dict]:
    """
    Archive games (both players from the archive) that passed through the position: newest by date first, undated ones at
    the end. The position is looked up by the hash position_index.position_key; the year is the first four characters of
    the PGN date.
    """
    white, black = aliased(User), aliased(User)
    rows = (await db.execute(
        select(Game.id, white.username, black.username, Game.pgn_date, Game.result, Game.eco)
        .join(PositionGame, PositionGame.game_id == Game.id)
        .join(white, white.id == Game.white_player_id).join(black, black.id == Game.black_player_id)
        .where(PositionGame.position_hash == position_index.position_key(board),
               white.hashed_password == ARCHIVE_PASSWORD, black.hashed_password == ARCHIVE_PASSWORD)
        .order_by(Game.pgn_date.desc().nulls_last(), Game.id.desc()).limit(limit)
    )).all()
    return [
        {"id": gid, "white": w, "black": b, "year": (date or "")[:4] or None, "result": result, "eco": eco,
         "source": "archive"}
        for gid, w, b, date, result, eco in rows
    ]


def player_key(name: str) -> str:
    """
    Player surname for comparing archive and library games: the part before the comma ("Lasker, Emanuel" -> lasker), otherwise
    the last word; lowercase letters only. An empty name gives an empty string (such a game will match nothing).
    """
    if "," in name:
        base = name.split(",")[0]
    else:
        words = name.split()
        base = words[-1] if words else ""
    return "".join(ch for ch in base.lower() if ch.isalpha())


def _same_game(game: dict) -> tuple[str, str, str] | None:
    """The "same game" marker: surnames of both players and the year; without a year or name there is nothing to compare."""
    white, black, year = player_key(game["white"]), player_key(game["black"]), game.get("year")
    return (white, black, str(year)) if white and black and year else None


def merge_examples(archive: list[dict], library: list[dict], limit: int = MASTER_GAMES) -> list[dict]:
    """
    Games under a position from the archive and the library in one list: an archive game duplicated in the library (the
    same surnames and year - both already passed through this position) is removed from the archive. Sorting - newest by
    year first, undated at the end; with an equal year the library game ranks higher.
    """
    in_library = {key for key in map(_same_game, library) if key}
    merged = [*library, *(g for g in archive if _same_game(g) not in in_library)]
    merged.sort(key=lambda g: (-int(g["year"]) if g.get("year") else 1, g["source"] != "library"))
    return merged[:limit]


async def library_games(db: AsyncSession, board: chess.Board, limit: int = MASTER_GAMES) -> list[dict]:
    """
    Games of public library collections that passed through the position (position_library_games): newest by year
    first. annotated - the game has explanations visible to the player (library_annotations); structure and themes are
    the game's library marks (task 27.5: library_games.structure, library_games.themes), so the explorer can lead to
    "library games with this structure / theme".
    """
    public = exists().where(
        LibraryGameCollection.game_id == LibraryGame.id,
        LibraryCollection.id == LibraryGameCollection.collection_id,
        LibraryCollection.visibility == "public",
    )
    # Explanations the player sees: the same statuses that the game viewer shows (library.PUBLIC_ANNOTATION).
    annotated = exists().where(LibraryAnnotation.game_id == LibraryGame.id,
                               LibraryAnnotation.status.in_(library.PUBLIC_ANNOTATION))
    rows = (await db.execute(
        select(LibraryGame.id, LibraryGame.white, LibraryGame.black, LibraryGame.year, LibraryGame.result,
               LibraryGame.eco, annotated, LibraryGame.structure, LibraryGame.themes)
        .join(PositionLibraryGame, PositionLibraryGame.library_game_id == LibraryGame.id)
        .where(PositionLibraryGame.position_hash == position_index.position_key(board), public)
        .order_by(LibraryGame.year.desc().nulls_last(), LibraryGame.id.desc()).limit(limit)
    )).all()
    return [
        {"id": gid, "white": w, "black": b, "year": str(year) if year else None, "result": result, "eco": eco or None,
         "source": "library", "annotated": bool(has_notes), "structure": structure,
         "themes": decode_themes(themes or "")}
        for gid, w, b, year, result, eco, has_notes, structure, themes in rows
    ]


async def explore(db: AsyncSession, moves_uci: list[str]) -> dict:
    """
    Position reference: the opening name, moves from the position with game statistics (the position index) and master games
    that passed through it (archive and library without duplicates - merge_examples). For a move the opening is given only if
    the name changes after it.
    """
    board, played = board_after(moves_uci)
    opening = openings.classify_board_line(chess.Board(), played)
    stats = await position_index.moves_from(db, board)
    moves = []
    for stat in stats:
        move = chess.Move.from_uci(stat.move_uci)
        if move not in board.legal_moves:
            continue  # hash collision - there is no such move in the position
        after = openings.classify_board_line(chess.Board(), [*played, move])
        moves.append({
            "uci": stat.move_uci, "san": board.san(move), "games": stat.games, "white_wins": stat.white_wins,
            "draws": stat.draws, "black_wins": stat.black_wins,
            "opening": {"eco": after.eco, "name": after.name} if after and after != opening else None,
        })
    return {
        "fen": board.fen(),
        "opening": {"eco": opening.eco, "name": opening.name} if opening else None,
        "moves": moves,
        "games": merge_examples(await master_games(db, board), await library_games(db, board)),
    }
