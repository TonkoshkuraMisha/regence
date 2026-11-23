"""
Odds in a game with a person (task 21.1, network - 16.11): the same odds as in a game with a bot
(frontend/src/components/chessboard/odds.ts).
Material - the starting position without a piece of the odds giver (queen's knight, queen's rook - without long castling,
queen, f-pawn); by time - the giver has a third of the time (at least a minute); "hourglass" - the time spent
by the mover is added to the opponent (common to both, there is no giver; the clock is counted by
src/services/game_state.py by the
flag games.hourglass). A game with odds does not change the rating.

The odds are set in the invitation link; they are applied by src/services/matchmaker.py (``_odds_start``) at the start,
when the colours are already known - it also makes the game casual. Here is only the calculation of position and time.
"""

import chess

# Kind of material odds -> the square of the removed piece if white gives the odds and if black does.
MATERIAL = {"knight": ("b1", "b8"), "rook": ("a1", "a8"), "queen": ("d1", "d8"), "pawn": ("f2", "f7")}
HOURGLASS = "hourglass"  # "hourglass": the position and starting time are ordinary, only the clock running changes
KINDS = (*MATERIAL, "time", HOURGLASS)  # all odds kinds; an empty string in the invitation - a game without odds
GIVERS = ("creator", "acceptor")  # who gives the odds: the invitation author or the one who accepted it


def odds_fen(kind: str, giver: chess.Color) -> str | None:
    """Starting position with material odds; None - the odds are not material."""
    squares = MATERIAL.get(kind)
    if squares is None:
        return None
    board = chess.Board()
    board.remove_piece_at(chess.parse_square(squares[0 if giver == chess.WHITE else 1]))
    if kind == "rook":
        board.castling_rights &= ~(chess.BB_A1 if giver == chess.WHITE else chess.BB_A8)
    return board.fen()


def odds_times(kind: str, giver: chess.Color, base_ms: int) -> tuple[int, int]:
    """
    Starting time of white and black. Time odds: the giver has a third of the base time, but at least a minute;
    the opponent has the full time. The lower bound is not compared with the base time: with a control shorter than
    a minute the giver would get more than the opponent.
    """
    if kind != "time":
        return base_ms, base_ms
    cut = max(60_000, round(base_ms / 3))
    return (cut, base_ms) if giver == chess.WHITE else (base_ms, cut)


def pgn_header(start_fen: str) -> str:
    """
    The start of a game's PGN from a position: SetUp/FEN headers - the server move check and the client understand
    them. A Fischer game (position in Shredder-FEN, game_engine.is_chess960_fen) also gets the Variant header.
    """
    from src.services.game_engine import CHESS960_HEADER, is_chess960_fen

    variant = f"{CHESS960_HEADER}\n" if is_chess960_fen(start_fen) else ""
    return f'{variant}[SetUp "1"]\n[FEN "{start_fen}"]'
