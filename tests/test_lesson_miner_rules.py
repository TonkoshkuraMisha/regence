# --- FILE: tests/test_lesson_miner_rules.py ---
"""
Pure motif rules of the lesson position miner (scripts/dev/mine_lesson_positions.py) added for the Great Course modules
of levels 3-5: knight_outpost (S3.8), minor_exchange (S4.10), restriction (S4.8), worst_piece and prophylaxis (S4.9),
critical (S5.1), quiet_over_forcing (C5.1) and greedy_refuted (C4.1). Fixtures are positions of the lessons built from
them. The engine part of the miner is not run here.
"""

import chess

from scripts.dev.mine_lesson_positions import (
    rule_critical,
    rule_greedy_refuted,
    rule_knight_outpost,
    rule_minor_exchange,
    rule_prophylaxis,
    rule_quiet_over_forcing,
    rule_restriction,
    rule_worst_piece,
)

# Korchnoi - Ekstroem 2010: ...e3 takes many squares from White's rooks and pawns.
EKSTROEM = "4r3/p5k1/1p4pp/2pPr3/P1P1p3/6RP/6P1/4R1K1 b - - 0 38"
# Keres - Bondarevsky 1941 (lesson strategy-worst-piece): the idle rook f1 goes to the open c-file.
BONDAREVSKY = "8/2R1bkpp/pr2pp2/1p1r4/1P6/PN4P1/4PP1P/5RK1 w - - 2 30"
# Rubinstein - Lowcki 1927 (lesson strategy-worst-piece): Ng2 closes the diagonal h3-f1 before ...Bxf1.
LOWCKI = "r2r2k1/p1q1bppp/1p1p1nn1/2pPp3/2P1P3/PP1B2Pb/1B1NQP1P/2R1NRK1 w - - 3 17"

# Rubinstein - Salwe 1905 (lesson strategy-centralisation): ...Nd4 is protected by e5, and White has no pawn for c3/e3.
SALWE = "1r6/5kpp/2n2p2/4p3/4P1P1/1p1K1P2/1R4P1/N7 b - - 1 44"
# Steinitz - Bird 1866: Bxe7 trades the bishop for the bishop e7, which the queen d8 defends.
BIRD = "r2q1rk1/pp1nbppp/4b3/3p2B1/8/2N2P2/PPPQN1PP/2KR3R w - - 0 14"


def test_knight_outpost_takes_a_pawn_guarded_central_square():
    board = chess.Board(SALWE)
    assert rule_knight_outpost(board, chess.Move.from_uci("c6d4"))
    assert not rule_knight_outpost(board, chess.Move.from_uci("c6a5"))  # the rim is not the centre
    assert not rule_knight_outpost(board, chess.Move.from_uci("c6b4"))  # no own pawn guards b4


def test_knight_outpost_refuses_a_square_an_enemy_pawn_can_reach():
    # The same knight jump, but White has a pawn on c2 that can go to c3 and attack d4.
    board = chess.Board("1r6/5kpp/2n2p2/4p3/4P1P1/1p1K1P2/1RP3P1/N7 b - - 1 44")
    assert not rule_knight_outpost(board, chess.Move.from_uci("c6d4"))


def test_minor_exchange_is_a_trade_of_minor_pieces():
    board = chess.Board(BIRD)
    assert rule_minor_exchange(board, chess.Move.from_uci("g5e7"))
    assert not rule_minor_exchange(board, chess.Move.from_uci("g5f4"))  # not a capture
    assert not rule_minor_exchange(board, chess.Move.from_uci("c3d5"))  # takes a pawn, not a piece


def test_minor_exchange_skips_a_recapture():
    # The white knight on c6 is defended by the pawn b5; ...Bxc6 trades the bishop for it.
    standing = chess.Board("4k3/1b6/2N5/1P6/8/8/8/4K3 b - - 0 20")
    assert rule_minor_exchange(standing, chess.Move.from_uci("b7c6"))
    # The same picture right after Nd4xc6: taking back on c6 is a recapture, not a choice of exchange.
    recapture = chess.Board("4k3/1b6/2n5/1P6/3N4/8/8/4K3 w - - 0 20")
    recapture.push(chess.Move.from_uci("d4c6"))
    assert not rule_minor_exchange(recapture, chess.Move.from_uci("b7c6"))


def test_restriction_takes_squares_away():
    board = chess.Board(EKSTROEM)
    assert rule_restriction(board, chess.Move.from_uci("e4e3"))
    assert not rule_restriction(board, chess.Move.from_uci("h6h5"))  # a pawn move that squeezes nothing


def test_worst_piece_is_the_least_mobile_one_going_active():
    board = chess.Board(BONDAREVSKY)
    assert rule_worst_piece(board, chess.Move.from_uci("f1c1"))
    assert not rule_worst_piece(board, chess.Move.from_uci("b3c5"))  # the knight is not the worst piece


def test_prophylaxis_removes_the_threat_without_running_away():
    board = chess.Board(LOWCKI)
    assert rule_prophylaxis(board, chess.Move.from_uci("e1g2"))  # the line h3-f1 is closed
    assert not rule_prophylaxis(board, chess.Move.from_uci("f1e1"))  # the threatened rook simply leaves


# Steinitz - Blackburne 1862 (lesson strategy-critical-position): pieces in contact, captures for both sides.
BLACKBURNE = "4rrk1/pbpqnp1p/1p1p1npb/5PQ1/3P4/2NB2N1/PPP3PP/R4RK1 w - - 0 15"
# Steinitz - Robey 1862 (lesson calc-creative): the quiet retreat Bd1 while captures were available.
ROBEY = "6k1/b1p3pp/p1np1p2/4pP2/qB2P1B1/2PP3P/6P1/1Q5K w - - 2 27"
# Steinitz - Lenhof 1859 (lesson calc-technique): Bxc6 is possible, the master played d5.
LENHOF = "r1b1k1nr/bppq1ppp/p1np4/8/B2PP3/1Q3N2/P4PPP/RNB2RK1 w kq - 2 12"


def test_critical_needs_tension():
    assert rule_critical(chess.Board(BLACKBURNE), chess.Move.from_uci("g5h6"))
    calm = chess.Board("6k1/5ppp/8/8/8/8/5PPP/6K1 w - - 0 20")
    assert not rule_critical(calm, chess.Move.from_uci("g1f1"))


def test_quiet_over_forcing_skips_the_captures_themselves():
    board = chess.Board(ROBEY)
    assert rule_quiet_over_forcing(board, chess.Move.from_uci("g4d1"))
    assert not rule_quiet_over_forcing(board, chess.Move.from_uci("b4d6"))  # a capture is not the quiet choice


def test_greedy_refuted_is_a_non_capture_next_to_a_tempting_capture():
    board = chess.Board(LENHOF)
    assert rule_greedy_refuted(board, chess.Move.from_uci("d4d5"))
    assert not rule_greedy_refuted(board, chess.Move.from_uci("a4c6"))  # the capture itself
