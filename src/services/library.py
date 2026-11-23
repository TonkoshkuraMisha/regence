"""
Game library (tasks 27.1-27.2): parsing PGN into library records, merging identical games, the collection tree,
visibility and PGN assembly for viewing.

On import only the headers and the main line are taken: comments, variations and evaluations from the files are discarded
(rule 5, `docs/research/books-library-review.md`). An illegal move cuts the game off at that move, not the import.

Data: the tables library_games, library_collections, library_game_collections (src/models/library.py); PGN files are read
by the scripts scripts/import_library.py and scripts/build_master_books.py and the initial load src/db/seed.py.
Visibility and annotations are used by src/api/library.py and src/services/opening_explorer.py.
"""

import hashlib
import io
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import TextIO

import chess
import chess.pgn
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.library import LibraryCollection, LibraryGame, LibraryGameCollection
from src.models.user import User
from src.services import openings, pawn_structures, position_index
from src.services.beauty import is_beautiful
from src.services.game_engine import normalize_result

STANDARD_FEN = chess.STARTING_FEN
# The main line length limit, plies: a longer one is left truncated rather than rejected.
MAX_PLIES = 1000
# The year at the start of the Date field ("1985.??.??").
YEAR = re.compile(r"^(\d{4})")


@dataclass
class ParsedGame:
    """
    A game read from PGN: header fields, the main line of moves and its hash -- by which identical games from different
    files are merged.
    """
    white: str
    black: str
    event: str
    site: str
    date: str
    year: int | None
    round: str
    result: str
    white_elo: int | None
    black_elo: int | None
    eco: str
    opening: str
    start_fen: str | None
    moves: list[str]

    @property
    def moves_hash(self) -> str:
        """SHA-256 of the players, year, starting position and moves: the merge key of identical games."""
        key = "|".join((self.white.lower(), self.black.lower(), str(self.year or ""), self.start_fen or "",
                        " ".join(self.moves)))
        return hashlib.sha256(key.encode("utf-8")).hexdigest()


# Figurine symbols of old fonts in PGN text (¢ king ... § pawn) and the move letters they are replaced with; a symbol
# is replaced only before a square or a capture (see _FIGURINE).
FIGURINES = {"¢": "K", "£": "Q", "¤": "N", "¥": "B", "¦": "R", "§": "P"}
_FIGURINE = re.compile(r"[¢£¤¥¦§](?=[a-hx])")
_LATIN_HIGH = re.compile(r"[\u00c0-\u00ff]")
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")
_HIGH_WORD = re.compile(r"[\u00c0-\u00ff]{3,}")


def repair_text(value: str) -> str:
    """
    Text in cp1251 read as single-byte Latin (mojibake such as "Ñèöèëèàíñêàÿ") -- back to
    Cyrillic; font figurines -- to move letters. Latin with diacritics (Müller, Réti) is left alone: it has few
    high letters, while Cyrillic read the wrong way has almost all of them.
    """
    value = _FIGURINE.sub(lambda m: FIGURINES[m.group(0)], value)
    if _CYRILLIC.search(value):
        return value
    high = len(_LATIN_HIGH.findall(value))
    letters = high + sum(ch.isascii() and ch.isalpha() for ch in value)
    if high >= 2 and high / letters > 0.5:
        return _to_cp1251(value)
    # A Latin prefix dilutes the share ("KID_AverbakhVar-Ñòàðîèíäèéñêàÿ"): a word of three or more high letters
    # in a row does not occur in real Western names.
    return _HIGH_WORD.sub(lambda m: _to_cp1251(m.group(0)), value)


def _to_cp1251(value: str) -> str:
    """The reverse of "cp1251 read as cp1252/latin-1"; if it fails -- the string as is."""
    for single_byte in ("cp1252", "latin-1"):
        try:
            return value.encode(single_byte).decode("cp1251")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return value


def _header(game: chess.pgn.Game, name: str, limit: int) -> str:
    """A PGN header after repair_text, truncated to limit; "?" and "????.??.??" -- an empty string."""
    value = repair_text(game.headers.get(name, "").strip())
    return "" if value in ("?", "????.??.??") else value[:limit]


def _int(value: str) -> int | None:
    """A rating from a header: an integer from 1 to 3999, otherwise None."""
    value = value.strip()
    return int(value) if value.isdigit() and 0 < int(value) < 4000 else None


def parse_game(game: chess.pgn.Game) -> ParsedGame | None:
    """A PGN game -> a library record; None -- a game without moves or chess of another variant."""
    variant = game.headers.get("Variant", "").lower()
    if variant and variant not in ("standard", "chess"):
        return None
    try:
        board = game.board()
    except ValueError:
        return None
    start_fen = None if board.fen() == STANDARD_FEN else board.fen()
    moves: list[str] = []
    node: chess.pgn.GameNode = game
    while node.variations and len(moves) < MAX_PLIES:
        node = node.variations[0]
        move = node.move
        if move is None or move not in board.legal_moves:
            break
        moves.append(move.uci())
        board.push(move)
    if not moves:
        return None
    date = _header(game, "Date", 10)
    year_match = YEAR.match(date)
    year = int(year_match.group(1)) if year_match and 1400 < int(year_match.group(1)) < 2200 else None
    opening = openings.classify(moves) if start_fen is None else None
    eco = _header(game, "ECO", 3).upper()
    if not re.fullmatch(r"[A-E]\d\d", eco):
        eco = opening.eco if opening else ""
    result = game.headers.get("Result", "*").strip()
    return ParsedGame(
        white=_header(game, "White", 120), black=_header(game, "Black", 120), event=_header(game, "Event", 200),
        site=_header(game, "Site", 200), date=date, year=year, round=_header(game, "Round", 20),
        result=normalize_result(result),
        white_elo=_int(game.headers.get("WhiteElo", "")), black_elo=_int(game.headers.get("BlackElo", "")),
        eco=eco, opening=opening.name[:200] if opening else "", start_fen=start_fen, moves=moves,
    )


def open_pgn(path: str) -> TextIO:
    """
    A PGN file in UTF-8 or cp1251 (old Cyrillic-language databases): the encoding is determined from the start of the file.
    """
    with open(path, "rb") as raw:
        head = raw.read(65536)
    try:
        head.decode("utf-8")
        encoding = "utf-8-sig"
    except UnicodeDecodeError as exc:
        # A multibyte character cut off at the end of a block is no reason to consider the file not UTF-8.
        encoding = "utf-8-sig" if exc.start >= len(head) - 4 else "cp1251"
    return open(path, encoding=encoding, errors="replace")


def read_games(handle: TextIO) -> Iterator[chess.pgn.Game]:
    """Lazily reads games from an open PGN file until they run out."""
    while True:
        game = chess.pgn.read_game(handle)
        if game is None:
            return
        yield game


def read_text(text: str) -> Iterator[chess.pgn.Game]:
    """The same as read_games, for a PGN in a string."""
    return read_games(io.StringIO(text))


@dataclass
class ImportStats:
    """Import counters: games read, added, duplicates found, attached to a collection, skipped."""
    games: int = 0
    added: int = 0
    duplicates: int = 0
    linked: int = 0
    skipped: int = 0

    def __iadd__(self, other: ImportStats) -> ImportStats:
        for name in ("games", "added", "duplicates", "linked", "skipped"):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        return self


async def ensure_collection(db: AsyncSession, path: str, *, visibility: str = "public", owner_id: int | None = None,
                            source: str = "") -> LibraryCollection:
    """A collection by the path "A/B/C" with all parents; visibility and owner are those of all path nodes."""
    parent: LibraryCollection | None = None
    parts = [part.strip() for part in path.split("/") if part.strip()]
    for depth in range(len(parts)):
        sub = "/".join(parts[:depth + 1])[:500]
        node = await db.scalar(select(LibraryCollection).where(LibraryCollection.path == sub))
        if node is None:
            node = LibraryCollection(path=sub, name=parts[depth][:200], parent_id=parent.id if parent else None)
            db.add(node)
        node.visibility, node.owner_id, node.source = visibility, owner_id, source
        await db.flush()
        parent = node
    if parent is None:
        raise ValueError("empty collection path")
    return parent


async def import_games(db: AsyncSession, collection: LibraryCollection, games: Iterable[chess.pgn.Game],
                       batch: int = 500) -> ImportStats:
    """Games -> the library: new ones are added, identical ones (by hash) are only attached to the collection."""
    stats = ImportStats()
    sort = await db.scalar(select(LibraryGameCollection.sort).where(LibraryGameCollection.collection_id == collection.id)
                           .order_by(LibraryGameCollection.sort.desc()).limit(1)) or 0
    pending: list[ParsedGame] = []

    async def flush() -> None:
        """
        Writes the accumulated batch of games: already known ones (by move hash) are only attached to the collection, new
        ones are
        added to the library.
        """
        nonlocal sort
        hashes = {game.moves_hash for game in pending}
        known = dict((await db.execute(
            select(LibraryGame.moves_hash, LibraryGame.id).where(LibraryGame.moves_hash.in_(hashes))
        )).tuples().all())
        linked = set((await db.execute(
            select(LibraryGameCollection.game_id).where(LibraryGameCollection.collection_id == collection.id,
                                                        LibraryGameCollection.game_id.in_(known.values()))
        )).scalars().all()) if known else set()
        for parsed in pending:
            key = parsed.moves_hash
            if key in known:
                stats.duplicates += 1
                game_id = known[key]
            else:
                row = LibraryGame(moves_hash=key, white=parsed.white, black=parsed.black, event=parsed.event,
                                  site=parsed.site, date=parsed.date, year=parsed.year, round=parsed.round,
                                  result=parsed.result, white_elo=parsed.white_elo, black_elo=parsed.black_elo,
                                  eco=parsed.eco, opening=parsed.opening, start_fen=parsed.start_fen,
                                  plies=len(parsed.moves), moves=" ".join(parsed.moves),
                                  structure=structure_of(parsed), mate_finish=ends_in_mate(parsed.start_fen, parsed.moves),
                                  beautiful=is_beautiful(parsed.start_fen, parsed.moves))
                db.add(row)
                await db.flush()
                # Positions of the new game go into the library index: examples under a position in the openings reference
                # (8b).
                await position_index.index_library_game(db, row)
                known[key] = game_id = row.id
                stats.added += 1
            if game_id not in linked:
                sort += 1
                db.add(LibraryGameCollection(collection_id=collection.id, game_id=game_id, sort=sort))
                linked.add(game_id)
                stats.linked += 1
        await db.flush()
        pending.clear()

    for game in games:
        stats.games += 1
        parsed = parse_game(game)
        if parsed is None:
            stats.skipped += 1
            continue
        pending.append(parsed)
        if len(pending) >= batch:
            await flush()
    if pending:
        await flush()
    return stats


def structure_of(parsed: ParsedGame) -> str | None:
    """The game's pawn structure (27.5) -- only from the starting position."""
    if parsed.start_fen is not None:
        return None
    return pawn_structures.game_structure(chess.Move.from_uci(uci) for uci in parsed.moves)


def ends_in_mate(start_fen: str | None, moves: list[str]) -> bool:
    """The game ended in mate on the board (a mark for "Miniatures", 27.9)."""
    board = chess.Board(start_fen) if start_fen else chess.Board()
    try:
        for uci in moves:
            board.push(chess.Move.from_uci(uci))
    except (ValueError, AssertionError):
        return False
    return board.is_checkmate()


def visible_clause(user: User | None) -> ColumnElement[bool]:
    """Which collections a user sees: public ones, their own closed ones, service ones -- moderators."""
    conditions: list[ColumnElement[bool]] = [LibraryCollection.visibility == "public"]
    if user is not None:
        conditions.append((LibraryCollection.visibility == "owner") & (LibraryCollection.owner_id == user.id))
        if user.is_moderator:
            conditions.append(LibraryCollection.visibility == "staff")
    return or_(*conditions)


# Annotation statuses (task 27.4): auto and approved are visible to everyone, draft and review -- to moderators.
ANNOTATION_STATUSES = ("auto", "draft", "review", "approved")
# The subset of statuses shown without moderator rights.
PUBLIC_ANNOTATION = ("auto", "approved")


def annotation_view(annotation, user: User | None) -> dict | None:
    """An annotation for viewing a game -- if it can be shown to this user."""
    if annotation is None:
        return None
    if annotation.status not in PUBLIC_ANNOTATION and not (user is not None and user.is_moderator):
        return None
    body = annotation.body or {}
    return {"status": annotation.status, "version": annotation.version, "comments": body.get("comments", {}),
            "evals": body.get("evals", [])}


def to_pgn(game: LibraryGame) -> str:
    """The PGN of a library game: headers and moves, without comments."""
    pgn = chess.pgn.Game()
    for name, value in (("Event", game.event), ("Site", game.site), ("Date", game.date), ("Round", game.round),
                        ("White", game.white), ("Black", game.black), ("Result", game.result),
                        ("WhiteElo", str(game.white_elo or "")), ("BlackElo", str(game.black_elo or "")),
                        ("ECO", game.eco), ("Opening", game.opening)):
        if value:
            pgn.headers[name] = value
    if game.start_fen:
        pgn.setup(chess.Board(game.start_fen))
    node: chess.pgn.GameNode = pgn
    for uci in game.moves.split():
        node = node.add_variation(chess.Move.from_uci(uci))
    return str(pgn)
