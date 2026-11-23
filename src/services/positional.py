# --- FILE: src/services/positional.py ---
"""
Positional features (task B.4): what to say when there is no tactic. The rules are simple and verifiable, with no engine -
the mentor names a feature and a square, not an evaluation:

* king_center - middlegame (from move 8, not an endgame, the opponent has a queen or pieces worth at least 10
  points), while the side's king is still on the first rank on file d or e (castling rights are not checked);
* king_holes - the king is on a wing (on the first rank, not on d/e), and on the third rank in front of it (king's file
  +-1) there is a square that an own pawn can never defend again; the opponent has a bishop of that colour, the side does not;
* passed_enemy / passed_own - an opponent's passed pawn (not blocked) or an own one that has reached at least the fourth
  rank from its own edge; the most advanced is named;
* king_active - endgame (no queens, few minor and heavy pieces), with the king on its own first two ranks;
* open_file - a file without pawns on which there is no own rook or queen (while a rook exists);
* outpost - a free square for a knight on files c-f and on the 4th-6th rank from its own edge, defended by an own
  pawn, which an opponent pawn can no longer drive away (the side has a knight);
* isolated_enemy - an opponent's isolated pawn in the centre (c-f) - a target of attack;
* backward_enemy - an opponent's backward pawn on a file half-open for the side: the neighbouring pawns have advanced, and
  the square in front of it is attacked by the side's pawn;
* bad_bishop - an own bishop, with more than half of the own pawns (at least three) on the squares of its colour and at
least two
  of them blocked;
* doubled_own - own doubled pawns.

Features are for the side color; the order is from important (king safety, passed pawns) to minor.

The module stores and reads nothing except the board. The features are turned into mentor sentences by
src/services/coach.py: advice on a position, the first hint step and the explanation of the best move (``move_idea``); the
text is assembled by the client from the coach.* catalogue by the code and parameters (square, file).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import chess

# Feature codes in order of importance; ``positional_features`` returns them in the same order.
POSITIONAL_PRIORITY = (
    "king_center", "king_holes", "passed_enemy", "passed_own", "king_active", "open_file", "outpost",
    "isolated_enemy", "backward_enemy", "bad_bishop", "doubled_own",
)
CENTRAL_FILES = (2, 3, 4, 5)  # c–f
# Endgame: each side has minor and heavy pieces worth no more than a rook plus a minor piece.
ENDGAME_MATERIAL = 8
PIECE_POINTS = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}  # points of pieces without pawns and the king


@dataclass(frozen=True)
class Feature:
    """A position feature: a code, parameters for the text (a square or a file) and the squares the client highlights."""

    code: str
    params: dict[str, str] = field(default_factory=dict)
    squares: tuple[chess.Square, ...] = ()


def _material(board: chess.Board, color: chess.Color) -> int:
    return sum(len(board.pieces(pt, color)) * points for pt, points in PIECE_POINTS.items())


def is_endgame(board: chess.Board) -> bool:
    """Endgame by the module's rule: nobody has queens, and each side has pieces worth no more than ENDGAME_MATERIAL."""
    return not board.pieces(chess.QUEEN, chess.WHITE) and not board.pieces(chess.QUEEN, chess.BLACK) and all(
        _material(board, color) <= ENDGAME_MATERIAL for color in chess.COLORS)


def _forward(color: chess.Color) -> int:
    return 1 if color == chess.WHITE else -1


def _relative_rank(square: chess.Square, color: chess.Color) -> int:
    """Rank from the side's point of view: 0 is its own first."""
    rank = chess.square_rank(square)
    return rank if color == chess.WHITE else 7 - rank


def is_passed(board: chess.Board, square: chess.Square, color: chess.Color) -> bool:
    """Whether the side's pawn on the square is passed: no opponent pawns ahead on its file and the neighbouring ones."""
    file, rank = chess.square_file(square), chess.square_rank(square)
    for enemy in board.pieces(chess.PAWN, not color):
        ef, er = chess.square_file(enemy), chess.square_rank(enemy)
        if abs(ef - file) <= 1 and (er - rank) * _forward(color) > 0:
            return False
    return True


def is_isolated(board: chess.Board, square: chess.Square, color: chess.Color) -> bool:
    """Whether the pawn is isolated: there are no own pawns on the neighbouring files."""
    file = chess.square_file(square)
    return not any(abs(chess.square_file(p) - file) == 1 for p in board.pieces(chess.PAWN, color))


def pawn_can_attack(board: chess.Board, square: chess.Square, by: chess.Color) -> bool:
    """
    Whether the pawn of side by can ever attack the square: a pawn on a neighbouring file is still behind the square. Whether
    its path is free is not checked - the estimate is cautious: the square counts as unreachable only when there is no such
    pawn at all.
    """
    file, rank = chess.square_file(square), chess.square_rank(square)
    for pawn in board.pieces(chess.PAWN, by):
        pf, pr = chess.square_file(pawn), chess.square_rank(pawn)
        if abs(pf - file) == 1 and (rank - pr) * _forward(by) > 0:
            return True
    return False


def is_outpost(board: chess.Board, square: chess.Square, color: chess.Color) -> bool:
    """
    Outpost for a knight: a square on the 4th-6th rank from its own edge, defended by an own pawn, which opponent pawns
    can no longer attack. A square occupied by an own piece (not a knight) is not an outpost.
    """
    if not 3 <= _relative_rank(square, color) <= 5:
        return False
    occupant = board.piece_at(square)
    if occupant is not None and occupant.color == color and occupant.piece_type != chess.KNIGHT:
        return False
    protected = any(board.piece_at(s) == chess.Piece(chess.PAWN, color)
                    for s in board.attackers(color, square))
    return protected and not pawn_can_attack(board, square, not color)


def is_open_file(board: chess.Board, file: int) -> bool:
    """Open file: there are no pawns of either side on it."""
    return not any(chess.square_file(p) == file for p in board.pieces(chess.PAWN, chess.WHITE)) and not any(
        chess.square_file(p) == file for p in board.pieces(chess.PAWN, chess.BLACK))


def _central_first(squares: list[chess.Square]) -> list[chess.Square]:
    """Squares from the central files to the edge ones: of several candidates the mentor names the most central."""
    return sorted(squares, key=lambda s: (abs(chess.square_file(s) - 3.5), s))


def _king_center(board: chess.Board, color: chess.Color) -> Feature | None:
    """
    King in the centre. Silent until move 8 (the opening is still on), in the endgame and when the opponent has neither a
    queen nor pieces worth 10 points: there is nothing to attack the king with.
    """
    king = board.king(color)
    if king is None or is_endgame(board) or board.fullmove_number < 8:
        return None
    if not board.pieces(chess.QUEEN, not color) and _material(board, not color) < 10:
        return None
    if _relative_rank(king, color) == 0 and chess.square_file(king) in (3, 4):
        return Feature("king_center", {}, (king,))
    return None


def _passed(board: chess.Board, color: chess.Color, own: bool) -> Feature | None:
    """
    Passed pawn: own (own) or the opponent's. The most advanced is named (on a tie - closer to the centre), and only
    if it has reached the fourth rank from its own edge: a passed pawn far from promotion is not yet a topic.
    """
    side = color if own else not color
    pawns = [p for p in board.pieces(chess.PAWN, side) if is_passed(board, p, side)]
    if not own:
        # A passed pawn blocked by a piece is not dangerous yet.
        pawns = [p for p in pawns if board.piece_at(p + 8 * _forward(side)) is None]
    if not pawns:
        return None
    lead = max(pawns, key=lambda p: (_relative_rank(p, side), -abs(chess.square_file(p) - 3.5)))
    if _relative_rank(lead, side) < 3:
        return None
    return Feature("passed_own" if own else "passed_enemy", {"square": chess.square_name(lead)}, (lead,))


def _king_active(board: chess.Board, color: chess.Color) -> Feature | None:
    king = board.king(color)
    if king is None or not is_endgame(board) or _relative_rank(king, color) > 1:
        return None
    return Feature("king_active", {}, (king,))


def _open_file(board: chess.Board, color: chess.Color) -> Feature | None:
    """
    Open file not occupied by an own rook or queen; of several - the closest to the centre (d, e, c, f, b, g,
    a, h). The side's first rook is highlighted - the one that can be put there.
    """
    rooks = list(board.pieces(chess.ROOK, color))
    if not rooks:
        return None
    heavy_files = {chess.square_file(s) for s in rooks + list(board.pieces(chess.QUEEN, color))}
    files = [f for f in (3, 4, 2, 5, 1, 6, 0, 7) if is_open_file(board, f) and f not in heavy_files]
    if not files:
        return None
    file = files[0]
    return Feature("open_file", {"file": chess.FILE_NAMES[file]}, tuple(rooks[:1]))


def _outpost(board: chess.Board, color: chess.Color) -> Feature | None:
    """Free outpost on files c-f if the side has a knight that can be brought there."""
    if not board.pieces(chess.KNIGHT, color):
        return None
    candidates = [s for s in chess.SQUARES if chess.square_file(s) in CENTRAL_FILES and is_outpost(board, s, color)]
    candidates = [s for s in candidates if board.piece_at(s) is None]
    if not candidates:
        return None
    square = _central_first(candidates)[0]
    return Feature("outpost", {"square": chess.square_name(square)}, (square,))


def _isolated_enemy(board: chess.Board, color: chess.Color) -> Feature | None:
    pawns = [p for p in board.pieces(chess.PAWN, not color)
             if chess.square_file(p) in CENTRAL_FILES and is_isolated(board, p, not color)]
    if not pawns:
        return None
    square = _central_first(pawns)[0]
    return Feature("isolated_enemy", {"square": chess.square_name(square)}, (square,))


def _shade(square: chess.Square) -> int:
    """Square colour: 0 is dark (like a1), 1 is light."""
    return (chess.square_file(square) + chess.square_rank(square)) % 2


def _king_holes(board: chess.Board, color: chess.Color) -> Feature | None:
    """
    Weak squares near the king on a wing (not in the endgame, king on the first rank). The parameter is the one nearest to
    the king "hole", the highlight is all of them.
    """
    king = board.king(color)
    if king is None or is_endgame(board) or _relative_rank(king, color) != 0:
        return None
    king_file = chess.square_file(king)
    if king_file in (3, 4):
        return None  # king in the centre - that is king_center
    holes = []
    # The third rank in front of the king: the king itself defends the square right in front of it, and the holes after
    # g3/h3 are f3, h3, g3.
    for file in range(max(0, king_file - 1), min(7, king_file + 1) + 1):
        square = chess.square(file, chess.square_rank(king) + 2 * _forward(color))
        if board.piece_at(square) == chess.Piece(chess.PAWN, color) or pawn_can_attack(board, square, color):
            continue
        shade = _shade(square)
        enemy_bishop = any(_shade(b) == shade for b in board.pieces(chess.BISHOP, not color))
        own_bishop = any(_shade(b) == shade for b in board.pieces(chess.BISHOP, color))
        if enemy_bishop and not own_bishop:
            holes.append(square)
    if not holes:
        return None
    nearest = min(holes, key=lambda s: (chess.square_distance(s, king), s))
    return Feature("king_holes", {"square": chess.square_name(nearest)}, tuple(holes))


def is_backward(board: chess.Board, square: chess.Square, color: chess.Color) -> bool:
    """
    Backward pawn of side color: the neighbouring pawns have advanced and will not defend it, and the square in front of it
    is attacked by an opponent pawn - it cannot advance.
    """
    file, rank = chess.square_file(square), _relative_rank(square, color)
    neighbours = [p for p in board.pieces(chess.PAWN, color) if abs(chess.square_file(p) - file) == 1]
    if not neighbours or any(_relative_rank(p, color) <= rank for p in neighbours):
        return False
    stop = square + 8 * _forward(color)
    if not 0 <= stop < 64:
        return False
    return any(board.piece_at(s) == chess.Piece(chess.PAWN, not color) for s in board.attackers(not color, stop))


def _backward_enemy(board: chess.Board, color: chess.Color) -> Feature | None:
    # A target of attack only if the file is half-open for us: an own pawn does not prevent pressing on it.
    own_files = {chess.square_file(p) for p in board.pieces(chess.PAWN, color)}
    pawns = [p for p in board.pieces(chess.PAWN, not color)
             if chess.square_file(p) not in own_files and is_backward(board, p, not color)]
    if not pawns:
        return None
    square = _central_first(pawns)[0]
    return Feature("backward_enemy", {"square": chess.square_name(square)}, (square,))


def _bad_bishop(board: chess.Board, color: chess.Color) -> Feature | None:
    """
    "Bad" bishop: on the squares of its colour there are at least three own pawns and more than half of all own pawns, at least
    two of them blocked by a piece or a pawn. The bishop and the blocked pawns are highlighted.
    """
    pawns = list(board.pieces(chess.PAWN, color))
    for bishop in board.pieces(chess.BISHOP, color):
        shade = (chess.square_file(bishop) + chess.square_rank(bishop)) % 2
        same = [p for p in pawns if (chess.square_file(p) + chess.square_rank(p)) % 2 == shade]
        blocked = [p for p in same if board.piece_at(p + 8 * _forward(color)) is not None]
        if len(same) >= 3 and len(same) * 2 > len(pawns) and len(blocked) >= 2:
            return Feature("bad_bishop", {"square": chess.square_name(bishop)}, (bishop, *blocked))
    return None


def _doubled_own(board: chess.Board, color: chess.Color) -> Feature | None:
    by_file: dict[int, list[chess.Square]] = {}
    for pawn in board.pieces(chess.PAWN, color):
        by_file.setdefault(chess.square_file(pawn), []).append(pawn)
    doubled = [squares for squares in by_file.values() if len(squares) >= 2]
    if not doubled:
        return None
    squares = min(doubled, key=lambda group: abs(chess.square_file(group[0]) - 3.5))
    return Feature("doubled_own", {"file": chess.FILE_NAMES[chess.square_file(squares[0])]}, tuple(squares))


def positional_features(board: chess.Board, color: chess.Color) -> list[Feature]:
    """Position features for the side color, in the order of POSITIONAL_PRIORITY."""
    found = [
        _king_center(board, color), _king_holes(board, color), _passed(board, color, own=False),
        _passed(board, color, own=True), _king_active(board, color), _open_file(board, color),
        _outpost(board, color), _isolated_enemy(board, color), _backward_enemy(board, color),
        _bad_bishop(board, color), _doubled_own(board, color),
    ]
    return [f for f in found if f is not None]


def move_idea(board: chess.Board, move: chess.Move) -> Feature | None:
    """
    Positional idea of a move (for a best move without a tactic): castling, a rook to an open file, a knight to an outpost,
    the king to the centre in the endgame, advancing a passed pawn. Checked in this order, the first is returned.
    Codes castle and passed_push exist only here - they are not in POSITIONAL_PRIORITY.
    """
    piece = board.piece_at(move.from_square)
    if piece is None:
        return None
    color = piece.color
    if board.is_castling(move):
        return Feature("castle")
    to_file = chess.square_file(move.to_square)
    if piece.piece_type == chess.ROOK and to_file != chess.square_file(move.from_square) and is_open_file(board, to_file):
        return Feature("open_file", {"file": chess.FILE_NAMES[to_file]}, (move.to_square,))
    if piece.piece_type == chess.KNIGHT and is_outpost(board, move.to_square, color):
        return Feature("outpost", {"square": chess.square_name(move.to_square)}, (move.to_square,))
    if piece.piece_type == chess.KING and is_endgame(board):
        def center_distance(square: chess.Square) -> float:
            return abs(chess.square_file(square) - 3.5) + abs(chess.square_rank(square) - 3.5)
        if center_distance(move.to_square) < center_distance(move.from_square):
            return Feature("king_active", {}, (move.to_square,))
    if piece.piece_type == chess.PAWN and is_passed(board, move.from_square, color):
        return Feature("passed_push", {}, (move.to_square,))
    return None
