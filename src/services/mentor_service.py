# --- FILE: src/services/mentor_service.py ---
"""
Chess motif detector for the mentor.

Returns **facts**, not text: the motif code, the side that benefits from it, the key square, the targets and a numeric
value. The template layer (task 11.2) turns the facts into words. The detector does not use the engine: everything is computed
by rules on `python-chess`, so the result is reproducible and is checked by tests on concrete positions.

The main principle is that a false positive is worse than a miss: a mentor who sees a "fork" where there is none
does more harm than a silent one. Therefore material motifs are verified by an honest exchange on the square (SEE over legal
moves, taking pins and defenders into account), not by the "attacked and not defended" flag.

The ``color`` field of a fact is the side that **benefits** from the motif (can make use of it): for a fork, the side whose
piece attacks; for a weak back rank, the opponent of the owner of that rank; for a passed pawn,
its owner.

Called by coach.py (mentor words), personal_puzzles.py (personal puzzle themes) and puzzle_import.py (puzzle database themes).
Takes no data from the DB, Redis or settings: the input is only a position (chess.Board) and a move.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

import chess

MotifCode = Literal[
    "hanging",            # a piece can be captured with a material gain
    "fork",               # one piece attacks two targets, and both cannot be saved
    "pin_absolute",       # pin: the king is behind the piece, so it cannot move
    "pin_relative",       # pin: a more valuable piece is behind the piece
    "skewer",             # skewer: a valuable piece in front, with another one behind it
    "discovered_attack",  # the move opened the line of a long-range piece onto a target
    "discovered_check",   # the move opened a check
    "double_check",       # double check
    "overloaded",         # one piece is the only defender of two attacked pieces
    "trapped",            # a piece is under attack and has nowhere to go
    "back_rank",          # weak back rank
    "mate_threat",        # if the ``color`` side were to move, it would have mate in one
    "mate_in",            # the side to move has mate in one or two (in two, only starting with a check)
    "passed_pawn",        # passed pawn
    "open_file",          # rook on an open file
    "half_open_file",     # rook on a half-open file
    "development_lag",    # lag in the development of minor pieces
    "delayed_castling",   # king uncastled at home, opponent has a queen, king has no own pawn on d or e
    "battery",            # two long-range pieces on one line, adjacent, with the line ending on an opponent piece
    "interference",       # the move blocked a line along which an opponent piece defended its own
]

# Teaching piece values (in centipawns): the exchange is computed with them, the way it is explained to a student.
PIECE_VALUE = {
    chess.PAWN: 100,
    chess.KNIGHT: 300,
    chess.BISHOP: 300,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 10_000,
}

# Opening motifs (development lag, delayed castling) are computed only on moves
# DEVELOPMENT_MIN_MOVE ... OPENING_MOVE_LIMIT.
OPENING_MOVE_LIMIT = 20
# Before this move (the game's move number) it is too early to judge development.
DEVELOPMENT_MIN_MOVE = 6
# From this move on, a king that has not left home, with an opponent queen on the board and no pawn of its own on d or e,
# counts as having delayed castling.
CASTLING_MIN_MOVE = 10
# How many more untouched minor pieces a side must have than its opponent for this to become a motif.
DEVELOPMENT_LAG_MIN = 2

# Home squares of knights and bishops: a piece on its home square counts as undeveloped.
_MINOR_HOME = {
    chess.WHITE: {chess.B1: chess.KNIGHT, chess.G1: chess.KNIGHT, chess.C1: chess.BISHOP, chess.F1: chess.BISHOP},
    chess.BLACK: {chess.B8: chess.KNIGHT, chess.G8: chess.KNIGHT, chess.C8: chess.BISHOP, chess.F8: chess.BISHOP},
}
# King's home square for the "has not castled" check.
_KING_HOME = {chess.WHITE: chess.E1, chess.BLACK: chess.E8}
# Number of each side's back rank (0 is the first rank, 7 is the eighth).
_BACK_RANK = {chess.WHITE: 0, chess.BLACK: 7}

# Board steps (file, rank) for rook and bishop rays; the queen is their sum (_slider_steps).
_ROOK_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))
_BISHOP_STEPS = ((1, 1), (1, -1), (-1, 1), (-1, -1))


@dataclass(frozen=True)
class Motif:
    """
    One fact about a position: a code, the side that benefits from it, the key square, the targets and a number (``value``:
    material gain in centipawns, mate length, number of moves to promotion, depending on the code). ``targets`` are the
    target squares (for a pin: the pinned piece, then the piece behind it; for ``hanging``: the squares of the attacking
    pieces).
    """

    code: MotifCode
    color: chess.Color
    square: chess.Square
    targets: tuple[chess.Square, ...] = ()
    value: int | None = None

    @property
    def key(self) -> tuple:
        """Identity of a fact for comparing positions before and after a move (the value is not included)."""
        return self.code, self.color, self.square, self.targets

    def to_dict(self, board: chess.Board) -> dict:
        """JSON representation: field names and the pieces on them in position ``board``."""
        def describe(square: chess.Square) -> dict:
            piece = board.piece_at(square)
            return {"square": chess.square_name(square), "piece": piece.symbol() if piece else None}

        return {
            "code": self.code,
            "color": "white" if self.color == chess.WHITE else "black",
            **describe(self.square),
            "targets": [describe(target) for target in self.targets],
            "value": self.value,
        }


@dataclass
class MoveFacts:
    """
    What the move changed: ``created`` are motifs that appeared in favour of the mover, ``allowed`` are those handed to the
    opponent, ``resolved`` are motifs that disappeared after the move.
    """

    created: list[Motif] = field(default_factory=list)
    allowed: list[Motif] = field(default_factory=list)
    resolved: list[Motif] = field(default_factory=list)


# --- exchange on a square ---------------------------------------------------------------------


def _value(piece: chess.Piece | None) -> int:
    """Teaching value of a piece according to PIECE_VALUE; an empty square is 0."""
    return PIECE_VALUE[piece.piece_type] if piece else 0


def _least_valuable_capture(board: chess.Board, square: chess.Square) -> chess.Move | None:
    """Legal capture on the square by the cheapest piece of the side to move (promotion is to a queen)."""
    best: chess.Move | None = None
    best_value = 0
    for move in board.generate_legal_captures(to_mask=chess.BB_SQUARES[square]):
        if move.promotion not in (None, chess.QUEEN):
            continue
        attacker_value = _value(board.piece_at(move.from_square))
        if best is None or attacker_value < best_value:
            best, best_value = move, attacker_value
    return best


def _see(board: chess.Board, square: chess.Square) -> int:
    """Gain of the side to move from an exchange on the square with best play by both sides (it may decline)."""
    move = _least_valuable_capture(board, square)
    if move is None:
        return 0
    captured = _value(board.piece_at(square))
    promotion_gain = PIECE_VALUE[chess.QUEEN] - PIECE_VALUE[chess.PAWN] if move.promotion else 0
    board.push(move)
    try:
        return max(0, captured + promotion_gain - _see(board, square))
    finally:
        board.pop()


def capture_gain(board: chess.Board, square: chess.Square) -> int | None:
    """
    Net gain of the side to move if it **starts** the exchange on the square (it can no longer change its mind
    after the first capture). None means there is nothing to capture on the square with.
    """
    move = _least_valuable_capture(board, square)
    if move is None:
        return None
    captured = _value(board.piece_at(square))
    promotion_gain = PIECE_VALUE[chess.QUEEN] - PIECE_VALUE[chess.PAWN] if move.promotion else 0
    board.push(move)
    try:
        return captured + promotion_gain - _see(board, square)
    finally:
        board.pop()


def _as_side_to_move(board: chess.Board, color: chess.Color) -> chess.Board | None:
    """
    A copy of the position where ``color`` is to move: this is how threats of the side that is not currently on move are
    computed ("what happens if the move is skipped"). None if skipping the move is impossible (the side to move is in check).
    """
    if board.turn == color:
        return board.copy(stack=False)
    if board.is_check():
        return None
    probe = board.copy(stack=False)
    probe.push(chess.Move.null())
    return probe


# --- geometry -------------------------------------------------------------------------------


def _ray_squares(square: chess.Square, step: tuple[int, int]) -> Iterator[chess.Square]:
    """Squares of the ray from ``square`` (excluding it) in direction ``step`` up to the edge of the board."""
    file, rank = chess.square_file(square), chess.square_rank(square)
    while True:
        file, rank = file + step[0], rank + step[1]
        if not (0 <= file < 8 and 0 <= rank < 8):
            return
        yield chess.square(file, rank)


def _slider_steps(piece_type: chess.PieceType) -> tuple[tuple[int, int], ...]:
    """Ray directions of a long-range piece; empty for other kinds."""
    if piece_type == chess.ROOK:
        return _ROOK_STEPS
    if piece_type == chess.BISHOP:
        return _BISHOP_STEPS
    if piece_type == chess.QUEEN:
        return _ROOK_STEPS + _BISHOP_STEPS
    return ()


def _first_two_on_ray(board: chess.Board, square: chess.Square, step: tuple[int, int]) -> list[chess.Square]:
    """The first two pieces (of any colour) on the ray from the square."""
    found: list[chess.Square] = []
    for target in _ray_squares(square, step):
        if board.piece_at(target):
            found.append(target)
            if len(found) == 2:
                break
    return found


def _real_defenders(board: chess.Board, square: chess.Square, color: chess.Color) -> list[chess.Square]:
    """Defenders of the square that can recapture: a piece pinned to the king defends only along the pin line."""
    return [
        defender for defender in board.attackers(color, square)
        if not board.is_pinned(color, defender) or square in board.pin(color, defender)
    ]


def _is_defended(board: chess.Board, square: chess.Square) -> bool:
    """The piece on the square is defended by at least one real defender (``_real_defenders``)."""
    piece = board.piece_at(square)
    return piece is not None and bool(_real_defenders(board, square, piece.color))


# --- position motifs --------------------------------------------------------------------------


def _hanging(board: chess.Board) -> list[Motif]:
    """Pieces that a side can capture with a material gain (for both sides)."""
    found: list[Motif] = []
    for attacker in (chess.WHITE, chess.BLACK):
        probe = _as_side_to_move(board, attacker)
        if probe is None:
            continue
        for square in chess.SquareSet(board.occupied_co[not attacker]):
            piece = board.piece_at(square)
            if piece is None or piece.piece_type == chess.KING:
                continue
            gain = capture_gain(probe, square)
            if gain is not None and gain > 0:
                attackers = tuple(sorted(probe.attackers(attacker, square)))
                found.append(Motif("hanging", attacker, square, attackers, gain))
    return found


def _loose_target(board: chess.Board, attacker_square: chess.Square, target: chess.Square) -> bool:
    """A target on which an attack is really dangerous: the king, a more valuable piece or an undefended piece."""
    piece = board.piece_at(target)
    if piece is None:
        return False
    if piece.piece_type == chess.KING:
        return True
    if piece.piece_type == chess.PAWN:
        return False
    return _value(piece) > _value(board.piece_at(attacker_square)) or not _is_defended(board, target)


def _forks(board: chess.Board) -> list[Motif]:
    """
    Forks by the side that has just moved: its piece attacks two or more targets, and the opponent cannot
    simply capture that piece with a gain. For the side to move, an attack on two pieces is
    no longer a fork but an opportunity to capture one of them (the ``hanging`` motif).
    """
    forker = not board.turn
    found: list[Motif] = []
    for square in chess.SquareSet(board.occupied_co[forker]):
        piece = board.piece_at(square)
        if piece is None or piece.piece_type == chess.KING:
            continue
        targets = tuple(sorted(
            target for target in board.attacks(square)
            if board.color_at(target) == (not forker) and _loose_target(board, square, target)
        ))
        if len(targets) < 2:
            continue
        gain = capture_gain(board, square)
        if gain is not None and gain > 0:
            continue  # the forking piece will simply be removed
        found.append(Motif("fork", forker, square, targets))
    return found


def _slider_can_be_taken(board: chess.Board, slider_square: chess.Square, victim: chess.Color) -> bool:
    """
    The victim side can remove the pinning piece at least with an equal exchange, in which case there is effectively no pin
    (a queen against an undefended queen is an offer to trade, not a skewer).
    """
    probe = _as_side_to_move(board, victim)
    if probe is None:
        return False
    gain = capture_gain(probe, slider_square)
    return gain is not None and gain >= 0


def _pins_and_skewers(board: chess.Board) -> list[Motif]:
    """Pins (absolute and relative) and skewers for both sides; the motif is on the long-range piece."""
    found: list[Motif] = []
    for square in chess.SquareSet(board.occupied):
        slider = board.piece_at(square)
        if slider is None:
            continue
        for step in _slider_steps(slider.piece_type):
            pieces = _first_two_on_ray(board, square, step)
            if len(pieces) < 2:
                continue
            front_square, back_square = pieces
            front, back = board.piece_at(front_square), board.piece_at(back_square)
            if front is None or back is None or front.color == slider.color or back.color == slider.color:
                continue
            if _slider_can_be_taken(board, square, front.color):
                continue
            front_value, back_value = _value(front), _value(back)
            if back.piece_type == chess.KING:
                found.append(Motif("pin_absolute", slider.color, square, (front_square, back_square)))
            elif front.piece_type == chess.KING:
                if back.piece_type != chess.PAWN:
                    found.append(Motif("skewer", slider.color, square, (front_square, back_square)))
            elif back_value > front_value and back_value > _value(slider):
                found.append(Motif("pin_relative", slider.color, square, (front_square, back_square)))
            elif front_value > back_value and back.piece_type != chess.PAWN and (
                    front_value > _value(slider) or not _is_defended(board, front_square)):
                found.append(Motif("skewer", slider.color, square, (front_square, back_square)))
    return found


def _overloaded(board: chess.Board) -> list[Motif]:
    """
    The piece is the only defender of two attacked pieces of its own side, and both are currently held only
    by it (if the piece can be captured anyway, that is the ``hanging`` motif, not overloading).
    """
    found: list[Motif] = []
    for defender_color in (chess.WHITE, chess.BLACK):
        attacker = not defender_color
        probe = _as_side_to_move(board, attacker)
        if probe is None:
            continue
        duties: dict[chess.Square, list[chess.Square]] = {}
        for square in chess.SquareSet(board.occupied_co[defender_color]):
            piece = board.piece_at(square)
            if piece is None or piece.piece_type in (chess.KING, chess.PAWN):
                continue
            if not board.attackers(attacker, square):
                continue
            gain = capture_gain(probe, square)
            if gain is None or gain > 0:
                continue
            # A defender pinned to the king is not a "second defender": the only real one is overloaded.
            defenders = _real_defenders(board, square, defender_color)
            if len(defenders) == 1:
                duties.setdefault(defenders[0], []).append(square)
        for defender, guarded in duties.items():
            defender_piece = board.piece_at(defender)
            if len(guarded) >= 2 and defender_piece and defender_piece.piece_type != chess.KING:
                found.append(Motif("overloaded", attacker, defender, tuple(sorted(guarded))))
    return found


def _trapped(board: chess.Board) -> list[Motif]:
    """
    A piece of the side to move is under attack and there is nothing to save it with: neither retreat, nor defence, nor capture
    of the attacker, since any move loses it. Otherwise it is merely a threat (the ``hanging`` motif).
    """
    found: list[Motif] = []
    owner = board.turn
    for square in chess.SquareSet(board.occupied_co[owner]):
        piece = board.piece_at(square)
        if piece is None or piece.piece_type in (chess.KING, chess.PAWN):
            continue
        probe = _as_side_to_move(board, not owner)
        if probe is None:
            continue
        gain = capture_gain(probe, square)
        if gain is None or gain <= 0:
            continue
        safe = False
        for move in list(board.legal_moves):
            # A capturing move pays off if what is then given up is no more than what was taken.
            taken = _value(board.piece_at(move.to_square)) if board.is_capture(move) else 0
            where = move.to_square if move.from_square == square else square
            board.push(move)
            try:
                after = capture_gain(board, where)
                if after is None or after <= taken:
                    safe = True
            finally:
                board.pop()
            if safe:
                break
        if not safe:
            found.append(Motif("trapped", not owner, square, (), _value(piece)))
    return found


def _back_rank(board: chess.Board) -> list[Motif]:
    """
    The king is on the back rank with no "luft", and an opponent heavy piece already attacks the square of that
    rank from which it will give check, where the king cannot capture it and which nobody else defends. Simply
    "pawns f, g, h have not moved" does not count as a motif.
    """
    found: list[Motif] = []
    for owner in (chess.WHITE, chess.BLACK):
        king = board.king(owner)
        if king is None or chess.square_rank(king) != _BACK_RANK[owner]:
            continue
        enemy = not owner
        forward = 1 if owner == chess.WHITE else -1
        escape_rank = _BACK_RANK[owner] + forward
        has_luft = False
        for file in range(max(0, chess.square_file(king) - 1), min(7, chess.square_file(king) + 1) + 1):
            escape = chess.square(file, escape_rank)
            if board.color_at(escape) != owner and not board.attackers(enemy, escape):
                has_luft = True
                break
        if has_luft:
            continue
        heavy = board.pieces(chess.ROOK, enemy) | board.pieces(chess.QUEEN, enemy)
        weak: list[chess.Square] = []
        for file in range(8):
            square = chess.square(file, _BACK_RANK[owner])
            if board.color_at(square) == owner:
                continue
            enemy_attackers = board.attackers(enemy, square)
            if not any(attacker in heavy for attacker in enemy_attackers):
                continue
            if chess.between(square, king) & board.occupied:
                continue  # there will be no check from this square: there are pieces between it and the king
            if board.attackers(owner, square) - chess.SquareSet(chess.BB_SQUARES[king]):
                continue  # the square is defended by more than just the king
            if square in board.attacks(king) and len(enemy_attackers) < 2:
                continue  # the king will simply capture the piece that arrives
            weak.append(square)
        if weak:
            found.append(Motif("back_rank", enemy, king, tuple(weak)))
    return found


def _mate_in_one(board: chess.Board) -> chess.Move | None:
    """The first mate in one found for the side to move, otherwise None."""
    for move in board.legal_moves:
        board.push(move)
        try:
            if board.is_checkmate():
                return move
        finally:
            board.pop()
    return None


def _mate_in_two_by_checks(board: chess.Board) -> chess.Move | None:
    """Mate in 2 starting with a check: a full search of quiet first moves in Python is too slow."""
    for move in board.legal_moves:
        if not board.gives_check(move):
            continue
        board.push(move)
        try:
            replies = list(board.legal_moves)
            if replies and all(_mates_after(board, reply) for reply in replies):
                return move
        finally:
            board.pop()
    return None


def _mates_after(board: chess.Board, reply: chess.Move) -> bool:
    """After the reply ``reply`` the side to move has mate in one."""
    board.push(reply)
    try:
        return _mate_in_one(board) is not None
    finally:
        board.pop()


def _mates(board: chess.Board) -> list[Motif]:
    """
    Mate in 1 or 2 for the side to move (``mate_in``), and a mate in one that it would get
    if the opponent's move were skipped (``mate_threat``).
    """
    found: list[Motif] = []
    if board.is_game_over():
        return found
    mover = board.turn
    mate = _mate_in_one(board)
    if mate is not None:
        found.append(Motif("mate_in", mover, mate.from_square, (mate.to_square,), 1))
    else:
        mate = _mate_in_two_by_checks(board)
        if mate is not None:
            found.append(Motif("mate_in", mover, mate.from_square, (mate.to_square,), 2))

    probe = _as_side_to_move(board, not mover)
    if probe is not None:
        threat = _mate_in_one(probe)
        if threat is not None:
            found.append(Motif("mate_threat", not mover, threat.from_square, (threat.to_square,), 1))
    return found


def _batteries(board: chess.Board) -> list[Motif]:
    """
    Battery: the front and rear long-range pieces of one line stand adjacent (no pieces between them), and the line beyond
    the front one ends on an opponent piece. The motif is on the front piece; the targets are the rear piece and the target
    piece.
    """
    found: list[Motif] = []
    for color in (chess.WHITE, chess.BLACK):
        for square in chess.SquareSet(board.occupied_co[color]):
            front = board.piece_at(square)
            if front is None:
                continue
            for step in _slider_steps(front.piece_type):
                # Look for the rear piece: behind the front one, in the direction opposite to the target.
                back_step = (-step[0], -step[1])
                rear_square = next((s for s in _ray_squares(square, back_step) if board.piece_at(s)), None)
                if rear_square is None:
                    continue
                rear = board.piece_at(rear_square)
                if rear is None or rear.color != color or step not in _slider_steps(rear.piece_type):
                    continue
                target = next((s for s in _ray_squares(square, step) if board.piece_at(s)), None)
                if target is None or board.color_at(target) == color:
                    continue
                found.append(Motif("battery", color, square, (rear_square, target)))
    return found


def _passed_pawns(board: chess.Board) -> list[Motif]:
    """Passed pawns of both sides; ``value`` is how many moves remain to the promotion square."""
    found: list[Motif] = []
    for color in (chess.WHITE, chess.BLACK):
        enemy_pawns = board.pieces(chess.PAWN, not color)
        forward = 1 if color == chess.WHITE else -1
        for square in board.pieces(chess.PAWN, color):
            file, rank = chess.square_file(square), chess.square_rank(square)
            blocked = any(
                chess.square_file(pawn) in (file - 1, file, file + 1)
                and (chess.square_rank(pawn) - rank) * forward > 0
                for pawn in enemy_pawns
            )
            if not blocked:
                to_promotion = (7 - rank) if color == chess.WHITE else rank
                found.append(Motif("passed_pawn", color, square, (), to_promotion))
    return found


def _files(board: chess.Board) -> list[Motif]:
    """Rooks on an open file (no pawns on it) and a half-open file (no pawns of their own only)."""
    found: list[Motif] = []
    for color in (chess.WHITE, chess.BLACK):
        # Rooks only: the queen also moves along diagonals, and a "queen on an open file" explains nothing to a student.
        for square in board.pieces(chess.ROOK, color):
            file_mask = chess.BB_FILES[chess.square_file(square)]
            own_pawns = board.pieces_mask(chess.PAWN, color) & file_mask
            enemy_pawns = board.pieces_mask(chess.PAWN, not color) & file_mask
            if not own_pawns and not enemy_pawns:
                found.append(Motif("open_file", color, square))
            elif not own_pawns:
                found.append(Motif("half_open_file", color, square))
    return found


def _undeveloped(board: chess.Board, color: chess.Color) -> int:
    """How many knights and bishops of the side are still on their home squares (_MINOR_HOME)."""
    return sum(
        1 for square, piece_type in _MINOR_HOME[color].items()
        if board.piece_type_at(square) == piece_type and board.color_at(square) == color
    )


def _opening(board: chess.Board) -> list[Motif]:
    """
    Opening motifs ``development_lag`` and ``delayed_castling`` (in favour of the opponent of the lagging side); computed
    only on moves DEVELOPMENT_MIN_MOVE ... OPENING_MOVE_LIMIT.
    """
    found: list[Motif] = []
    move_number = board.fullmove_number
    if not DEVELOPMENT_MIN_MOVE <= move_number <= OPENING_MOVE_LIMIT:
        return found
    for color in (chess.WHITE, chess.BLACK):
        lag = _undeveloped(board, color) - _undeveloped(board, not color)
        if lag >= DEVELOPMENT_LAG_MIN:
            king = board.king(color)
            if king is not None:
                found.append(Motif("development_lag", not color, king, (), lag))

        king = board.king(color)
        if (
                move_number >= CASTLING_MIN_MOVE
                and king == _KING_HOME[color]
                and board.pieces(chess.QUEEN, not color)
                and any(
                    not (board.pieces_mask(chess.PAWN, color) & chess.BB_FILES[file])
                    for file in (3, 4)  # files d and e
                )
        ):
            found.append(Motif("delayed_castling", not color, king))
    return found


def detect_motifs(board: chess.Board) -> list[Motif]:
    """
    All motifs of the position for both sides, in a stable order. After mate or stalemate there are no motifs: a "fork"
    by the rook that gave mate explains nothing to a student.
    """
    if board.is_game_over():
        return []
    motifs = [
        *_mates(board),
        *_hanging(board),
        *_forks(board),
        *_pins_and_skewers(board),
        *_overloaded(board),
        *_trapped(board),
        *_back_rank(board),
        *_passed_pawns(board),
        *_files(board),
        *_opening(board),
        *_batteries(board),
    ]
    unique: dict[tuple, Motif] = {}
    for motif in motifs:
        unique.setdefault(motif.key, motif)
    return list(unique.values())


# --- move motifs ------------------------------------------------------------------------------


def _discoveries(board_before: chess.Board, move: chess.Move, board_after: chess.Board) -> list[Motif]:
    """The move opened a line for its own long-range piece: discovered attack, discovered check, double check."""
    mover = board_before.turn
    found: list[Motif] = []
    enemy_king = board_after.king(not mover)
    checkers = board_after.checkers() if enemy_king is not None else chess.SquareSet()
    for square in chess.SquareSet(board_after.occupied_co[mover]):
        if square == move.to_square:
            continue
        piece = board_after.piece_at(square)
        if piece is None or not _slider_steps(piece.piece_type):
            continue
        before = board_before.attacks(square)
        for target in board_after.attacks(square):
            if target in before or board_after.color_at(target) != (not mover):
                continue
            if move.from_square not in chess.SquareSet(chess.between(square, target)):
                continue
            target_piece = board_after.piece_at(target)
            if target_piece is not None and target_piece.piece_type == chess.KING:
                code: MotifCode = "double_check" if len(checkers) > 1 else "discovered_check"
                found.append(Motif(code, mover, square, (target, move.to_square)))
            elif _loose_target(board_after, square, target):
                found.append(Motif("discovered_attack", mover, square, (target,)))
    return found


def _interferences(board_before: chess.Board, move: chess.Move, board_after: chess.Board) -> list[Motif]:
    """
    Interference: the moved piece stepped between an opponent long-range piece and the piece it defended, and
    the defended piece became prey (it can be captured with a gain). The motif is on the move square; the targets are the
    defender and the piece.
    """
    mover = board_before.turn
    enemy = not mover
    found: list[Motif] = []
    for slider in chess.SquareSet(board_before.occupied_co[enemy]):
        piece = board_before.piece_at(slider)
        if piece is None or not _slider_steps(piece.piece_type):
            continue
        for defended in board_before.attacks(slider):
            if board_before.color_at(defended) != enemy or board_before.piece_type_at(defended) == chess.KING:
                continue
            if move.to_square not in chess.SquareSet(chess.between(slider, defended)):
                continue
            if board_after.piece_at(defended) is None or defended in board_after.attacks(slider):
                continue
            probe = _as_side_to_move(board_after, mover)
            gain = capture_gain(probe, defended) if probe is not None else None
            if gain is not None and gain > 0:
                found.append(Motif("interference", mover, move.to_square, (slider, defended)))
    return found


def analyze_move(
        board_before: chess.Board, move: chess.Move, before_motifs: list[Motif] | None = None,
) -> MoveFacts:
    """
    What the move changed: ``created`` are new motifs in favour of the mover (including discovered ones, which are visible
    only from the move itself), ``allowed`` are new motifs in favour of the opponent, ``resolved`` are motifs that
    disappeared after the move. ``before_motifs`` are the already found motifs of the position before the move (so as not
    to search for them again when several moves from one position are analysed).
    """
    if move not in board_before.legal_moves:
        raise ValueError(f"Illegal move {move.uci()} in position {board_before.fen()}")
    mover = board_before.turn
    if before_motifs is None:
        before_motifs = detect_motifs(board_before)
    before = {motif.key: motif for motif in before_motifs}
    board_after = board_before.copy(stack=False)
    board_after.push(move)
    after_list = detect_motifs(board_after)
    if not board_after.is_game_over():
        after_list += _discoveries(board_before, move, board_after)
        after_list += _interferences(board_before, move, board_after)
    after: dict[tuple, Motif] = {}
    for motif in after_list:
        after.setdefault(motif.key, motif)

    facts = MoveFacts()
    for key, motif in after.items():
        if key in before:
            continue
        (facts.created if motif.color == mover else facts.allowed).append(motif)
    facts.resolved = [motif for key, motif in before.items() if key not in after]
    return facts
