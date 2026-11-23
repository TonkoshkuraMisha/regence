"""
The opening repertoire (task 20.1): one's own lines for White or for Black. A repertoire is stored as a graph of positions: the
move
`move_uci` from the position `position` (EPD - four FEN fields, as in the openings table src/services/openings.py), so
transpositions converge into one position. The tree for the client is built by src/services/repertoire.py by a walk from
the initial position.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, one_of

# The repertoire colour.
REPERTOIRE_COLORS = ("white", "black")


class Repertoire(Base):
    """A player's repertoire: a name and the colour it is built for."""
    __tablename__ = "repertoires"
    __table_args__ = (one_of("repertoires", "color", REPERTOIRE_COLORS),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    color: Mapped[str] = mapped_column(String(5))  # white | black
    # Which starter repertoire it was created from (None - one's own from scratch): the client shows the intro text.
    starter: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RepertoireMove(Base):
    """
    A repertoire move is an edge of the position graph: from a position (EPD) a move is made. Transpositions come to the same
    position.
    """
    __tablename__ = "repertoire_moves"
    __table_args__ = (UniqueConstraint("repertoire_id", "position", "move_uci", name="uq_repertoire_move"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repertoire_id: Mapped[int] = mapped_column(ForeignKey("repertoires.id", ondelete="CASCADE"), index=True)
    position: Mapped[str] = mapped_column(String(100))
    move_uci: Mapped[str] = mapped_column(String(5))
    comment: Mapped[str] = mapped_column(String(300), default="", server_default="")


class RepertoireCard(Base):
    """
    A repetition card (task 20.2): a repertoire position where the player is to move - "find your move". The SM-2 schedule:
    ease, the interval in days, the number of correct answers in a row, the date of the next showing.
    """

    __tablename__ = "repertoire_cards"
    __table_args__ = (UniqueConstraint("repertoire_id", "position", name="uq_repertoire_card"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    repertoire_id: Mapped[int] = mapped_column(ForeignKey("repertoires.id", ondelete="CASCADE"), index=True)
    position: Mapped[str] = mapped_column(String(100))
    ease: Mapped[float] = mapped_column(Float, default=2.5, server_default="2.5")
    interval_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    repetitions: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lapses: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    first_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
