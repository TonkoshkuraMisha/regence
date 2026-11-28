# --- FILE: src/models/imported_game.py ---
"""
A player's games from other sites (task 24.1): lichess, chess.com or pasted PGN.

A separate table, not games: a foreign game does not take part in the rating, archive, profile statistics, opening tree or
league - it is needed only for review with the mentor and personal puzzles (13.5). The opponent is just a name from the PGN.
import_subscriptions - the opt-in daily import from a site (ImportSubscription below).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, one_of

# Where the game is from: sites (src/services/game_import.py, SOURCES) and pasted PGN.
IMPORT_SOURCES = ("lichess", "chesscom", "pgn")
# The colour the game's owner played.
IMPORT_COLORS = ("white", "black")
# The game result - normalised on import (game_engine.normalize_result).
IMPORT_RESULTS = ("1-0", "0-1", "1/2-1/2", "*")


class ImportedGame(Base):
    """
    A player's game brought from another site or pasted as PGN: belongs to one player, stores the move record,
    information from the headers and the engine review.
    """
    __tablename__ = "imported_games"
    __table_args__ = (
        UniqueConstraint("user_id", "source", "external_id", name="uq_imported_games_source_id"),
        one_of("imported_games", "source", IMPORT_SOURCES),
        one_of("imported_games", "color", IMPORT_COLORS),
        one_of("imported_games", "result", IMPORT_RESULTS),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # lichess | chesscom | pgn; external_id - the game id on the site, for PGN - a hash of moves (a repeated paste does not
    # duplicate).
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # The player's side and the names from the PGN headers.
    color: Mapped[str] = mapped_column(String(5), nullable=False)
    white_name: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    black_name: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    white_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    black_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str] = mapped_column(String(10), nullable=False, default="*")
    # bullet | blitz | rapid | classical | daily; None - unknown (pasted PGN).
    speed: Mapped[str | None] = mapped_column(String(12), nullable=True)
    played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    pgn: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# Sites a daily import can follow (a pasted PGN has no account to follow); equal to game_import.SOURCES (test_db_integrity).
SUBSCRIPTION_SOURCES = ("lichess", "chesscom")


class ImportSubscription(Base):
    """
    A player's request to import new games from a site every day (task 24.1, "import on a schedule"): the site and the
    player's own username there. Opt-in, one row per site; the scheduled task game_import_schedule.run_due imports the
    player's recent games once a day and records how the last run went. The username is personal data: it is exported
    with the account data and erased on deletion (src/services/account.py).
    """
    __tablename__ = "import_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "source", name="uq_import_subscriptions_source"),
        one_of("import_subscriptions", "source", SUBSCRIPTION_SOURCES),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    username: Mapped[str] = mapped_column(String(30), nullable=False)
    # The last scheduled run: when, how many games it added, and the error code if it failed (import_* codes).
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
