# --- FILE: src/models/move.py ---
"""
A game move with telemetry (the moves table): time per move by the server clock, window focus loss, premove, network
delay. Written when a game between people finishes from the move log in Redis (src/services/game_state.finish_game) and
read by anti-cheat (src/services/anticheat.py). The moves for viewing themselves are taken from games.pgn, not from here.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class Move(Base):
    """
    One move of a game between people with telemetry for anti-cheat. The rows appear all at once when the game finishes; games
    with bots, archive games and simulations have no records in this table.
    """
    __tablename__ = "moves"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="RESTRICT"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)

    # The game's move number (fullmove, as in the record "12. Nf3"): for White's move and Black's reply it is the same. This is
    # not the
    # ply number - it is written by src/api/websockets._record_applied_move from move_data["fullmove_number"].
    move_number: Mapped[int] = mapped_column(Integer)

    # --- Move ---
    notation: Mapped[str] = mapped_column(String(10))  # Universal UCI (e.g., e2e4)
    san: Mapped[str | None] = mapped_column(String(10), nullable=True)  # For nice display (e.g., Nf3)
    fen_after: Mapped[str | None] = mapped_column(String, nullable=True)  # The board state AFTER the move
    # ------------------

    # --- Telemetry ---
    # The time per move by the server clock (from the previous move to the arrival of this one) - not what the client reported.
    time_taken_ms: Mapped[int] = mapped_column(Integer)
    # The window lost focus before the move - by the client's word (forgeable, so it does not penalise by itself).
    window_blurred_before_move: Mapped[bool] = mapped_column(Boolean, default=False)
    # Premove: a client flag accepted by the server only if the move arrived almost instantly (anticheat.trusted_premove).
    is_premove: Mapped[bool] = mapped_column(Boolean, default=False)
    # The server time minus the thinking time reported by the client (not below zero): an estimate of network delay.
    network_lag_ms: Mapped[int] = mapped_column(Integer, default=0)

    # The moment the row was inserted into the database, i.e. of the game finishing, not of the move itself.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
