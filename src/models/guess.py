"""
Positions of "Guess the master's move" (the guess_positions table). Filled by scripts/build_guess_positions.py by the rules of
src/services/guess_selection.py; answers are served and scored by src/services/guess.py.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class GuessPosition(Base):
    """
    "Guess the master's move" (task 14.3): a position from a master's game where the master's move is objectively found by
    calculation -
    the engine's best move with a margin or the only one that keeps the result (selection - src/services/guess_selection.py,
    the script scripts/build_guess_positions.py). Positions of one series (several player moves in a row) share series_id.
    """

    __tablename__ = "guess_positions"
    __table_args__ = (UniqueConstraint("game_id", "ply", name="uq_guess_game_ply"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    # The ply number in the game (0 - White's first move): the position is before this move.
    ply: Mapped[int] = mapped_column(Integer)
    fen: Mapped[str] = mapped_column(String(100))
    move_uci: Mapped[str] = mapped_column(String(5))
    # The evaluation of the best move and the gap to the second - from the point of view of the side to move, in centipawns.
    best_cp: Mapped[int] = mapped_column(Integer)
    gap_cp: Mapped[int] = mapped_column(Integer)
    # Up to three best engine moves with evaluations: [[uci, cp], ...] - the player's answer is scored by them without the
    # engine.
    lines: Mapped[list] = mapped_column(JSON)
    # A series: positions of one game in a row where each player move passes the selection.
    series_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    series_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Difficulty - a number on the puzzle rating scale. The initial value is computed at selection
    # (guess_selection.difficulty); then it changes by the answers of logged-in players (src/services/guess.answer).
    difficulty: Mapped[int] = mapped_column(Integer, index=True)
    # Theme codes of registry 13.0 (guess_selection.position_themes) - shown after the answer.
    themes: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    plays: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    solved: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
