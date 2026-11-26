"""
Thematic master game candidates (task 27.7, scripts/dev/theme_games.py): the idea detectors on fixed positions and the
game filter (decisive, classical, not a simultaneous exhibition, long enough).
"""

import chess

from scripts.dev import theme_games as tg

# White knight on d5, no black c- or e-pawn can drive it away, defended by the e4 pawn.
OUTPOST = "4k3/pp3ppp/3p4/3N4/4P3/8/PPP2PPP/4K3 w - - 0 1"
# The same knight on a5: an edge square is not the idea of the S2.2 module.
EDGE_KNIGHT = "4k3/1p3ppp/3p4/N7/1P6/8/P1P2PPP/4K3 w - - 0 1"
# Black's isolated d5 pawn, White to press it.
IQP = "4k3/pp3ppp/8/3p4/8/8/PP3PPP/4K3 w - - 0 1"
SHORT = '[Event "Test"]\n[White "A"]\n[Black "B"]\n[Result "1-0"]\n\n1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0\n'


def test_knight_outpost_in_the_centre_only():
    assert tg._knight_outpost(chess.Board(OUTPOST), chess.WHITE, chess.BLACK) == "d5"
    assert tg._knight_outpost(chess.Board(EDGE_KNIGHT), chess.WHITE, chess.BLACK) is None


def test_isolated_pawn_of_the_loser():
    assert tg._weak_pawn(chess.Board(IQP), chess.WHITE, chess.BLACK) == "d5"
    assert tg._weak_pawn(chess.Board(), chess.WHITE, chess.BLACK) is None


def test_short_draw_and_simul_games_are_not_candidates():
    assert tg.score("outpost", SHORT) is None
    assert tg.score("outpost", SHORT.replace('"1-0"', '"1/2-1/2"').replace("1-0\n", "1/2-1/2\n")) is None
    assert tg.SPECIAL.search("GBR tour sim") and tg.SPECIAL.search("Casablanca Chess 2024")
    assert not tg.SPECIAL.search("Simferopol")


def test_uncastled_king_of_the_loser_from_move_eight():
    # Move 10, Black's king still on e8, White has the queen: the mentor's king_center rule speaks.
    stuck = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1 w kq - 0 10")
    assert tg._king_center(stuck, chess.WHITE, chess.BLACK) == "e8"
    stuck.fullmove_number = 5  # the opening is still on: silent
    assert tg._king_center(stuck, chess.WHITE, chess.BLACK) is None
    assert tg.THEMES["king_center"].from_move == 8 and tg.THEMES["king_center"].max_moves < tg.THEMES["outpost"].max_moves
