# --- FILE: src/services/bots/personality.py ---
"""
A parametric opponent model: the player sets a personality with sliders, the server builds a style and a strength from them.

An honest account of how it works: moves are evaluated by the engine from the pool (up to 8 MultiPV lines) or by the static
analyser if
there is no engine. Sliders and piece weights do NOT change the engine evaluation — they give bonuses to candidates inside the
blunder_guard_cp window
(rules in src/services/bots/style.py). This is not "its own engine" but a choice among good moves by the persona's taste.

Strength: the UCI_Elo limit weakens play only starting from STOCKFISH_MIN_ELO (1320). Below it the engine works at this
minimum, and weakness is added by controlled errors: with a share along the ERROR_RATE_CURVE curve (0.57 at 300 → 0 at 1500)
a weaker line or a random move is chosen. The search depth and time (no more than MAX_SEARCH_DEPTH half-moves and
MAX_SEARCH_TIME_S seconds) are set by the server from target_elo; the client does not pass them.

Data: favourite openings and opening-character lines come from the open openings table (src/services/openings.py).
BotPersonalityConfig is built by archetypes.py, masters.py, guests.py and the workshop API (src/api/bots.py); PersonalityBot
is created by the bot routes, tournament simulation and self-play (selfplay.py).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from functools import cache
from typing import Literal

import chess
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.errors import validation_error
from src.services import openings
from src.services.bots.base import BookEntry, HistoricalBot, bot_comment
from src.services.bots.style import (
    ALWAYS,
    CAPTURE,
    CASTLING,
    CENTER_SQUARES,
    CHECK,
    EXTENDED_CENTER,
    FROM_BACK_RANK,
    MINOR_PIECES,
    NEAR_ENEMY_KING,
    QUIET,
    SACRIFICE,
    STANDARD_VALUES,
    Cond,
    MoveContext,
    Rule,
    Style,
    by_move,
    mobility_count,
    pawn_structure_delta,
    piece,
    prophylaxis,
    to,
)

# Bounds of the target rating (target_elo) of a workshop opponent.
MIN_TARGET_ELO = 300
# Search parameters (level, depth, time) are computed from 600: below that the strength is set only by the error share (task
# 21.4),
# so opponents of 600+ after the range extension play as before.
SEARCH_FLOOR_ELO = 600
MAX_TARGET_ELO = 2800
# The minimum UCI_Elo the engine accepts (below it the pool raises it itself): weaker bots play with errors, not options.
STOCKFISH_MIN_ELO = 1320
# Cap of depth (half-moves) and time (s) of analysing one move: the server keeps the load on the engine pool in check.
MAX_SEARCH_DEPTH = 8
MAX_SEARCH_TIME_S = 0.5
# Probability of a controlled error by the target rating — a correction curve from the 14.11 calibration (log
# 2026-11-13_asymmetric_window.log), not a straight line: the measured strength falls non-linearly with the error share (0.05 →
# 1398,
# 0.15 → 1251, 0.29 → 737, 0.43 → 471), and a linear share made targets 1100-1250 stronger and 700-900 weaker than declared.
# Above 1320 Stockfish at the minimum UCI_Elo with the style window plays about 1480, so errors fade out towards 1500.
# Linear between the points; after an edit — recalibration (scripts/calibrate_bots.py --only ...).
# Refinement from the second run (2026-11-14_weak_curve.log): two points per weak bot give the error share
# at which it plays at the declared strength — almost a straight line 0.355 (700) → 0.10 (1250).
# Third run (2026-11-14_weak_rounds8.log, 8 rounds, +-75...130): the previous curve gave +65...+85 across the whole lower
# part and +171 for "Rusher". The "share → strength" points of this run (0.027 → 1484, 0.10 → 1318, 0.175 → 1165,
# 0.265 → 982, 0.355 → 871; below — the 0.43 → 471 section of the first run) were interpolated back into targets.
# Fourth run (2026-11-14_weak_curve_3.log) with this point-by-point curve overshot the middle: 0.331 → 769,
# 0.207 → 994, 0.133 → 1057 (-106...-193), the edges hit the targets (0.387 → 728, 0.064 → 1390). Point-by-point fitting chases
# noise (+-80...130 per point), so now it is a straight line weighted by the error, over all 11 points of the three runs:
# strength ~ 1501 − 2091 × share (residuals within the error). Inverse: 0.43 at 600 → 0 at 1500.
# Below 600 (task 21.4) — the same line: 300 ↔ 0.57.
ERROR_RATE_CURVE: tuple[tuple[int, float], ...] = ((300, 0.57), (600, 0.43), (1500, 0.0))
# The largest error share — at the weakest target (MIN_TARGET_ELO).
MAX_ERROR_RATE = ERROR_RATE_CURVE[0][1]
# Share of gross blunders (a random legal move) among controlled errors; the rest are a move from the worse half of the lines.
BLUNDER_SHARE = 1 / 3
# Random spread of candidate evaluations, cp per unit of the randomness slider: 100 → +-40 cp between equal moves.
JITTER_CP_PER_RANDOMNESS = 0.4
# Attitude to draws (task 21.4): "equality" — the best move's evaluation within +-EQUAL_CP cp (0.8 pawn); the correction
# to piece trades is TRADE_CP_PER_ATTITUDE cp per unit of the draw_attitude slider (+-40 cp at +-100).
EQUAL_CP = 80
TRADE_CP_PER_ATTITUDE = 0.4



# How many favourite openings can be chosen per colour.
MAX_FAVORITE_OPENINGS = 3
# Beginner habits (task 21.4) and opening characters: codes, texts — on the client (workshop.habits / openingStyles).
HABITS = ("hangs_pieces", "early_queen", "pawn_grabber", "knight_lover", "no_castling", "trades_all")
OPENING_STYLES = ("normal", "trapper", "trap_victim", "gambit", "early_queen", "drawish", "capture_lover", "offbeat")
Habit = Literal["hangs_pieces", "early_queen", "pawn_grabber", "knight_lover", "no_castling", "trades_all"]
OpeningStyle = Literal["normal", "trapper", "trap_victim", "gambit", "early_queen", "drawish", "capture_lover",
                       "offbeat"]


class PieceValues(BaseModel):
    """How a persona values pieces (in pawns). Affects the choice of trades, not the engine evaluation."""

    model_config = ConfigDict(extra="forbid")

    pawn: float = Field(1.0, ge=0.5, le=1.5)
    knight: float = Field(3.0, ge=2.0, le=4.5)
    bishop: float = Field(3.0, ge=2.0, le=4.5)
    rook: float = Field(5.0, ge=3.5, le=6.5)
    queen: float = Field(9.0, ge=7.0, le=11.0)

    def of(self, piece_type: int | None) -> float:
        """Piece value in pawns; 0 — for the king, an empty square and None."""
        return {
            chess.PAWN: self.pawn, chess.KNIGHT: self.knight, chess.BISHOP: self.bishop,
            chess.ROOK: self.rook, chess.QUEEN: self.queen,
        }.get(piece_type or 0, 0.0)

    def is_standard(self) -> bool:
        """All values match the standard scale STANDARD_VALUES (the "taste for pieces" rule is not needed)."""
        return all(self.of(pt) == value for pt, value in STANDARD_VALUES.items())


class BotPersonalityConfig(BaseModel):
    """
    Opponent personality. Sliders 0..200: 100 — the usual weight of a feature, 0 — the feature is ignored,
    200 — doubled. aggression: +100 — checks, sacrifices, play against the king; -100 — prophylaxis and quiet moves.
    randomness 0..100 — random spread of evaluations (JITTER_CP_PER_RANDOMNESS); blunder_guard_cp — the width of the move
    selection window; target_elo — the target strength (see strength_for). The other fields are favourite openings, habits,
    opening character,
    attitude to draws and passed pawns; the meaning of each is in build_style and PersonalityBot.
    """

    model_config = ConfigDict(extra="forbid")

    aggression: int = Field(0, ge=-100, le=100)
    center_control: int = Field(100, ge=0, le=200)
    mobility: int = Field(100, ge=0, le=200)
    king_safety: int = Field(100, ge=0, le=200)
    pawn_structure: int = Field(100, ge=0, le=200)
    piece_values: PieceValues = Field(default_factory=PieceValues)
    randomness: int = Field(20, ge=0, le=100)
    blunder_guard_cp: int = Field(120, ge=0, le=400)
    target_elo: int = Field(1500, ge=MIN_TARGET_ELO, le=MAX_TARGET_ELO)
    # Favourite openings (task 21.2): positions (EPD) of entries of the open openings table, up to three per colour.
    openings_white: list[str] = Field(default_factory=list, max_length=MAX_FAVORITE_OPENINGS)
    openings_black: list[str] = Field(default_factory=list, max_length=MAX_FAVORITE_OPENINGS)
    # Task 21.4: habits (beginner weaknesses), opening character, attitude to draws (-100 — never agrees,
    # +100 — gladly) and passed pawns (100 — as for everyone; separate from the pawn structure).
    habits: list[Habit] = Field(default_factory=list, max_length=3)
    opening_style: OpeningStyle = "normal"
    draw_attitude: int = Field(0, ge=-100, le=100)
    passed_pawns: int = Field(100, ge=0, le=200)

    @field_validator("openings_white", "openings_black")
    @classmethod
    def _known_openings(cls, value: list[str]) -> list[str]:
        """Favourite openings — only positions from the openings table (otherwise bot_opening_unknown); repeats are removed."""
        table = openings.lines()
        unique = list(dict.fromkeys(value))
        if any(epd not in table or not table[epd].moves for epd in unique):
            raise validation_error("bot_opening_unknown")
        return unique


# --- Strength ----------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Strength:
    """Search and error parameters for a target rating (see strength_for)."""

    uci_elo: int
    depth: int
    time_limit: float
    error_rate: float


def _error_rate(elo: int) -> float:
    """Share of controlled errors for a rating: piecewise-linear interpolation along ERROR_RATE_CURVE."""
    for (lo_elo, lo_rate), (hi_elo, hi_rate) in zip(ERROR_RATE_CURVE, ERROR_RATE_CURVE[1:], strict=False):
        if elo <= hi_elo:
            share = (max(elo, lo_elo) - lo_elo) / (hi_elo - lo_elo)
            return lo_rate + (hi_rate - lo_rate) * share
    return 0.0


def strength_for(target_elo: int) -> Strength:
    """
    Parameters by target rating: uci_elo (not below STOCKFISH_MIN_ELO), search depth and time (growing from
    SEARCH_FLOOR_ELO to MAX_TARGET_ELO within the caps), error share. The client does not set these parameters.
    """
    elo = max(MIN_TARGET_ELO, min(MAX_TARGET_ELO, target_elo))
    t = (max(elo, SEARCH_FLOOR_ELO) - SEARCH_FLOOR_ELO) / (MAX_TARGET_ELO - SEARCH_FLOOR_ELO)
    error_rate = _error_rate(elo)
    return Strength(
        uci_elo=max(STOCKFISH_MIN_ELO, elo),
        depth=min(MAX_SEARCH_DEPTH, round(4 + 4 * t)),
        time_limit=min(MAX_SEARCH_TIME_S, round(0.15 + 0.35 * t, 3)),
        error_rate=round(error_rate, 4),
    )


# --- Move features for the sliders -------------------------------------------------------------

def _queens_on_board(c: MoveContext) -> bool:
    """Both sides have queens (while they are on the board, it is dangerous for the king to leave cover)."""
    return bool(c.board.pieces(chess.QUEEN, chess.WHITE)) and bool(c.board.pieces(chess.QUEEN, chess.BLACK))


def _shelter_pawn_push(c: MoveContext) -> bool:
    """A pawn move from the king's shelter, for a king standing on a flank of the first rank."""
    if c.piece is None or c.piece.piece_type != chess.PAWN:
        return False
    king = c.board.king(c.us)
    if king is None or chess.square_rank(king) != (0 if c.us == chess.WHITE else 7):
        return False
    king_file = chess.square_file(king)
    if king_file in (3, 4):
        return False
    return abs(chess.square_file(c.move.from_square) - king_file) <= 1


# Conditions for the king safety rules.
QUEENS_ON = Cond(_queens_on_board)
SHELTER_PAWN_PUSH = Cond(_shelter_pawn_push)


def _mobility_gain(c: MoveContext) -> float:
    """Increase in the number of own moves (from -20 to +20)."""
    gain = mobility_count(c.board_after, c.us) - mobility_count(c.board, c.us)
    return float(max(-20, min(20, gain)))


def _material_perception(values: PieceValues):
    """Bonus function for the "taste for pieces" rule: the deviation of the persona's values from the standard scale, in cp."""

    def bonus(c: MoveContext) -> float:
        """
        Bonus for the persona's attitude to pieces: capturing a piece it values above the usual is more attractive, and
        putting its own "expensive" piece en prise is less attractive.
        """
        total = 0.0
        if c.captured_piece_type is not None:
            total += 100.0 * (values.of(c.captured_piece_type) - STANDARD_VALUES[c.captured_piece_type])
        if c.piece is not None and c.piece.piece_type != chess.KING and c.destination_attacked:
            total -= 100.0 * (values.of(c.piece.piece_type) - STANDARD_VALUES[c.piece.piece_type])
        return total

    return bonus


def _scaled(weight: float, feature):
    """Bonus function: a feature feature(ctx) multiplied by the slider weight."""
    return lambda c: weight * feature(c)


def build_style(config: BotPersonalityConfig) -> Style:
    """Style rules from the sliders; features with zero weight are not computed at all. The move remark is from the heaviest
    feature."""
    rules: list[Rule] = []
    a = config.aggression / 100.0
    if a > 0:
        rules += [
            Rule(CHECK, 40.0 * a, "personality.check"),
            Rule(SACRIFICE, 45.0 * a, "personality.sacrifice"),
            Rule(CAPTURE & ~SACRIFICE, 12.0 * a, "personality.openByTrade"),
            Rule(NEAR_ENEMY_KING & ~piece(chess.KING), 15.0 * a, "personality.kingHunt"),
        ]
    elif a < 0:
        calm = -a
        rules += [
            Rule(QUIET, _scaled(calm, prophylaxis), "personality.prophylaxis"),
            Rule(CHECK | CAPTURE, -10.0 * calm),
        ]

    center = config.center_control / 100.0
    if center:
        rules += [
            Rule(to(CENTER_SQUARES), 22.0 * center, "personality.center"),
            Rule(to(EXTENDED_CENTER) & ~to(CENTER_SQUARES), 10.0 * center, "personality.centerSpace"),
        ]

    mobility = config.mobility / 100.0
    if mobility:
        rules += [
            Rule(
                piece(*MINOR_PIECES) & by_move(15) & FROM_BACK_RANK, 25.0 * mobility,
                "personality.develop",
            ),
            Rule(ALWAYS, _scaled(1.5 * mobility, _mobility_gain), "personality.activate"),
        ]

    king = config.king_safety / 100.0
    if king:
        rules += [
            Rule(CASTLING, 40.0 * king, "personality.castle"),
            Rule(piece(chess.KING) & ~CASTLING & QUEENS_ON, -25.0 * king),
            Rule(SHELTER_PAWN_PUSH & QUEENS_ON, -15.0 * king),
        ]

    pawns = config.pawn_structure / 100.0
    if pawns:
        rules.append(Rule(ALWAYS, _scaled(pawns, pawn_structure_delta), "personality.pawns"))

    if not config.piece_values.is_standard():
        rules.append(Rule(ALWAYS, _material_perception(config.piece_values), "personality.trade"))

    passed = (config.passed_pawns - 100) / 100.0
    if passed:
        rules.append(Rule(PASSED_PAWN_PUSH, 35.0 * passed, "personality.passedPawn" if passed > 0 else None))

    rules += _habit_rules(config)
    return Style("personality", *rules, note_by_weight=True)


def _passed_pawn_push(c: MoveContext) -> bool:
    """A pawn move after which it is passed: ahead on its own and adjacent files there are no opponent pawns."""
    if c.piece is None or c.piece.piece_type != chess.PAWN:
        return False
    square = c.move.to_square
    file, rank = chess.square_file(square), chess.square_rank(square)
    ahead = range(rank + 1, 8) if c.us == chess.WHITE else range(0, rank)
    for enemy in c.board_after.pieces(chess.PAWN, not c.us):
        if abs(chess.square_file(enemy) - file) <= 1 and chess.square_rank(enemy) in ahead:
            return False
    return True


def _captures(*types: int) -> Cond:
    """The move captures a piece of one of the types types."""
    return Cond(lambda c: c.captured_piece_type in types)


PASSED_PAWN_PUSH = Cond(_passed_pawn_push)
# A piece (not a pawn or a king) goes en prise without a capture — the "hanging pieces" habit.
HANGING = ~piece(chess.PAWN, chess.KING) & Cond(lambda c: c.destination_attacked) & ~CAPTURE


def _habit_rules(config: BotPersonalityConfig) -> list[Rule]:
    """Beginner habits and opening character (task 21.4) — bonuses in centipawns on top of the engine evaluation."""
    rules: list[Rule] = []
    habits = set(config.habits)
    style = config.opening_style
    if "hangs_pieces" in habits:
        rules.append(Rule(HANGING, 70.0, "personality.careless"))
    if "early_queen" in habits or style == "early_queen":
        rules.append(Rule(piece(chess.QUEEN) & by_move(10), 80.0, "personality.earlyQueen"))
    if "pawn_grabber" in habits:
        rules.append(Rule(_captures(chess.PAWN), 90.0, "personality.pawnGrab"))
    if "knight_lover" in habits:
        rules += [Rule(piece(chess.KNIGHT), 45.0, "personality.knights"),
                  Rule(piece(chess.BISHOP, chess.ROOK, chess.QUEEN) & ~CAPTURE, -15.0)]
    if "no_castling" in habits:
        rules.append(Rule(CASTLING, -250.0))
    if "trades_all" in habits:
        rules.append(Rule(_captures(chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN), 80.0, "personality.trade"))
    if style == "capture_lover":
        rules.append(Rule(CAPTURE & by_move(15), 50.0, "personality.trade"))
    return rules


def _style_match(style: str, line: openings.OpeningLine) -> bool:
    """The line suits a character played for both colours: gambit — gambits (except declined ones), drawish — trading lines."""
    if style == "gambit":
        return "Gambit" in line.name and "Declined" not in line.name
    return style == "drawish" and "Exchange Variation" in line.name


@cache  # the openings table does not change within a process
def style_lines(style: str) -> tuple[tuple[chess.Color | None, tuple[str, ...], str], ...]:
    """
    Openings table lines for an opening character: (which colour to play them as — None for both, moves, name).
    Traps are entries with "Trap" in the name: the one setting the trap is the side of the line's last move, the one falling
    into it is the other.
    """
    found: list[tuple[chess.Color | None, tuple[str, ...], str]] = []
    for line in openings.lines().values():
        if not line.moves:
            continue
        springer = chess.WHITE if len(line.moves) % 2 else chess.BLACK
        if style in ("trapper", "trap_victim") and "Trap" in line.name:
            found.append((springer if style == "trapper" else not springer, line.moves, line.name))
        elif style == "offbeat" and line.eco in ("A00", "B00"):
            # An unusual first move for White (A00) and an unusual reply for Black to 1.e4 (B00): B00 lines start with
            # the usual 1.e4, so White cannot play them.
            found.append((chess.WHITE if line.eco == "A00" else chess.BLACK, line.moves, line.name))
        elif _style_match(style, line):
            found.append((None, line.moves, line.name))
    return tuple(found)


def accepts_draw(config: BotPersonalityConfig, score_cp: int) -> bool:
    """
    Reply to a draw offer (task 21.4). score_cp is the evaluation of the position for the bot. An ordinary opponent agrees in
    an equal or worse position (up to +0.3), a peaceable one — even with an advantage of up to +2, an uncompromising one (-100)
    — never.
    """
    if config.draw_attitude <= -100:
        return False
    return score_cp <= 30 + round(1.7 * config.draw_attitude)


# Before this move (the game's move number) the bot rejects a draw as premature.
DRAW_OFFER_MIN_MOVE = 10


def draw_answer(config: BotPersonalityConfig, score_cp: int | None, move_number: int) -> tuple[bool, dict]:
    """Reply and remark: in the opening (before move 10) — "too early", later — by the evaluation and the attitude to draws."""
    if move_number < DRAW_OFFER_MIN_MOVE or score_cp is None:
        return False, bot_comment("personality.drawTooEarly")
    accepted = accepts_draw(config, score_cp)
    return accepted, bot_comment("personality.drawAccepted" if accepted else "personality.drawDeclined")


def default_comment_for(config: BotPersonalityConfig) -> str:
    """Default remark by aggression: from +30 — attack, from -30 — calm play, otherwise positional."""
    if config.aggression >= 30:
        return "personality.seekAttack"
    if config.aggression <= -30:
        return "personality.calm"
    return "personality.positional"


def favorite_moves(config: BotPersonalityConfig) -> dict[str, list[tuple[str, str]]]:
    """
    Position (EPD) → the bot's favourite opening moves from it and the opening name. Moves are taken only for the colour of the
    list: White
    openings — when the bot plays White, Black ones — Black; by position, so move transpositions also lead into the line.
    """
    table = openings.lines()
    sources: list[tuple[chess.Color | None, tuple[str, ...], str]] = []
    for own, epds in ((chess.WHITE, config.openings_white), (chess.BLACK, config.openings_black)):
        sources += [(own, table[epd].moves, table[epd].name) for epd in epds]
    # Own favourite openings matter more than character lines: with chosen openings the character adds lines rather than
    # replaces them.
    # Character lines have no name: the remark must not give away a trap ("... Trap").
    sources += [(color, line_moves, "") for color, line_moves, _ in style_lines(config.opening_style)]
    moves: dict[str, list[tuple[str, str]]] = {}
    for color, line_moves, name in sources:
        board = chess.Board()
        for uci in line_moves:
            if color is None or board.turn == color:
                entry = (uci, name)
                bucket = moves.setdefault(board.epd(), [])
                if entry not in bucket:
                    bucket.append(entry)
            board.push_uci(uci)
    return moves


class PersonalityBot(HistoricalBot):
    """
    An opponent with a personality from BotPersonalityConfig: favourite openings instead of a book, style from build_style,
    strength by
    target_elo (strength_for). The errors of the weak and the attitude to draws are added by _select_move.
    """

    bot_id = "custom"
    engine_source_name = "personality_engine"
    multipv = 8
    opening_book: dict[str, list[BookEntry]] = {}

    def __init__(self, config: BotPersonalityConfig, stockfish_path: str | None = None):
        """Builds the strength, style, default remark and favourite openings from config."""
        self.config = config
        self.strength = strength_for(config.target_elo)
        super().__init__(
            stockfish_path,
            uci_elo=self.strength.uci_elo,
            search_depth=self.strength.depth,
        )
        self.time_limit = self.strength.time_limit
        self.blunder_guard_cp = float(config.blunder_guard_cp)
        self.jitter_range = config.randomness * JITTER_CP_PER_RANDOMNESS
        self.style = build_style(config)
        self.default_comment = default_comment_for(config)
        self.favorites = favorite_moves(config)

    def _book_move(self, board: chess.Board) -> tuple[chess.Move, dict] | None:
        """A favourite-opening move while the position is in its lines; the opponent deviated — then the engine plays."""
        options = [(chess.Move.from_uci(uci), name) for uci, name in self.favorites.get(board.epd(), [])]
        options = [(move, name) for move, name in options if move in board.legal_moves]
        if not options:
            return None
        # A named (favourite) opening matters more than nameless character lines: a master with an opening of his own name goes
        # into it,
        # not into a random gambit line.
        named = [option for option in options if option[1]]
        move, name = random.choice(named or options)
        if not name:
            return move, bot_comment("personality.openingHabit")
        return move, bot_comment("personality.favoriteOpening", name=name)

    def _draw_attitude(self, board: chess.Board, scores: dict[chess.Move, float]) -> dict[chess.Move, float]:
        """On equality (the best move within +-0.8) a peaceable bot trades pieces more readily, an uncompromising one avoids
        it."""
        attitude = self.config.draw_attitude
        if not attitude or not scores or abs(max(scores.values())) > EQUAL_CP:
            return scores
        adjusted = dict(scores)
        for move in scores:
            captured = board.piece_at(move.to_square)
            if captured is not None and captured.piece_type != chess.PAWN and board.is_capture(move):
                adjusted[move] += TRADE_CP_PER_ATTITUDE * attitude
        return adjusted

    def _select_move(
            self, board: chess.Board, scores: dict[chess.Move, float], reference: chess.Move | None = None,
    ) -> tuple[chess.Move, str | None]:
        """Move choice with the draw attitude and the controlled errors of the weak taken into account; otherwise — as the
        base bot."""
        # Controlled error for the weak (the ERROR_RATE_CURVE curve). MultiPV lines are often almost equal to the best — an
        # "error"
        # among them cost almost nothing (13.11 calibration: "Rusher" with target 700 played at ~1150). Now an error is
        # a move from the worse half of the lines, and in BLUNDER_SHARE cases a random legal move: a gross blunder, like a
        # beginner's.
        scores = self._draw_attitude(board, scores)
        if self.strength.error_rate and len(scores) > 1 and random.random() < self.strength.error_rate:
            if random.random() < BLUNDER_SHARE:
                weaker = random.choice(list(board.legal_moves))
            else:
                ranked = sorted(scores, key=lambda mv: scores[mv], reverse=True)
                weaker = random.choice(ranked[max(1, len(ranked) // 2):])
            return weaker, self.evaluate_style_bonus(board, weaker)[1]
        return super()._select_move(board, scores, reference)
