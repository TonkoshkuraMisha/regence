"""
"Beautiful game" mark (task 27.5): a material sacrifice followed by the winner delivering mate.

The rule needs no engine or database, it works on the game's moves: the winner mates, and in the last MATE_WINDOW_PLIES
half-moves before the mate
gave up at least SACRIFICE_MIN_POINTS points of material (values as in exchanges: pawn 1, minor piece 3,
rook 5, queen 9). An exchange does not count: while the winner takes as much as they give, the difference does not drop.
The mark is set on import (`services/library.py`) and by the script `scripts/tag_library.py --all`; it is searched with the
filter
`beautiful` in `GET /library/games`. The "long forced line" from the 27.5 plan requires an engine and is not searched for here.
"""

import chess

PIECE_POINTS = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
SACRIFICE_MIN_POINTS = 3  # at least a pawn triple given up: a piece for a pawn is already a sacrifice
MATE_WINDOW_PLIES = 14  # the sacrifice and the mate are one combination: no more than seven moves apart


def _material(board: chess.Board, color: chess.Color) -> int:
    """Material of a side in points (without the king)."""
    return sum(len(board.pieces(kind, color)) * points for kind, points in PIECE_POINTS.items())


def is_beautiful(start_fen: str | None, moves: list[str]) -> bool:
    """The winner delivered mate, giving up at least SACRIFICE_MIN_POINTS points of material in the last moves."""
    board = chess.Board(start_fen) if start_fen else chess.Board()
    balances: list[int] = []  # White's advantage after each half-move, including the starting position
    try:
        balances.append(_material(board, chess.WHITE) - _material(board, chess.BLACK))
        for uci in moves:
            board.push(chess.Move.from_uci(uci))
            balances.append(_material(board, chess.WHITE) - _material(board, chess.BLACK))
    except (ValueError, AssertionError):
        return False
    if not board.is_checkmate():
        return False
    winner = not board.turn  # the mate was received by the side to move
    sign = 1 if winner == chess.WHITE else -1
    window = balances[-(MATE_WINDOW_PLIES + 1):]
    peak = max(sign * value for value in window)  # the winner's best moment in the window
    return peak - sign * window[-1] >= SACRIFICE_MIN_POINTS
