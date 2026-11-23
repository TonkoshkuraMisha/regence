# --- FILE: src/models/puzzle.py ---
"""
Puzzles (task 13.1). The source is the open lichess puzzle database (CC0), the sample - data/puzzles/. The move format is as in
the database: `moves[0]` is the opponent's move that creates the puzzle, then the solver's move and the reply alternate.
Themes are registry codes (src/services/themes.py) in a separate table, so that puzzles can be chosen by theme via an index.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, one_of

# Kinds of defence drills (src/services/defense_drills.py, KINDS).
DEFENSE_DRILL_KINDS = ("threat", "blunder")


class Puzzle(Base):
    """
    A puzzle: the position, the solution, the difficulty rating and the identifier in the source (a repeated load of the same
    puzzle
    is skipped).
    """
    __tablename__ = "puzzles"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_puzzles_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[str] = mapped_column(String(20), nullable=False)
    # The position before the opponent's move (moves[0]); the solver plays the side that moves after it.
    fen: Mapped[str] = mapped_column(String(100), nullable=False)
    moves: Mapped[str] = mapped_column(String(400), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    rating_deviation: Mapped[int] = mapped_column(Integer, nullable=False, default=75)
    popularity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    plays: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The source tags of the database - for re-tagging when the registry changes.
    source_tags: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # The tier (task 13.4): 1 - introduction, 2 - consolidation, 3 - in combination, 4 - master; computed on import from
    # the rating and the solution length (src/services/puzzle_import.stage_for).
    stage: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1", index=True)
    # The theme markup version (src/services/puzzle_import.TAG_VERSION): an old one - the puzzle is re-tagged on import.
    tag_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    themes: Mapped[list[PuzzleTheme]] = relationship(
        back_populates="puzzle", cascade="all, delete-orphan", lazy="selectin",
    )

    @property
    def theme_codes(self) -> list[str]:
        return [t.theme for t in self.themes]


class PuzzleTheme(Base):
    """
    A puzzle theme - a registry code from src/services/themes.py. A separate row for each theme, so that puzzles by theme are
    chosen
    by an index.
    """
    __tablename__ = "puzzle_themes"

    puzzle_id: Mapped[int] = mapped_column(ForeignKey("puzzles.id", ondelete="CASCADE"), primary_key=True)
    theme: Mapped[str] = mapped_column(String(40), primary_key=True, index=True)

    puzzle: Mapped[Puzzle] = relationship(back_populates="themes")


class ThemeProgress(Base):
    """A player's progress by theme (task 13.4): the tier, the latest results on it ('1' - clean, '0' - not)."""
    __tablename__ = "theme_progress"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    theme: Mapped[str] = mapped_column(String(40), primary_key=True)
    stage: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    recent: Mapped[str] = mapped_column(String(10), nullable=False, default="", server_default="")
    solved: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    mastered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class PersonalPuzzle(Base):
    """
    A puzzle from a player's game (task 13.5): the position before their mistake and the only strong move. Repetition with
    intervals: an unsolved one returns after 1, 3, 7, 21 days until it is solved twice in a row (then done).
    The numbers are personal_puzzles.INTERVALS_DAYS and SOLVES_TO_MASTER; the puzzles are created by the background game review
    (src/worker/tasks.py → personal_puzzles.extract_for_game / extract_for_imported).
    """
    __tablename__ = "personal_puzzles"
    __table_args__ = (
        UniqueConstraint("user_id", "game_id", "ply", name="uq_personal_puzzles_move"),
        UniqueConstraint("user_id", "imported_game_id", "ply", name="uq_personal_puzzles_imported_move"),
        CheckConstraint("(game_id IS NULL) <> (imported_game_id IS NULL)", name="ck_personal_puzzles_one_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # A game on the site or a game from another site (task 24.1) - exactly one of the two.
    game_id: Mapped[int | None] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=True, index=True)
    imported_game_id: Mapped[int | None] = mapped_column(
        ForeignKey("imported_games.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    # The ply of the mistake (1 - the first move of the game) and the position before it; the previous move is for
    # highlighting.
    ply: Mapped[int] = mapped_column(Integer, nullable=False)
    fen: Mapped[str] = mapped_column(String(100), nullable=False)
    previous_move: Mapped[str | None] = mapped_column(String(5), nullable=True)
    solution: Mapped[str] = mapped_column(String(5), nullable=False)
    played: Mapped[str] = mapped_column(String(5), nullable=False)
    cp_loss: Mapped[int] = mapped_column(Integer, nullable=False)
    # Registry theme codes separated by commas; read and write via personal_puzzles.split_themes / join_themes.
    themes: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    interval_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    solved_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DefenseDrill(Base):
    """
    A defence drill (task 13.6, src/services/defense_drills.py): "What does the opponent threaten?" (kind=threat) and "Don't
    blunder" (kind=blunder). The position has the defender to move; the threat and the correct moves are not sent to the
    client.
    """
    __tablename__ = "defense_drills"
    __table_args__ = (
        UniqueConstraint("kind", "source", "source_id", name="uq_defense_drills_source"),
        Index("ix_defense_drills_kind_stage", "kind", "stage"),
        one_of("defense_drills", "kind", DEFENSE_DRILL_KINDS),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[str] = mapped_column(String(20), nullable=False)
    fen: Mapped[str] = mapped_column(String(100), nullable=False)
    # threat: the opponent's move that threatens (if it were their move); blunder - no.
    threat: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # blunder: three moves to choose from and the refutations of the losing ones ("move:reply" separated by a space).
    choices: Mapped[str] = mapped_column(String(20), nullable=False, default="", server_default="")
    refutations: Mapped[str] = mapped_column(String(30), nullable=False, default="", server_default="")
    good_moves: Mapped[str] = mapped_column(String(30), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[int] = mapped_column(Integer, nullable=False)
    # The tactic themes behind the threat or the blunder (from the original puzzle) - an explanation after the answer.
    motifs: Mapped[str] = mapped_column(String(300), nullable=False, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DrillRecord(Base):
    """A personal record of the one-minute run in the generator drills (task 13.7): the combination "kind.piece.level"."""
    __tablename__ = "drill_records"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    combo: Mapped[str] = mapped_column(String(30), primary_key=True)
    best: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now(), nullable=False)


class PuzzleAttempt(Base):
    """
    A player's attempt to solve a puzzle and its result. The solver rating, theme progress and the skill map are computed from
    attempts.
    """
    __tablename__ = "puzzle_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    puzzle_id: Mapped[int] = mapped_column(ForeignKey("puzzles.id", ondelete="CASCADE"), nullable=False, index=True)
    solved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hints_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating_before: Mapped[int] = mapped_column(Integer, nullable=False)
    rating_after: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class PuzzleTimedScore(Base):
    """
    A player's best score in a timed run for a week (the leaderboard, task 26.1): a row per player, run length
    (3 or 5 minutes) and week - the UTC Monday. Written by puzzle_leaders.record_week at the end of a run, the score only
    grows.
    """
    __tablename__ = "puzzle_timed_scores"
    __table_args__ = (UniqueConstraint("user_id", "minutes", "week", name="uq_puzzle_timed_scores_week"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)

