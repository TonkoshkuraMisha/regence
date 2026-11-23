# --- FILE: src/schemas/analysis.py ---
"""
The format of analysis and mentor requests and responses (src/api/analysis.py): position evaluation, a full game review with
move classification and the accuracy of the sides, advice, a tiered hint, move check, the game summary.

There are no texts for the player here: the mentor's comment is a list of sentences {template key, parameters} from which
the client assembles a phrase in its language (the coach catalogue), plus arrows and square highlights for the board.
"""

from pydantic import BaseModel, Field


class PositionAnalysisRequest(BaseModel):
    """A position evaluation request (POST /analysis/position): the position is given by moves from the initial setup or from a
    FEN."""
    moves: list[str] = Field(default_factory=list, max_length=1000, description="A list of moves in SAN or UCI format")
    start_fen: str | None = Field(
        default=None, max_length=120,
        description="The initial position (FEN) from which the moves were made; the standard setup by default",
    )


class CoachSentence(BaseModel):
    """A mentor sentence: the key of the coach catalogue template on the client and parameters (pieces - in figurine
    notation)."""
    key: str
    params: dict[str, str | int] = Field(default_factory=dict)


class CoachArrow(BaseModel):
    """An arrow on the board: best - the best move, threat - the opponent's threat, idea - the tactic of the best/played
    move."""
    from_: str = Field(alias="from")
    to: str
    kind: str

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class CoachHighlight(BaseModel):
    """A square highlight on the board; kind is the highlight kind by which the client chooses the colour."""
    square: str
    kind: str


class CoachComment(BaseModel):
    """The mentor's comment on a move or position: sentences (template keys), arrows and square highlights."""
    comment: list[CoachSentence]
    arrows: list[CoachArrow] = Field(default_factory=list)
    highlights: list[CoachHighlight] = Field(default_factory=list)


class MoveEvaluationItem(BaseModel):
    """
    One move in a game review: the number and side, the move record, the evaluation of the position after it, the engine's best
    move, the loss in
    centipawns, the move class and the mentor's comment. The class and the sign are computed by
    analysis_service.classify_move_by_cp_loss: Best "!" (a loss up to 10 centipawns or the engine's first line), Good
    (up to 45), Inaccuracy "?!" (up to 95), Mistake "?" (up to 199), Blunder "??" (from 200). eval_display is the evaluation
    from
    White's point of view as a string ("+1.4", "M3").
    """
    ply: int
    move_number: int
    color: str
    san: str
    uci: str
    eval_cp: int
    eval_display: str
    mate: int | None = None
    best_move_uci: str | None = None
    cp_loss: int
    classification: str
    symbol: str
    coach: CoachComment | None = None


class SideSummaryStats(BaseModel):
    """
    The review summary for one side: the accuracy in percent (the mean over moves, the formula -
    analysis_service.calculate_move_accuracy), the number of moves of each class and the average loss in centipawns.
    """
    accuracy: float
    best: int
    good: int
    inaccuracies: int
    mistakes: int
    blunders: int
    avg_cp_loss: float


class AdviceRequest(BaseModel):
    """A mentor advice request (POST /analysis/advice)."""
    fen: str = Field(..., max_length=100, description="The position for which advice is needed (the player's side is to move)")


class AdviceResponse(CoachComment):
    """Mentor advice: a comment with arrows, the best move and the position evaluation."""
    fen: str
    best_move_uci: str | None = None
    eval_cp: int | None = Field(default=None, description="Evaluation for White; None - the engine is unavailable")


class HintRequest(BaseModel):
    fen: str = Field(..., max_length=100)
    step: int = Field(1, ge=1, le=3, description="Tier: 1 - a nudge, 2 - the piece, 3 - the move")


class HintResponse(BaseModel):
    """A hint of one tier (POST /analysis/hint); best_move_uci is filled only on the last tier."""
    fen: str
    step: int
    final: bool = Field(description="The last tier: the move is shown, there is nothing more to hint")
    best_move_uci: str | None = None
    comment: list[CoachSentence]
    arrows: list[CoachArrow] = []
    highlights: list[CoachHighlight] = []


class DisputeRequest(BaseModel):
    """"Disagree" with a mentor warning (POST /analysis/dispute): the position, the move and the loss shown."""
    fen: str = Field(..., max_length=100)
    move: str = Field(..., min_length=4, max_length=5)
    cp_loss: int | None = Field(default=None, ge=0, le=20000)


class MoveCheckRequest(BaseModel):
    """A move check request in a game with the mentor (POST /analysis/check-move)."""
    fen: str = Field(..., max_length=100, description="The position before the player's move")
    move: str = Field(..., min_length=4, max_length=5, description="The player's move in UCI")


class MoveCheckResponse(BaseModel):
    """A move check. available=False - there is no engine, the check was not done (the other fields are empty)."""
    available: bool
    cp_loss: int | None = None
    classification: str | None = None
    symbol: str | None = None
    eval_before: int | None = Field(default=None, description="The evaluation before the move from the mover's point of view")
    eval_after: int | None = Field(default=None, description="The evaluation after the move from the mover's point of view")
    best_move_uci: str | None = None
    reply_uci: str | None = None
    missed_tactic: bool = False
    coach: CoachComment | None = None


class KeyMoments(BaseModel):
    """A side's key moments in the game summary: the plies of its best and worst move (None - nothing to single out)."""
    best_ply: int | None = None
    worst_ply: int | None = None


class GameSummary(BaseModel):
    """The game summary (task 11.5), see src/services/game_summary.py."""
    kind: str = Field(description="seesaw | decisive_blunder | domination | missed_win | balanced | gradual")
    turning_point_ply: int | None = None
    lead_changes: int
    equal_share: float
    white: KeyMoments
    black: KeyMoments


class FullGameAnalysisResponse(BaseModel):
    """
    A full game review. Stored in games.analysis_json (for imported ones - imported_games.analysis_json);
    format_version is analysis_service.ANALYSIS_FORMAT_VERSION: a review of another version is considered outdated and
    recomputed. summary is not stored in the database - it is computed on every response (src/services/game_summary.py).
    """
    game_id: int
    format_version: int
    engine: str
    white: SideSummaryStats
    black: SideSummaryStats
    moves: list[MoveEvaluationItem]
    summary: GameSummary | None = None
