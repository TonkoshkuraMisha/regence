# --- FILE: src/models/bot_memory.py ---
"""
Bot memory (task 32.1): statistics of their opening lines by games played and the rating measured by games
with humans (32.1), memory of regular opponents (32.2) - by results and by mistakes from game reviews.
The rules are in src/services/bots/memory.py.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class BotOpeningStat(Base):
    """A bot's book move in a position (a FEN key without counters) and its result for the bot: games and points scored."""

    __tablename__ = "bot_opening_stats"
    __table_args__ = (UniqueConstraint("bot_id", "fen_key", "uci", name="uq_bot_opening_stat"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[str] = mapped_column(String(40), index=True)
    fen_key: Mapped[str] = mapped_column(String(100))
    uci: Mapped[str] = mapped_column(String(5))
    games: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    points: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")


class BotRating(Base):
    """The bot's rating from games with humans and the engine strength correction, if the divergence from the declared strength
    is stable."""

    __tablename__ = "bot_ratings"

    bot_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    rating: Mapped[float] = mapped_column(Float)
    games: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # A correction to the bot's UCI_Elo (within memory.MAX_OFFSET); recomputed once every memory.OFFSET_EVERY games.
    offset: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    offset_games: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BotRival(Base):
    """A bot's regular opponent (task 32.2): how many games were played with the player and how many points the bot scored in
    them."""

    __tablename__ = "bot_rivals"
    __table_args__ = (UniqueConstraint("bot_id", "user_id", name="uq_bot_rival"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[str] = mapped_column(String(40))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    games: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    points: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    # The last game whose mistakes from the review are already counted (memory.record_rival_errors): a repeated review of the
    # same or
    # an earlier game will not double them.
    errors_game_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class BotRivalStat(Base):
    """
    A bot's book move against a specific player: the result for the bot, whether the last game with this move was lost and in
    how many
    games the player soon after it made a mistake (errors - by engine review, memory.ERROR_WINDOW plies).
    """

    __tablename__ = "bot_rival_stats"
    __table_args__ = (UniqueConstraint("bot_id", "user_id", "fen_key", "uci", name="uq_bot_rival_stat"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[str] = mapped_column(String(40))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    fen_key: Mapped[str] = mapped_column(String(100))
    uci: Mapped[str] = mapped_column(String(5))
    games: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    points: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    last_lost: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    errors: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class BotTuning(Base):
    """Tuning of an archetype's character by self-play (task 32.3): the current strength sliders and the pot of games before
    the check."""

    __tablename__ = "bot_tunings"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    randomness: Mapped[int] = mapped_column(Integer)
    blunder_guard_cp: Mapped[int] = mapped_column(Integer)
    games: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    points: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    opponents_rating: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BotTuningLog(Base):
    """The open tuning log (the transparency page): what was measured and how the sliders were shifted."""

    __tablename__ = "bot_tuning_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    games: Mapped[int] = mapped_column(Integer)
    measured: Mapped[int] = mapped_column(Integer)
    target: Mapped[int] = mapped_column(Integer)
    randomness_before: Mapped[int] = mapped_column(Integer)
    randomness_after: Mapped[int] = mapped_column(Integer)
    guard_before: Mapped[int] = mapped_column(Integer)
    guard_after: Mapped[int] = mapped_column(Integer)
