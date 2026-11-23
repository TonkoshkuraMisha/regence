# --- FILE: src/services/mate_patterns.py ---
"""
Named mating patterns by the final position (task 13.4): lichess database puzzles have no tags for some of the mates
of catalogue section F -- this module recognises them by the arrangement of pieces in the mating position. Only
patterns with an unambiguous definition are recognised; disputed ones (Pillsbury's mate, Legal's mate as a sequence) are not
guessed -- better without a tag than with a wrong one.

* ``queen_kiss_mate`` -- the queen mates adjacent to the king and is protected by its own piece;
* ``damiano_mate`` -- the same, the queen on the edge file protected by a pawn;
* ``lolli_mate`` -- the same, the queen not on the edge protected by a pawn;
* ``epaulette_mate`` -- the queen mates from two squares on a file, at the king's sides are its own pieces (not pawns);
* ``opera_mate`` -- a rook mates adjacent to the king along its back rank, protected by a bishop;
* ``corridor_mate`` -- a rook/queen mates along the edge file, the exit to the side is closed by its own pieces;
* ``greco_mate`` -- the king in the corner, a rook/queen mates along the edge file, a bishop takes away the neighbouring
  square;
* ``morphy_mate`` -- the king in the corner, mate by a bishop, a rook takes away the neighbouring file;
* ``blackburne_mate`` -- a bishop mate to a king on the back rank after short castling (files f-h): the second
  bishop and a knight take away its neighbouring squares.

One position may get several tags (``queen_kiss_mate`` always accompanies ``damiano_mate`` and
``lolli_mate``). Who calls it: the puzzle import (src/services/puzzle_import.py) and the build of the extra theme sample
(scripts/dev/build_theme_extra.py) -- the tags are written as the puzzle's themes in puzzle_themes.
"""

import chess

CORNERS = {chess.A1, chess.A8, chess.H1, chess.H8}
EDGE_FILES = {0, 7}


def _distance(a: chess.Square, b: chess.Square) -> int:
    return chess.square_distance(a, b)


def _flights(board: chess.Board, king: chess.Square) -> list[chess.Square]:
    """
    All squares adjacent to the king -- both occupied and attacked: whether they are free is decided by each check itself.
    """
    return [s for s in chess.SQUARES if _distance(s, king) == 1]


def mate_patterns(board: chess.Board, last_move: chess.Move) -> list[str]:
    """
    Named patterns of a mating position (after ``last_move``); not a mate -- empty. The mating piece is taken to be the one
    that
    made the last move: whether it is the one giving check is not verified (a discovered mate is a rare case that may
    give an inaccurate tag). Its defenders are pieces of the mating side that attack its square.
    """
    if not board.is_checkmate():
        return []
    mated = board.turn
    attacker = not mated
    king = board.king(mated)
    mover = board.piece_at(last_move.to_square)
    if king is None or mover is None:
        return []
    m = last_move.to_square
    protectors = [board.piece_at(s) for s in board.attackers(attacker, m)]
    protector_types = {p.piece_type for p in protectors if p is not None}
    flights = _flights(board, king)
    back_rank = 0 if mated == chess.WHITE else 7
    k_file, k_rank = chess.square_file(king), chess.square_rank(king)
    m_file, m_rank = chess.square_file(m), chess.square_rank(m)
    found: list[str] = []

    if mover.piece_type == chess.QUEEN and _distance(m, king) == 1 and protector_types:
        found.append("queen_kiss_mate")
        if chess.PAWN in protector_types:
            found.append("damiano_mate" if m_file in EDGE_FILES else "lolli_mate")

    if mover.piece_type == chess.QUEEN and m_file == k_file and abs(m_rank - k_rank) == 2:
        sides = [chess.square(k_file + d, k_rank) for d in (-1, 1) if 0 <= k_file + d < 8]
        if len(sides) == 2 and all(board.color_at(s) == mated and board.piece_type_at(s) != chess.PAWN for s in sides):
            found.append("epaulette_mate")

    if (mover.piece_type == chess.ROOK and k_rank == back_rank and m_rank == k_rank and _distance(m, king) == 1
            and chess.BISHOP in protector_types):
        found.append("opera_mate")

    if mover.piece_type in (chess.ROOK, chess.QUEEN) and k_file in EDGE_FILES and m_file == k_file \
            and _distance(m, king) >= 2:
        side = [s for s in flights if chess.square_file(s) != k_file]
        if side and all(board.color_at(s) == mated for s in side):
            found.append("corridor_mate")

    if king in CORNERS and mover.piece_type in (chess.ROOK, chess.QUEEN) and m_file == k_file:
        rank_flights = [s for s in flights if chess.square_rank(s) == k_rank]
        if any(board.piece_type_at(a) == chess.BISHOP for s in rank_flights for a in board.attackers(attacker, s)):
            found.append("greco_mate")

    if king in CORNERS and mover.piece_type == chess.BISHOP:
        file_flights = [s for s in flights if chess.square_file(s) != k_file]
        if any(board.piece_type_at(a) == chess.ROOK for s in file_flights for a in board.attackers(attacker, s)):
            found.append("morphy_mate")

    if mover.piece_type == chess.BISHOP and k_rank == back_rank and k_file >= 5:
        helpers = {board.piece_type_at(a) for s in flights for a in board.attackers(attacker, s) if a != m}
        if chess.BISHOP in helpers and chess.KNIGHT in helpers:
            found.append("blackburne_mate")

    return found


def patterns_for_solution(fen: str, moves: list[str]) -> list[str]:
    """Patterns of the final position of a puzzle solution (if the solution ends with mate)."""
    board = chess.Board(fen)
    for uci in moves:
        board.push_uci(uci)
    return mate_patterns(board, board.peek()) if board.move_stack else []
