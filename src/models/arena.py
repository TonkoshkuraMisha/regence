# --- FILE: src/models/arena.py ---
"""
Arenas - tournaments between people (task 17.2): run for a set time, players play game after game against those who are also
waiting;
points per game, a win streak doubles the points ("fire"). The rules are in src/services/arena.py.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, one_of

# Formats of a tournament between people (src/services/arena.py, arena_schedule.Slot.format).
ARENA_FORMATS = ("arena", "swiss", "match")
# The result of an arena game; "*" - a cancelled or uncounted game, NULL - the game is still in progress.
ARENA_GAME_RESULTS = ("1-0", "0-1", "1/2-1/2", "*")


class Arena(Base):
    """
    A tournament between people: a timed arena, a Swiss by rounds or a match of two conferences (two rounds, pairings by boards
    -
    src/services/conference_match_rules.py). Created by the schedule
    (src/services/arena_schedule.py) or as the next division of an overflowing arena (parent_id).
    """
    __tablename__ = "arenas"
    __table_args__ = (one_of("arenas", "format", ARENA_FORMATS),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # The schedule code (for example "blitz-3+2"), so as not to create the same arena twice; empty - a one-off arena.
    schedule_key: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    base_time_ms: Mapped[int] = mapped_column(Integer)
    increment_ms: Mapped[int] = mapped_column(Integer, default=0)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # arena - play while the time runs; swiss - a set number of rounds, pairings by points (src/services/arena.py); match -
    # a conference match: the host is conference, the guest is opponent_conference.
    format: Mapped[str] = mapped_column(String(16), default="arena", server_default="arena")
    rounds: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    current_round: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # The Swiss has finished (all rounds were played or there were not enough participants) - the moment of finishing.
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Divisions on overflow (33.2): the second and further ones are arenas with the parent_id of the first: the same time and
    # rules, their own table.
    division: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("arenas.id", ondelete="CASCADE"), nullable=True, index=True)
    # The conference whose schedule the arena runs by (33.4, src/services/arena_schedule.py); empty - a one-off arena.
    conference: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # A conference match: the guest conference (the host is conference); empty for other formats.
    opponent_conference: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArenaPlayer(Base):
    """
    An arena participant: points, number of games and wins, the current win streak, and also the rating and conference at the
    moment of joining -
    they do not change until the end of the arena.
    """
    __tablename__ = "arena_players"
    __table_args__ = (UniqueConstraint("arena_id", "user_id", name="uq_arena_player"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    arena_id: Mapped[int] = mapped_column(ForeignKey("arenas.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    games: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    wins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Consecutive wins: starting from arena.FIRE_AFTER (two) the next game brings twice as many points.
    streak: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # The rating in the arena's category at the moment of joining - for pairings and the table.
    rating: Mapped[int] = mapped_column(Integer)
    # Swiss: bye rounds with an odd number of players (each gets at most one).
    byes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # The player's conference at the moment of joining (33.6): their points go to its standings; empty - no country is set in
    # the profile.
    conference: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # A conference match: the player's board within their side (from 1); empty - a reserve or the line-up is not announced yet.
    board: Mapped[int | None] = mapped_column(Integer, nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArenaReminder(Base):
    """A reminder about the arena start (33.4): the player pressed "remind" - shortly before the start a notification will
    arrive."""
    __tablename__ = "arena_reminders"
    __table_args__ = (UniqueConstraint("arena_id", "user_id", name="uq_arena_reminder"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    arena_id: Mapped[int] = mapped_column(ForeignKey("arenas.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # The moment the notification was sent; empty - not sent yet.
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArenaGame(Base):
    """
    An arena game: a reference to the game in games, who played which colour, the result and the points of the sides. While
    result is empty the game
    is in progress - the arena results wait for it.
    """
    __tablename__ = "arena_games"
    __table_args__ = (one_of("arena_games", "result", ARENA_GAME_RESULTS),)

    id: Mapped[int] = mapped_column(primary_key=True)
    arena_id: Mapped[int] = mapped_column(ForeignKey("arenas.id", ondelete="CASCADE"), index=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), unique=True)
    white_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    black_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    result: Mapped[str | None] = mapped_column(String(8), nullable=True)
    white_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    black_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # "Berserk" (33.3): the side took half the time without increment before its first move - a win gives an extra point.
    white_berserk: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    black_berserk: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # The Swiss round (0 for an arena).
    round: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArenaAward(Base):
    """
    A prize place in a finished arena or Swiss (task 33.5): the top three of the results table. Written by the scheduled task
    arena_awards (src/services/arena_awards.py) when the results are final; then from this record - a notification to
    the winner, cups in the profile and the "arena prize-winner" / "arena winner" achievements.
    """
    __tablename__ = "arena_awards"
    __table_args__ = (
        UniqueConstraint("arena_id", "user_id", name="uq_arena_award_player"),
        one_of("arena_awards", "place", ("1", "2", "3")),
    )

    arena_id: Mapped[int] = mapped_column(ForeignKey("arenas.id", ondelete="CASCADE"), primary_key=True)
    # The place in the results table: 1, 2 or 3 (as a string - the shared one_of helper for CHECK).
    place: Mapped[str] = mapped_column(String(1), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # The arena's time-control category (rating.classify_time_control): by it cups in the profile are split into bullet, blitz,
    # etc.
    category: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
