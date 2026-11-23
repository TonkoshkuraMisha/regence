# --- FILE: src/models/position.py ---
"""
The position index (task 16.1): move statistics from a position and the games that passed through the position. A position is a
Zobrist hash (python-chess, 64 bits; signed in the database to fit into BIGINT). The index depth is the first
position_index.MAX_PLIES plies of a game. Built by src/services/position_index.py.

The primary keys are natural (database audit 29.1, finding 1; migration c9a4e7d2f5b8): there is no surrogate id, nobody
used it, and the position index takes about two thirds of the database. The key (position_hash, ...) is also the index for
search by position.
"""

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class PositionStat(Base):
    """
    Statistics of one move from a position: how many games went through it and how they ended (White wins, draws,
    Black wins). The key is (position, move).
    """
    __tablename__ = "position_stats"

    position_hash: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    move_uci: Mapped[str] = mapped_column(String(5), primary_key=True)
    white_wins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    draws: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    black_wins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class PositionGame(Base):
    """
    A game that passed through a position: once per game, even if the position repeated (ply is the first ply at
    which it occurred). The key is (position, game).
    """
    __tablename__ = "position_games"

    position_hash: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), primary_key=True, index=True)
    ply: Mapped[int] = mapped_column(Integer)


class PositionLibraryGame(Base):
    """
    A library game that passed through a position (8b): examples under the position in the opening explorer. Library games do
    not enter the move statistics
    (position_stats) - many of them are in the champions archive too, and one game
    would be counted twice. The key is (position, library game); ply is the first ply at which the position occurred.
    """
    __tablename__ = "position_library_games"

    position_hash: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    library_game_id: Mapped[int] = mapped_column(ForeignKey("library_games.id", ondelete="CASCADE"), primary_key=True,
                                                 index=True)
    ply: Mapped[int] = mapped_column(Integer)
