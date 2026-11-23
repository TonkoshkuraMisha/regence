# --- FILE: src/models/game.py ---
"""
A game (the games table) - shared by all kinds of play: with a human, with a bot, the masters archive, a tournament simulation.

Who writes: the start of a game with a human - src/services/matchmaker.py; moves and clocks during play and the result -
src/services/game_state.py (the source of truth during a game is Redis, the state is copied here); a game with a bot
in full after it ends - src/api/bots.py (save-game); the archive - src/db/seed.py; bot-vs-bot games -
src/services/tournament_simulation.py (is_simulation).

Main fields: pgn - the move record; board_fen, turn, clocks and state_version - the state of a game in progress (it is restored
from them if it vanished from Redis); result and termination - the result and its reason; players' ratings at the start
and the change after the game; analysis_json - the saved engine review; positions_indexed - the game is already laid out into
the position index.
"""

import enum
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, one_of

# The game result (CHECK ck_games_result; the same set - game_engine.GAME_RESULTS, checked by tests/test_db_integrity.py).
# NULL - the game has not finished yet.
GAME_RESULTS = ("1-0", "0-1", "1/2-1/2", "*")


class GameStatus(str, enum.Enum):
    """
    The game status: PENDING - the default value (a game between people is created straight as IN_PROGRESS);
    IN_PROGRESS - in progress; COMPLETED - finished with a result; ABORTED - cancelled while fewer than two
    plies were made (by a player or because of a no-show on the first move), the rating does not change. ABORTED is also given
    to the stub record
    of a Swiss round when the game could not be started (src/services/arena.py).
    """
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class Game(Base):
    """One game of any kind. What is in which fields and who writes them - in the module description above."""
    __tablename__ = "games"
    __table_args__ = (one_of("games", "result", GAME_RESULTS),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # RESTRICT is a deliberate decision (database audit 29.1, finding 5): a player with games is not deleted, the account
    # is anonymised (src/services/account.py), and the games stay with the opponent and in statistics. The same for winner_id
    # and moves.
    white_player_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
                                                 index=True)
    black_player_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
                                                 index=True)

    pgn: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[GameStatus] = mapped_column(
        Enum(GameStatus, name="gamestatus"),
        default=GameStatus.PENDING,
        nullable=False,
        index=True,
    )

    base_time_ms: Mapped[int] = mapped_column(Integer, default=180000, server_default="180000", nullable=False)
    increment_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_rated: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    # "Hourglass" (handicap, 21.1): the time spent by the mover is added to the opponent (src/services/game_state.py).
    hourglass: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    state_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    turn: Mapped[str] = mapped_column(String(1), default="w", server_default="w", nullable=False)
    # The initial position of a game between people that did not start from the standard setup: a handicap (21.1) or Fischer
    # chess;
    # None - the standard setup. A game with a bot has its own position recorded in the SetUp/FEN headers of its PGN.
    initial_fen: Mapped[str | None] = mapped_column(String(100), nullable=True)
    board_fen: Mapped[str] = mapped_column(
        String,
        default="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        server_default="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        nullable=False,
    )

    # Clocks: the remaining time of the sides at the moment of the last move and the time of that move by the server clock
    # (milliseconds
    # of the Unix epoch). The remainder of the side that is thinking now = its value minus the time elapsed since last_move_at.
    white_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    black_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_move_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    result: Mapped[str | None] = mapped_column(String(10), nullable=True)
    termination: Mapped[str | None] = mapped_column(String(50), nullable=True)
    winner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
                                                  index=True)

    # Players' ratings in the game's category at its start and the change after it - the rating history is built from them
    # (GET /profile/{username}/rating-history). For a casual and a cancelled game between people the change is 0;
    # for archive games and games with bots outside tournaments the change fields are empty.
    white_initial_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    black_initial_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    white_rating_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    black_rating_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # The date ("YYYY.MM.DD", as in PGN), place and opening code: for archive games - from the PGN headers, for those played on
    # the
    # site - the end date, the site name and the code from the openings table (src/services/openings.py).
    pgn_date: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    site: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    eco: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)

    analysis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A summary of move telemetry per side (src/services/anticheat.telemetry_summary): rhythm, focus loss, premoves,
    # penalty. Written when the game is evaluated by anti-cheat or before the raw moves are deleted from moves after
    # RETENTION_DAYS
    # (src/services/telemetry_retention.py) - after that the game's moves remain only here.
    telemetry_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # The name of a personality from the opponent workshop: in the database the opponent is a shared bot user,
    # while the archive and PGN show the name the player gave it.
    personality_name: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # A bot-vs-bot game played by the server in a tournament (task 15.2): without a rating, not in the archive and the profile
    # statistics, opened by a link from the tournament.
    is_simulation: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    # The game is laid out into the position index (task 16.1, src/services/position_index.py) - it is not computed again.
    positions_indexed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    # A training game (rule 2 of Part II): the player used the mentor - advice or move checking.
    # Without a rating (games with bots are unrated anyway), marked in the archive.
    assisted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    # Blindfold play (task 19.5): tier 1-4 (own pieces visible -> vanish -> pawns only -> completely) and the number
    # of peeks; null - an ordinary game. Only unrated games.
    blindfold_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blindfold_peeks: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    white_player = relationship("User", foreign_keys=[white_player_id])
    black_player = relationship("User", foreign_keys=[black_player_id])
    moves = relationship("Move", cascade="all, delete-orphan")
