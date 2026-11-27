# --- FILE: tests/test_lesson_miner_rules.py ---
"""
Pure motif rules of the lesson position miner (scripts/dev/mine_lesson_positions.py) added for the strategy modules:
knight_outpost (S3.8, a knight on a central pawn-guarded square no enemy pawn can reach) and minor_exchange (S4.10, a
minor piece trades itself for a defended enemy minor piece). The engine part of the miner is not run here.
"""

import chess

from scripts.dev.mine_lesson_positions import rule_knight_outpost, rule_minor_exchange

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
