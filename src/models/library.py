"""
The game library (task 27.1): a database separate from the games of players and bots (`games`) - the owner's collections,
masters'
games, model games of pawn structures and of the opening repertoire. library_games holds only the headers and the main
line of moves; move comments lie separately, in library_annotations (27.4). Import - scripts/import_library.py
(27.2), import rules - src/services/library.py.

Collections are a tree (folder -> subfolder). A game can lie in several collections; identical games from different
files are merged by `moves_hash` (SHA-256 of the player names, year, initial position and moves).
Visibility is set by the collection: public - to everyone, owner - only to the collection owner, staff - to moderators.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, one_of

# The library game result (src/services/library.py, RESULTS: anything else becomes "*" on import).
LIBRARY_RESULTS = ("1-0", "0-1", "1/2-1/2", "*")
# Annotation statuses (src/services/library.py, ANNOTATION_STATUSES).
ANNOTATION_STATUSES = ("auto", "draft", "review", "approved")

VISIBILITIES = ("public", "owner", "staff")


class LibraryCollection(Base):
    """A library collection - a node of the folder tree, with its own visibility: public, owner-only or staff."""
    __tablename__ = "library_collections"
    __table_args__ = (one_of("library_collections", "visibility", VISIBILITIES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("library_collections.id", ondelete="CASCADE"),
                                                  nullable=True, index=True)
    # The full path "Pawn structures/Isolated pawn" - the key of a repeated import.
    path: Mapped[str] = mapped_column(String(500), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    visibility: Mapped[str] = mapped_column(String(8), default="public", server_default="public")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), default="", server_default="")
    sort: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LibraryGame(Base):
    """
    A library game: headers and the main line of moves; labels for search (pawn structure, "ended in mate")
    are set by the markup.
    """
    __tablename__ = "library_games"
    __table_args__ = (one_of("library_games", "result", LIBRARY_RESULTS),)

    id: Mapped[int] = mapped_column(primary_key=True)
    moves_hash: Mapped[str] = mapped_column(String(64), unique=True)
    white: Mapped[str] = mapped_column(String(120), default="", server_default="", index=True)
    black: Mapped[str] = mapped_column(String(120), default="", server_default="", index=True)
    event: Mapped[str] = mapped_column(String(200), default="", server_default="")
    site: Mapped[str] = mapped_column(String(200), default="", server_default="")
    date: Mapped[str] = mapped_column(String(10), default="", server_default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    round: Mapped[str] = mapped_column(String(20), default="", server_default="")
    result: Mapped[str] = mapped_column(String(7), default="*", server_default="*")
    white_elo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    black_elo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eco: Mapped[str] = mapped_column(String(3), default="", server_default="", index=True)
    opening: Mapped[str] = mapped_column(String(200), default="", server_default="")
    start_fen: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plies: Mapped[int] = mapped_column(Integer, default=0, server_default="0", index=True)
    # The pawn structure of the game (task 27.5, src/services/pawn_structures.py); None - not determined.
    structure: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    # The game ended in mate on the board (miniatures 27.9 are chosen by this label).
    mate_finish: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    # A material sacrifice and the winner's mate (src/services/beauty.py, task 27.5).
    beautiful: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    # Tactical themes that paid off, ",fork,pin," (src/services/game_themes.py, task 27.5); empty for none.
    themes: Mapped[str] = mapped_column(String(200), default="", server_default="")
    moves: Mapped[str] = mapped_column(Text, default="", server_default="")  # UCI separated by spaces
    # The game is laid out into the library position index (position_library_games, src/services/position_index.py).
    positions_indexed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LibraryGameCollection(Base):
    """The "game - collection" link: one game can lie in several collections."""
    __tablename__ = "library_game_collections"
    __table_args__ = (UniqueConstraint("collection_id", "game_id", name="uq_library_game_collection"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("library_collections.id", ondelete="CASCADE"), index=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("library_games.id", ondelete="CASCADE"), index=True)
    sort: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class LibraryAnnotation(Base):
    """
    A library game annotation (task 27.4, docs/research/library-annotations.md): one per game. body is the document
    {"evals": [...], "comments": {ply: {"comment": [{key, params}], "arrows": [...]}}, "notes": {...}} - mentor
    comments as coach.* codes (as in the "Classic" 14.7) and, later, own texts in three languages. Status: auto - the mentor's
    draft (visible to everyone with a mark), draft / review - with authors, approved - checked by the owner.
    """

    __tablename__ = "library_annotations"
    __table_args__ = (one_of("library_annotations", "status", ANNOTATION_STATUSES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("library_games.id", ondelete="CASCADE"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(10), default="auto", server_default="auto", index=True)
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
