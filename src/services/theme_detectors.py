"""
Recognition of themes without a tag in the open puzzle database (task 27.8, filling the "M" themes): from a position and a
puzzle's solution - which technique it shows. Only python-chess rules, no engine; each rule is conservative (better to skip
a puzzle than attribute a foreign theme to it). The input is as in the database: the FEN before the opponent's move, the
moves (the first is the opponent's), the database tags.

Themes: Greek gift, double bishop sacrifice, windmill, perpetual check and stalemate trap (also "save the game"),
pawn breakthrough and pawn race, opposition, Lucena, Philidor, rook behind a passed pawn, "wrong" bishop, simplest mates,
opening trap, early queen, development lag, combination, rook lift, seventh rank, isolated pawn,
inevitable threat, domination, undermining the defender, exploiting a pin.

Called by puzzle_import.py when parsing rows of the open lichess database (detect). Tactical techniques for the
"combination" theme - by database tags through themes.themes_for_lichess_tags.
"""

import chess

from src.services import pawn_structures

# Codes of the registry's tactical techniques: two or more of them in one puzzle give the "combination" theme.
TACTICS = {"fork", "pin", "skewer", "discovered_attack", "double_check", "deflection", "decoy", "remove_defender",
           "interference", "clearance", "intermezzo", "x_ray", "overload", "trapped_piece", "hanging_piece", "sacrifice"}


def _relative_rank(square: chess.Square, color: chess.Color) -> int:
    """Rank number from the side's point of view: 0 is its first, 7 is the last."""
    rank = chess.square_rank(square)
    return rank if color == chess.WHITE else 7 - rank


def _only(board: chess.Board, kinds: set[int]) -> bool:
    """The board has, apart from the kings, only pieces of the listed kinds."""
    return all(piece.piece_type in kinds | {chess.KING} for piece in board.piece_map().values())


def _material(board: chess.Board, color: chess.Color) -> list[int]:
    """Piece kinds of a side without the king, in ascending order (for comparison with a list like [PAWN, ROOK])."""
    return sorted(p.piece_type for p in board.piece_map().values() if p.color == color and p.piece_type != chess.KING)


def _passed(board: chess.Board, square: chess.Square, color: chess.Color) -> bool:
    """The pawn of side color on square is passed: no opponent pawns ahead on its file and the neighbouring files."""
    file, rank = chess.square_file(square), chess.square_rank(square)
    for other in board.pieces(chess.PAWN, not color):
        o_file, o_rank = chess.square_file(other), chess.square_rank(other)
        if abs(o_file - file) <= 1 and ((o_rank > rank) if color == chess.WHITE else (o_rank < rank)):
            return False
    return True


def _discovered_check(board: chess.Board, move: chess.Move) -> bool:
    """The move gives check with a piece other than the one that moved (discovered check)."""
    if not board.gives_check(move):
        return False
    after = board.copy(stack=False)
    after.push(move)
    king = after.king(after.turn)
    return king is not None and any(sq != move.to_square for sq in after.checkers())


def detect(fen: str, moves: list[str], tags: list[str]) -> list[str]:
    """
    Registry theme codes that the puzzle shows, in order of detection. fen - the position before the opponent's move, moves
    - UCI (the opponent's first move, then the solution), tags - database tags. An empty list - no themes found or the data
    cannot be parsed.
    """
    found: list[str] = []

    def add(*codes: str) -> None:
        for code in codes:
            if code not in found:
                found.append(code)

    try:
        board = chess.Board(fen)
        board.push_uci(moves[0])
    except (ValueError, IndexError):
        return found
    solver = board.turn
    start = board.copy(stack=False)
    line = [chess.Move.from_uci(u) for u in moves[1:]]
    tagset = set(tags)

    solver_moves: list[tuple[chess.Board, chess.Move]] = []
    current = board.copy(stack=False)
    for index, move in enumerate(line):
        if move not in current.legal_moves:
            return found
        if index % 2 == 0:
            solver_moves.append((current.copy(stack=False), move))
        current.push(move)
    final = current
    if not solver_moves:
        return found
    first_board, first = solver_moves[0]
    mover = first_board.piece_at(first.from_square)

    # Greek gift: a bishop takes h7 (h2) with check to the king on g8 (g1).
    target, king_square = (chess.H7, chess.G8) if solver == chess.WHITE else (chess.H2, chess.G1)
    bishop_takes_h = [(b, m) for b, m in solver_moves
                      if m.to_square == target and b.piece_type_at(m.from_square) == chess.BISHOP and b.is_capture(m)]
    if (bishop_takes_h and first.to_square == target and start.king(not solver) == king_square
            and first_board.gives_check(first)):
        add("greek_gift", "sacrifice")
    # Double bishop sacrifice: the bishops take h7 and g7 (h2 and g2).
    g_square = chess.G7 if solver == chess.WHITE else chess.G2
    if bishop_takes_h and any(m.to_square == g_square and b.piece_type_at(m.from_square) == chess.BISHOP and b.is_capture(m)
                              for b, m in solver_moves):
        add("double_bishop_sacrifice", "sacrifice")

    # Windmill: two or more discovered checks, at least one with a capture.
    discovered = [(b, m) for b, m in solver_moves if _discovered_check(b, m)]
    if len(discovered) >= 2 and any(b.is_capture(m) for b, m in discovered):
        add("windmill")

    # Save the game: perpetual check (all the solver's moves are checks, the result is equality) and a stalemate trap.
    if "equality" in tagset and len(solver_moves) >= 2 and all(b.gives_check(m) for b, m in solver_moves):
        add("perpetual_check", "save_by_perpetual")
    if final.is_stalemate():
        add("stalemate_trick", "save_by_stalemate")

    # Pawn endings.
    if _only(start, {chess.PAWN}):
        promotes = any(m.promotion for _, m in solver_moves)
        if promotes and mover and mover.piece_type == chess.PAWN:
            # Breakthrough - a pawn goes under attack (a sacrifice), race - free passed pawns on both sides.
            if first_board.is_attacked_by(not solver, first.to_square):
                add("pawn_breakthrough")
            elif _passed(first_board, first.from_square, solver) and any(
                    _passed(first_board, sq, not solver) for sq in first_board.pieces(chess.PAWN, not solver)):
                add("pawn_race")
        if mover and mover.piece_type == chess.KING:
            after = first_board.copy(stack=False)
            after.push(first)
            own, other = after.king(solver), after.king(not solver)
            if own is not None and other is not None:
                df = abs(chess.square_file(own) - chess.square_file(other))
                dr = abs(chess.square_rank(own) - chess.square_rank(other))
                if (df, dr) in ((0, 2), (2, 0)):
                    add("opposition")

    # Rook endings: Lucena, Philidor, rook behind a passed pawn.
    mine, theirs = _material(start, solver), _material(start, not solver)
    if mine == [chess.PAWN, chess.ROOK] and theirs == [chess.ROOK]:
        pawn = next(iter(start.pieces(chess.PAWN, solver)))
        king = start.king(solver)
        if _relative_rank(pawn, solver) == 6 and king is not None and _relative_rank(king, solver) == 7:
            add("lucena")
    if mine == [chess.ROOK] and theirs == [chess.PAWN, chess.ROOK] and {"equality", "defensiveMove"} & tagset:
        add("philidor_position")
    if mover and mover.piece_type == chess.ROOK and "rookEndgame" in tagset:
        file = chess.square_file(first.to_square)
        for pawn in first_board.pieces(chess.PAWN, solver):
            ahead = (chess.square_rank(pawn) > chess.square_rank(first.to_square)) == (solver == chess.WHITE)
            if chess.square_file(pawn) == file and ahead and _passed(first_board, pawn, solver):
                add("rook_behind_passer")
    # The "wrong" bishop: a bishop and edge pawns against a king, the promotion square is not the bishop's colour - the
    # solver defends.
    if not mine and theirs and set(theirs) <= {chess.BISHOP, chess.PAWN} and theirs.count(chess.BISHOP) == 1:
        pawns = start.pieces(chess.PAWN, not solver)
        bishop = next(iter(start.pieces(chess.BISHOP, not solver)))
        files = {chess.square_file(p) for p in pawns}
        if pawns and files <= {0} | {7} and len(files) == 1:
            attacker_rank = 7 if solver == chess.BLACK else 0  # promotion square of the stronger side
            corner = chess.square(files.pop(), attacker_rank)
            light = chess.BB_LIGHT_SQUARES
            if bool(chess.BB_SQUARES[corner] & light) != bool(chess.BB_SQUARES[bishop] & light):
                add("wrong_bishop")

    # Simplest mates: no more than four pieces on the board including the kings.
    if final.is_checkmate() and len(start.piece_map()) <= 4:
        add("basic_mates")

    # Opening: trap, early queen, development lag.
    if "opening" in tagset and start.fullmove_number <= 12 and ({"mate", "crushing"} & tagset or final.is_checkmate()):
        add("opening_trap")
        queen_home = chess.D8 if solver == chess.WHITE else chess.D1
        enemy_queens = start.pieces(chess.QUEEN, not solver)
        if start.fullmove_number <= 10 and enemy_queens and queen_home not in enemy_queens and any(
                b.piece_type_at(m.to_square) == chess.QUEEN and b.color_at(m.to_square) != solver for b, m in solver_moves):
            add("early_queen")
        home = [chess.B8, chess.C8, chess.F8, chess.G8] if solver == chess.WHITE else [chess.B1, chess.C1, chess.F1, chess.G1]
        if sum(1 for sq in home if start.piece_type_at(sq) in (chess.KNIGHT, chess.BISHOP)
               and start.color_at(sq) != solver) >= 3:
            add("development_lag")

    # Calculation: combination - two or more tactical techniques in one puzzle (by database tags).
    from src.services.themes import themes_for_lichess_tags

    if len(set(themes_for_lichess_tags(tags)) & TACTICS) >= 2:
        add("combination")
    # Inevitable threat: a quiet move after which mate is unavoidable.
    if "quietMove" in tagset and ({"mate"} & tagset or final.is_checkmate()):
        add("unstoppable_threat")
    # Domination: trapping a piece with a quiet move.
    if "trappedPiece" in tagset and "quietMove" in tagset:
        add("domination")
    # Undermining the defender: the defender is destroyed by a pawn strike.
    if "capturingDefender" in tagset and mover and mover.piece_type == chess.PAWN and first_board.is_capture(first):
        add("undermining")
    # Exploiting a pin: the solver attacks the opponent's pinned piece.
    if "pin" in tagset and first_board.is_capture(first) and first_board.is_pinned(not solver, first.to_square):
        add("pin_exploit")

    # Attack: a rook lift along the third rank to the king.
    for index, (b, m) in enumerate(solver_moves):
        if b.piece_type_at(m.from_square) == chess.ROOK and _relative_rank(m.to_square, solver) == 2 and \
                _relative_rank(m.from_square, solver) == 0:
            later = [(b2, m2) for b2, m2 in solver_moves[index + 1:] if m2.from_square == m.to_square]
            if later and (later[0][0].gives_check(later[0][1]) or chess.square_file(later[0][1].to_square) in (6, 7)):
                add("rook_lift")
                break
    # Seventh rank: the solver's rook breaks into the 7th (2nd) rank with check or capture.
    if any(b.piece_type_at(m.from_square) == chess.ROOK and _relative_rank(m.to_square, solver) == 6
           and (b.gives_check(m) or b.is_capture(m)) for b, m in solver_moves):
        add("seventh_rank")
    # A position with an isolated pawn (structure 27.5).
    if pawn_structures.detect(start) == "isolated_pawn":
        add("isolated_pawn")
    return found
