# --- FILE: src/services/guess_selection.py ---
"""
Selection of positions for "Guess the master's move" (task 14.3). The owner's requirement: positions are objectively solvable
-- the player finds
the move by calculation and understanding rather than guessing what the master had in mind. The rules (on the engine output,
MultiPV >= 2):

* the master's move is the engine's best move and leads the second by at least GAP_CP; or only it keeps the result: for the
  other
  moves it is "win -> equality" or "equality -> loss";
* the move is not obvious: not the only legal one, not a capture in reply to a capture on the same square, not the capture of
  a hanging piece
  worth more than a pawn that is visible without calculation;
* the position is outside the book opening -- after the last game position from the openings table 16.1
  (src/services/openings.py) and
  no earlier than ply OPENING_FLOOR_PLY (side openings that are not in the table are development all the same);
* not a technical endgame: with TECHNICAL_PIECES pieces or fewer the answer is known to the endgame tablebases -- that is
  technique,
  not understanding (for it there is the endgame trainer 14.4);
* the position is not yet decided: the best move is no worse than -DECIDED_CP, and the second is no better than +DECIDED_CP
  (otherwise anything
  wins).

The position's themes are the same as for puzzles (src/services/puzzle_import.themes_for_row): the master's move and the
engine continuation
as the solution, the previous move of the game as the opponent's move.

Series: 2-6 consecutive player moves, each passes the selection, the opponent's moves between them are the game's moves; if
the opponent erred
by more than OPPONENT_ERROR_CP the series breaks there.

The module is pure: selection rules without an engine and without a database. The engine is run by the script
scripts/build_guess_positions.py -- it
passes the engine lines here and writes the passing positions to the guess_positions table; serving is src/services/guess.py.
"""

from dataclasses import dataclass

import chess

from src.services import openings

# Thresholds are in centipawns from the point of view of the side to move.
GAP_CP = 150              # the best move leads the second by at least this much
WIN_CP = 150              # "win": the evaluation is at least this (for the rule "only this move keeps the result")
EQUAL_CP = 50             # "equality": the evaluation modulus is at most this
DECIDED_CP = 700          # decided position: best move below -DECIDED_CP or second above +DECIDED_CP
OPENING_FLOOR_PLY = 10    # before this ply the position counts as opening even if it is not in the openings table
TECHNICAL_PIECES = 7      # this many pieces on the board (with kings and pawns) or fewer -- a technical endgame
THEME_LINE_PLIES = 4  # the master's move and three more plies of the engine line
MAX_MATE_IN = 5           # a longer mate is not tagged with the "mate in n" theme
OPPONENT_ERROR_CP = 100   # an opponent error larger than this between the moves of a series breaks the series
SERIES_MIN, SERIES_MAX = 2, 6  # the number of player moves in a series

# Piece values for the rule "a piece worth more than a pawn hangs".
VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}

# An engine line: the move and the evaluation in centipawns from the point of view of the side to move (mate -- +-100000).
Line = tuple[chess.Move, int]


@dataclass(frozen=True)
class Verdict:
    """
    Why the move passed the selection: gap -- a big lead over the second move, only_move -- only it keeps the result; the best
    evaluation and the lead over the second move in centipawns.
    """
    reason: str  # "gap" | "only_move"
    best_cp: int
    gap_cp: int


def is_obvious(board: chess.Board, move: chess.Move) -> bool:
    """A move made without calculation: the only one, a recapture or the capture of a hanging piece."""
    if board.legal_moves.count() <= 1:
        return True
    if board.is_capture(move) and board.move_stack:
        before = board.copy()
        previous = before.pop()
        if before.is_capture(previous) and previous.to_square == move.to_square:
            return True  # a capture in reply to a capture on the same square -- restoring material
    # A piece worth more than a pawn simply hangs -- it can be taken without calculation.
    captured = board.piece_type_at(move.to_square)
    return captured is not None and VALUES[captured] >= 3 and not board.attackers(not board.turn, move.to_square)


def book_plies(moves: list[chess.Move]) -> int:
    """How many plies the game followed the openings table: the number of the last position from the table (0 -- none)."""
    table = openings.lines()
    board = chess.Board()
    last = 0
    for ply, move in enumerate(moves[:openings.MAX_PLIES], 1):
        if move not in board.legal_moves:
            break
        board.push(move)
        if board.epd() in table:
            last = ply
    return last


def in_opening(board: chess.Board, book_ply: int) -> bool:
    """The move from this position is still opening: it leads to a table position or was made before ply OPENING_FLOOR_PLY."""
    return board.ply() < max(book_ply, OPENING_FLOOR_PLY)


def is_technical_endgame(board: chess.Board) -> bool:
    """
    The board has no more than TECHNICAL_PIECES pieces, counting kings and pawns: the answer is known to the endgame
    tablebases.
    """
    return len(board.piece_map()) <= TECHNICAL_PIECES


def qualifies(board: chess.Board, move: chess.Move, lines: list[Line], book_ply: int = 0) -> Verdict | None:
    """
    Whether the master's move passes the selection. board -- the position before the move (with the game's move stack or with
    the right move number in the FEN),
    lines -- the engine MultiPV, book_ply -- the result of book_plies for the game. None -- does not pass: opening, technical
    endgame, fewer than two engine lines, the master's move is not the best, the position is already decided, the move is
    obvious or the gap is small.
    """
    if in_opening(board, book_ply) or is_technical_endgame(board) or len(lines) < 2:
        return None
    ordered = sorted(lines, key=lambda line: line[1], reverse=True)
    (best_move, best), (_, second) = ordered[0], ordered[1]
    if best_move != move or best < -DECIDED_CP or second > DECIDED_CP:
        return None
    if is_obvious(board, move):
        return None
    if best - second >= GAP_CP:
        return Verdict("gap", best, best - second)
    if (best >= WIN_CP and second <= EQUAL_CP) or (best >= -EQUAL_CP and second <= -WIN_CP):
        return Verdict("only_move", best, best - second)
    return None


def build_series(passing_plies: list[int], opponent_errors: set[int]) -> list[list[int]]:
    """
    Series of plies of one side that passed the selection: consecutive (through the opponent's move), without an opponent
    error between them,
    of length SERIES_MIN-SERIES_MAX (long ones are cut into parts).
    """
    series: list[list[int]] = []
    current: list[int] = []
    for ply in sorted(passing_plies):
        if current and (ply != current[-1] + 2 or (ply - 1) in opponent_errors):
            series.append(current)
            current = []
        current.append(ply)
    if current:
        series.append(current)
    result = []
    for run in series:
        for start in range(0, len(run), SERIES_MAX):
            chunk = run[start:start + SERIES_MAX]
            if len(chunk) >= SERIES_MIN:
                result.append(chunk)
    return result


def difficulty(board: chess.Board, move: chess.Move, verdict: Verdict) -> int:
    """
    Difficulty as a puzzle rating: a quiet move and an "only move" are harder, a big gap is easier. The initial value is
    1500; a move without capture and check +200, an "only move" +100, a gap of 400 centipawns or more -200. After that the
    position's rating is
    refined by players' answers (guess.rating_after).
    """
    value = 1500
    if not board.is_capture(move) and not board.gives_check(move):
        value += 200
    if verdict.reason == "only_move":
        value += 100
    if verdict.gap_cp >= 400:
        value -= 200
    return value


def _mate_length(board: chess.Board, line: list[chess.Move]) -> int | None:
    """The number of the master side's moves to mate if the line ends with its mate (no longer than MAX_MATE_IN)."""
    current = board.copy(stack=False)
    for index, move in enumerate(line[:2 * MAX_MATE_IN - 1]):
        if move not in current.legal_moves:
            return None
        current.push(move)
        if current.is_checkmate():
            return index // 2 + 1 if index % 2 == 0 else None
    return None


def position_themes(board: chess.Board, move: chess.Move, pv: list[chess.Move]) -> list[str]:
    """
    Theme codes of registry 13.0 for a position: as for a puzzle -- the game's previous move as the "opponent's move", the
    master's move and
    the engine continuation (up to THEME_LINE_PLIES plies, and with a forced mate -- up to the mate) as the solution; mate in
    n moves
    is tagged the same way as in the puzzle database (mateIn<n>). Without a previous move -- empty.
    """
    from src.services.puzzle_import import themes_for_row

    if not board.move_stack:
        return []
    before = board.copy()
    previous = before.pop()
    line = [move, *pv[1:]] if pv and pv[0] == move else [move]
    mate_in = _mate_length(board, line)
    tags = f"mateIn{mate_in}" if mate_in else ""
    line = line[:2 * mate_in - 1] if mate_in else line[:THEME_LINE_PLIES]
    return themes_for_row({"FEN": before.fen(), "Moves": " ".join(m.uci() for m in [previous, *line]), "Themes": tags})
