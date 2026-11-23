# --- FILE: src/services/bots/style.py ---
"""
Bot style model: rules that give MultiPV candidates a bonus in centipawns.

The position evaluation comes only from the engine (or from the static analyser without one). Style does not change it:
it only reorders candidates inside the blunder_guard_cp window from the best move, awarding bonuses for
move features computed by python-chess (check, capture, castling, development, centre, pawn structure...).

A style is a list of rules:

* Rule(condition, bonus, comment, mode) — if the condition holds, the bonus is added;
  the comment either overwrites the current one (SET) or is set only if there is none yet (FILL);
* Group(condition, *rules) — nested rules are checked only if the common condition holds;
* FirstOf(*rules) — the first matching rule fires (like if/elif).

This is how both the seven historical bots (presets in their modules) and user personalities
(src/services/bots/personality.py) are expressed — one interpreter for all.

The module touches neither the database nor the network: rules are pure functions of the position and the move. They are
applied by base.HistoricalBot and
tournament simulation (Style.evaluate).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from functools import cached_property

import chess

# Four central squares: d4, e4, d5, e5.
CENTER_SQUARES = frozenset({chess.D4, chess.E4, chess.D5, chess.E5})
# Extended centre: files c-f on the 4th and 5th ranks (includes CENTER_SQUARES).
EXTENDED_CENTER = frozenset({
    chess.C4, chess.D4, chess.E4, chess.F4,
    chess.C5, chess.D5, chess.E5, chess.F5,
})
# Minor pieces — for those that need "development".
MINOR_PIECES = (chess.KNIGHT, chess.BISHOP)


class MoveContext:
    """A move in the position before it; expensive features are computed lazily and once."""

    def __init__(self, board: chess.Board, move: chess.Move):
        self.board = board
        self.move = move
        self.us = board.turn
        self.piece = board.piece_at(move.from_square)

    @cached_property
    def gives_check(self) -> bool:
        """The move gives check."""
        return self.board.gives_check(self.move)

    @cached_property
    def is_capture(self) -> bool:
        """The move is a capture (including en passant)."""
        return self.board.is_capture(self.move)

    @cached_property
    def is_castling(self) -> bool:
        """The move is castling."""
        return self.board.is_castling(self.move)

    @cached_property
    def captured_piece_type(self) -> int | None:
        """Type of the captured piece (for en passant — a pawn); None — no capture."""
        if self.board.is_en_passant(self.move):
            return chess.PAWN
        captured = self.board.piece_at(self.move.to_square)
        return captured.piece_type if captured and captured.color != self.us else None

    @cached_property
    def board_after(self) -> chess.Board:
        """Position after the move (a copy without move history)."""
        after = self.board.copy(stack=False)
        after.push(self.move)
        return after

    @cached_property
    def destination_attacked(self) -> bool:
        """The destination square after the move is attacked by the opponent (the piece can be captured)."""
        return self.board_after.is_attacked_by(not self.us, self.move.to_square)


# --- Conditions -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class Cond:
    """
    A style rule condition — a check of the move in its context. Conditions are combined with operators: & — and, | — or, ~ —
    not.
    """
    test: Callable[[MoveContext], bool]

    def __call__(self, ctx: MoveContext) -> bool:
        return self.test(ctx)

    def __and__(self, other: Cond) -> Cond:
        return Cond(lambda c: self.test(c) and other.test(c))

    def __or__(self, other: Cond) -> Cond:
        return Cond(lambda c: self.test(c) or other.test(c))

    def __invert__(self) -> Cond:
        return Cond(lambda c: not self.test(c))


# Ready conditions: always, check, capture, castling, a move from one's own side's first rank.
ALWAYS = Cond(lambda c: True)
CHECK = Cond(lambda c: c.gives_check)
CAPTURE = Cond(lambda c: c.is_capture)
CASTLING = Cond(lambda c: c.is_castling)
FROM_BACK_RANK = Cond(
    lambda c: chess.square_rank(c.move.from_square) == (0 if c.us == chess.WHITE else 7)
)


def piece(*types: int) -> Cond:
    """A piece of one of the types types moves (chess.PAWN, chess.KNIGHT ...)."""
    return Cond(lambda c: c.piece is not None and c.piece.piece_type in types)


def by_move(n: int) -> Cond:
    """No later than the n-th move of the game (fullmove_number)."""
    return Cond(lambda c: c.board.fullmove_number <= n)


def to(squares: Iterable[int]) -> Cond:
    """The move's destination square is in squares."""
    target = frozenset(squares)
    return Cond(lambda c: c.move.to_square in target)


def to_file(*files: int) -> Cond:
    """The file of the move's destination square is one of files (0 — the a file)."""
    return Cond(lambda c: chess.square_file(c.move.to_square) in files)


def side(color: chess.Color) -> Cond:
    """The side color moves."""
    return Cond(lambda c: c.us == color)


def piece_on(square: int, expected: chess.Piece) -> Cond:
    """Before the move, the square square holds exactly the piece expected (colour and type)."""
    return Cond(lambda c: c.board.piece_at(square) == expected)


# --- Rules -----------------------------------------------------------------------------------

class Note(Enum):
    """How a rule sets the move remark: SET — always, FILL — only if there is no remark yet."""

    SET = "set"  # overwrite the comment
    FILL = "fill"  # set only if there is no comment yet


# Rule bonus: a number of centipawns or a function of the move context (a feature with a computed weight).
Bonus = float | Callable[[MoveContext], float]


@dataclass(frozen=True)
class Rule:
    """A rule: if when holds — bonus (cp) is added to the move and the remark note (a botComments key) is set by mode."""

    when: Cond
    bonus: Bonus
    note: str | None = None
    mode: Note = Note.SET

    def value(self, ctx: MoveContext) -> float:
        """The rule's bonus for a move: a number or the function's result."""
        return self.bonus(ctx) if callable(self.bonus) else self.bonus


@dataclass(frozen=True)
class Group:
    """Nested rules items that are checked only if the common condition when holds for the move."""

    when: Cond
    items: tuple[StyleItem, ...]

    def __init__(self, when: Cond, *items: StyleItem):
        object.__setattr__(self, "when", when)
        object.__setattr__(self, "items", items)


@dataclass(frozen=True)
class FirstOf:
    """Of rules only the first matching one fires (like if/elif)."""

    rules: tuple[Rule, ...]

    def __init__(self, *rules: Rule):
        object.__setattr__(self, "rules", rules)


StyleItem = Rule | Group | FirstOf


class _Accumulator:
    """The sum of bonuses and the final comment of a move."""

    def __init__(self, note_by_weight: bool):
        self.bonus = 0.0
        self.note: str | None = None
        self._note_by_weight = note_by_weight
        self._note_weight = 0.0

    def apply(self, rule: Rule, ctx: MoveContext) -> None:
        """
        Takes into account a fired rule: adds its bonus and decides whose remark stays with the move (SET rules
        overwrite it, FILL ones only fill an empty one; for personalities — the remark of the heaviest feature).
        """
        value = rule.value(ctx)
        self.bonus += value
        if rule.note is None:
            return
        if self._note_by_weight:
            # The comment of the heaviest positive feature of the move.
            if value > self._note_weight:
                self.note, self._note_weight = rule.note, value
        elif rule.mode is Note.SET or self.note is None:
            self.note = rule.note


class Style:
    """
    A set of style rules. note_by_weight=False — comments in rule order (SET/FILL), as in
    the historical bots; True — the comment of the rule with the largest bonus (personalities with sliders).
    """

    def __init__(self, name: str, *items: StyleItem, note_by_weight: bool = False):
        self.name = name
        self.items = items
        self.note_by_weight = note_by_weight

    def evaluate(self, board_before: chess.Board, move: chess.Move) -> tuple[float, str | None]:
        """The sum of bonuses (cp) and the remark key for a move in the position before it; (0, None) — if the origin square
        is empty."""
        ctx = MoveContext(board_before, move)
        if ctx.piece is None:
            return 0.0, None
        acc = _Accumulator(self.note_by_weight)
        self._run(self.items, ctx, acc)
        return acc.bonus, acc.note

    def _run(self, items: Iterable[StyleItem], ctx: MoveContext, acc: _Accumulator) -> None:
        """Walks the rules in order: a Rule is applied, a Group is expanded, a FirstOf takes the first matching one."""
        for item in items:
            if isinstance(item, Rule):
                if item.when(ctx):
                    acc.apply(item, ctx)
            elif isinstance(item, Group):
                if item.when(ctx):
                    self._run(item.items, ctx, acc)
            else:
                for rule in item.rules:
                    if rule.when(ctx):
                        acc.apply(rule, ctx)
                        break


# --- Positional features shared by presets and personalities ---------------------------------------

def pawn_structure_score(board: chess.Board, us: chess.Color) -> float:
    """
    Pawn structure evaluation of side us (conventional points): +3 for each rank of advancement, +15 for a pawn in a phalanx
    (a neighbour to the right on the same rank), +10 for a pawn protected by a pawn, -20 for each doubled one.
    """
    our_pawns = board.pieces(chess.PAWN, us)
    start_rank = 1 if us == chess.WHITE else 6
    pawn_files = [chess.square_file(sq) for sq in our_pawns]

    score = 0.0
    for sq in our_pawns:
        f = chess.square_file(sq)
        r = chess.square_rank(sq)
        if r != start_rank:
            score += float(r if us == chess.WHITE else (7 - r)) * 3.0
        if f < 7 and chess.square(f + 1, r) in our_pawns:
            score += 15.0
        support_rank = (r - 1) if us == chess.WHITE else (r + 1)
        # The range is checked first: for edge ranks support_rank goes off the board.
        if 0 <= support_rank <= 7 and (
                (f > 0 and chess.square(f - 1, support_rank) in our_pawns)
                or (f < 7 and chess.square(f + 1, support_rank) in our_pawns)
        ):
            score += 10.0

    doubled_pawns = len(pawn_files) - len(set(pawn_files))
    score -= float(doubled_pawns) * 20.0
    return score


def pawn_structure_delta(ctx: MoveContext) -> float:
    """How a move changes the pawn structure of its own side (pawn_structure_score after minus before)."""
    return pawn_structure_score(ctx.board_after, ctx.us) - pawn_structure_score(ctx.board, ctx.us)


def mobility_count(board: chess.Board, color: chess.Color) -> int:
    """Number of moves of side color in the position (pseudo-legal — fast and sufficient for comparison)."""
    if board.turn == color:
        return board.pseudo_legal_moves.count()
    probe = board.copy(stack=False)
    probe.turn = color
    probe.ep_square = None
    return probe.pseudo_legal_moves.count()


# --- Middlegame personality features (task B.5): shared by the workshop and the historical bots -----------------

# Standard piece value scale in pawns (for evaluating sacrifices and a persona's "taste" for pieces); the king is not in it.
STANDARD_VALUES = {chess.PAWN: 1.0, chess.KNIGHT: 3.0, chess.BISHOP: 3.0, chess.ROOK: 5.0, chess.QUEEN: 9.0}


def _sacrifice(c: MoveContext) -> bool:
    """A piece goes en prise and is worth more than what is captured (an unprotected pawn is a sacrifice too)."""
    if c.piece is None or c.piece.piece_type == chess.KING or not c.destination_attacked:
        return False
    moved = STANDARD_VALUES[c.piece.piece_type]
    taken = STANDARD_VALUES.get(c.captured_piece_type or 0, 0.0)
    if moved <= taken:
        return False
    defended = c.board_after.is_attacked_by(c.us, c.move.to_square)
    return not defended or c.piece.piece_type != chess.PAWN


def _near_enemy_king(c: MoveContext) -> bool:
    """A piece goes no further than two squares from the opponent's king."""
    king = c.board.king(not c.us)
    return king is not None and chess.square_distance(c.move.to_square, king) <= 2


# A sacrifice, a piece near the opponent's king and a quiet move (neither check nor capture).
SACRIFICE = Cond(_sacrifice)
NEAR_ENEMY_KING = Cond(_near_enemy_king)
QUIET = ~CHECK & ~CAPTURE


def after_move(n: int) -> Cond:
    """After the n-th move of the game — the middlegame and later (a pair to by_move)."""
    return Cond(lambda c: c.board.fullmove_number > n)


def _active_moves(board: chess.Board, color: chess.Color) -> int:
    """Captures and checks available to side color are its threats."""
    probe = board
    if board.turn != color:
        probe = board.copy(stack=False)
        probe.turn = color
        probe.ep_square = None
    return sum(1 for m in probe.pseudo_legal_moves if probe.is_capture(m) or probe.gives_check(m))


def prophylaxis(c: MoveContext) -> float:
    """
    Prophylaxis: how many threats (captures and checks) the move takes away from the opponent — the main contribution (6 cp per
    threat, up to 6
    threats), and how much it reduces his mobility — an additional one (1 cp per square, up to 10).
    """
    them = not c.us
    threats_removed = _active_moves(c.board, them) - _active_moves(c.board_after, them)
    squares_removed = mobility_count(c.board, them) - mobility_count(c.board_after, them)
    return 6.0 * max(0, min(6, threats_removed)) + 1.0 * max(0, min(10, squares_removed))
