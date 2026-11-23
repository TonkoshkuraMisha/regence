# --- FILE: src/models/tournament.py ---
"""
Tournaments with historical masters (task 15.1). The rules are in src/services/tournament_rules.py, the tournament flow -
src/services/tournaments.py. A participant number (seat) is its seed: 1 is the strongest by rating at the start.
A participant is the tournament owner player, a historical bot, a workshop archetype or a player's personality (its name and
config
are copied into the tournament: deleting or editing the personality does not change a tournament already in progress). A master
of the past from the "Time
Machine" (src/services/bots/guests.py) is recorded as a personality with the key "guest:<id>" in bot_key.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, one_of

# The tournament format (src/services/tournaments.py, Format) and its state.
TOURNAMENT_FORMATS = ("round_robin", "knockout", "swiss")
TOURNAMENT_STATUSES = ("active", "finished")
# Who takes the seat: a player, a bot, a beginner archetype, a personality (one's own or a master of the past).
TOURNAMENT_PLAYER_KINDS = ("user", "bot", "archetype", "personality")
# A knockout match game (tournament_rules.Stage) and its result (tournament_rules.Result; "*" does not occur here).
TOURNAMENT_STAGES = ("main", "rematch", "armageddon")
TOURNAMENT_RESULTS = ("1-0", "0-1", "1/2-1/2")


class Tournament(Base):
    """
    A player's tournament with bots: the format (round-robin, knockout or Swiss), the time control and the status. The player's
    final
    place is stored in their row tournament_players.place.
    """
    __tablename__ = "tournaments"
    __table_args__ = (
        one_of("tournaments", "format", TOURNAMENT_FORMATS),
        one_of("tournaments", "status", TOURNAMENT_STATUSES),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # round_robin | knockout | swiss
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    # active | finished
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    base_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    increment_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The current round of a knockout tournament (in a round-robin all rounds are created at once).
    current_round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The player withdrew from the tournament (task A.3): their remaining games are losses, bots finish playing; a new
    # tournament can be started.
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # A career tournament (task 15.4): the key of a ladder stage (src/services/tournament_career.py); empty - one's own
    # tournament.
    career_stage: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # "Time Machine" (task 28.2): the key of a famous tournament from src/services/time_machine.py; empty - an ordinary
    # tournament.
    event_key: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)


class TournamentPlayer(Base):
    """
    A tournament participant under a seed number (seat): the player themselves or a bot. The bot's name and settings are copied
    into the tournament and do not
    depend on later edits.
    """
    __tablename__ = "tournament_players"
    __table_args__ = (
        UniqueConstraint("tournament_id", "seat", name="uq_tournament_players_seat"),
        one_of("tournament_players", "kind", TOURNAMENT_PLAYER_KINDS),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    seat: Mapped[int] = mapped_column(Integer, nullable=False)
    # user | bot | archetype | personality
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
                                                index=True)
    # The id of a historical bot ("morphy"), an archetype key ("archetype:rusher") or a master of the past ("guest:<id>").
    bot_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # A workshop personality - a copy of the name and config at the time the tournament was created.
    personality_name: Mapped[str | None] = mapped_column(String(30), nullable=True)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The rating at the start - the seeding is by it.
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    place: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A knockout tournament: the round (from 1) in which the participant was eliminated.
    eliminated_round: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TournamentGame(Base):
    """
    A tournament game: the round, participants by seed numbers and the result. The player's game is written by saving the
    played
    game, a bot-vs-bot game - by the simulation.
    """
    __tablename__ = "tournament_games"
    __table_args__ = (
        one_of("tournament_games", "stage", TOURNAMENT_STAGES),
        one_of("tournament_games", "result", TOURNAMENT_RESULTS),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    # The pairing number in the round (for a knockout tournament - the match number in the bracket).
    board: Mapped[int] = mapped_column(Integer, nullable=False)
    # main | rematch | armageddon (knockout; always main in a round-robin)
    stage: Mapped[str] = mapped_column(String(16), nullable=False, default="main")
    white_seat: Mapped[int] = mapped_column(Integer, nullable=False)
    black_seat: Mapped[int] = mapped_column(Integer, nullable=False)
    base_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    increment_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 1-0 | 0-1 | 1/2-1/2; empty - the game has not been played yet.
    result: Mapped[str | None] = mapped_column(String(8), nullable=True)
    game_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("games.id", ondelete="SET NULL"), nullable=True,
                                                index=True)
    # The game has been started: for bots - picked up by the worker (task 15.2), for the player - they pressed "Play"
    # themselves (task A.2).
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # A bot game was queued (task A.1): again - only if it was queued long ago and still not started.
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
