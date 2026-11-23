# --- FILE: tests/test_positional.py ---
"""Positional features and move ideas for the coach (task B.4)."""

import chess

from src.services.coach import advice_for_position, hint_for_position
from src.services.positional import is_outpost, move_idea, positional_features


def codes(fen: str) -> list[str]:
    board = chess.Board(fen)
    return [f.code for f in positional_features(board, board.turn)]


def test_king_in_the_centre_in_the_middlegame():
    # Move 10, queens on the board, the white king on e1 has not castled.
    assert codes("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R w KQkq - 0 10")[0] == "king_center"


def test_passed_pawns_own_and_enemy():
    assert "passed_own" in codes("4k3/8/8/3P4/8/8/8/4K3 w - - 0 40")
    found = codes("4k3/8/8/8/3p4/8/8/4K3 w - - 0 40")
    assert "passed_enemy" in found and "king_active" in found


def test_blockaded_enemy_passer_is_not_named():
    assert "passed_enemy" not in codes("4k3/8/8/8/3p4/3N4/8/4K3 w - - 0 40")


def test_open_file_for_a_rook():
    board = chess.Board("4k3/pp3ppp/8/8/8/8/PP3PPP/R3K3 w - - 0 25")
    feature = next(f for f in positional_features(board, chess.WHITE) if f.code == "open_file")
    assert feature.params == {"file": "d"}


def test_outpost_is_protected_and_safe_from_pawns():
    # d5 is protected by the e4 pawn; the opponent's c7 pawn can still reach c6 and drive the knight away.
    assert not is_outpost(chess.Board("4k3/1pp3pp/8/8/4P3/2N5/PP3PPP/4K3 w - - 0 25"), chess.D5, chess.WHITE)
    # The opponent has no c or e pawns: d5 is an outpost.
    board = chess.Board("4k3/6pp/8/8/4P3/2N5/PP3PPP/4K3 w - - 0 25")
    assert is_outpost(board, chess.D5, chess.WHITE)
    # Not protected by an own pawn: not an outpost.
    assert not is_outpost(board, chess.C5, chess.WHITE)
    assert move_idea(board, chess.Move.from_uci("c3d5")).code == "outpost"


def test_isolated_enemy_pawn_and_doubled_own():
    found = codes("4k3/pp3ppp/8/3p4/8/2P5/P1P2PPP/4K3 w - - 0 25")
    assert "isolated_enemy" in found and "doubled_own" in found


def test_holes_in_front_of_the_castled_king():
    # After g3 the f3 and h3 squares cannot be covered by a pawn; Black has a light-squared bishop on b7, White has none.
    holes = "6k1/1b3ppp/8/8/8/6P1/5P1P/3Q2K1 w - - 0 20"
    feature = next(f for f in positional_features(chess.Board(holes), chess.WHITE) if f.code == "king_holes")
    assert feature.params == {"square": "f3"} and set(feature.squares) == {chess.F3, chess.H3}
    # An own light-squared bishop covers the weakness; the untouched f2-g2-h2 cover gives no holes.
    assert "king_holes" not in codes("6k1/1b3ppp/8/8/8/6P1/4BP1P/3Q2K1 w - - 0 20")
    assert "king_holes" not in codes("6k1/1b3ppp/8/8/8/8/5PPP/3Q2K1 w - - 0 20")


def test_backward_enemy_pawn_on_a_half_open_file():
    # d6 lags behind e5, the d5 square is attacked by the c4 and e4 pawns, White has no d-pawn.
    board = chess.Board("6k1/pp3ppp/3p4/4p3/2P1P3/8/PP3PPP/6K1 w - - 0 20")
    feature = next(f for f in positional_features(board, chess.WHITE) if f.code == "backward_enemy")
    assert feature.params == {"square": "d6"}
    # An own pawn on the d-file prevents pressure on d6: there is no target to attack.
    assert "backward_enemy" not in codes("6k1/pp3ppp/3p4/4p3/2P1P3/3P4/PP3PPP/6K1 w - - 0 20")


def test_king_holes_advice_sentence():
    advice = advice_for_position(chess.Board("6k1/1b3pp1/7p/8/8/6P1/5P1P/3Q2K1 w - - 0 20"), None)  # h6: no Qd8 mate
    keys = [s["key"].rsplit(".", 1)[0] for s in advice["comment"]]
    assert keys == ["coach.advice.pos_king_holes"]


def test_bad_bishop():
    # White pawns on the dark squares d4, e5, c3 (blocked), the c1 bishop is dark-squared.
    board = chess.Board("4k3/8/2p1p3/2PpP3/3P4/8/8/2B1K3 w - - 0 30")
    assert any(f.code == "bad_bishop" for f in positional_features(board, chess.WHITE))


def test_move_ideas():
    board = chess.Board("4k3/pp3ppp/8/8/8/8/PP3PPP/R3K3 w - - 0 25")
    assert move_idea(board, chess.Move.from_uci("a1d1")).code == "open_file"
    castle = chess.Board("r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1")
    assert move_idea(castle, chess.Move.from_uci("e1g1")).code == "castle"
    ending = chess.Board("4k3/8/8/8/8/8/4P3/4K3 w - - 0 50")
    assert move_idea(ending, chess.Move.from_uci("e1d2")).code == "king_active"
    assert move_idea(ending, chess.Move.from_uci("e2e4")).code == "passed_push"


def test_quiet_position_gets_a_positional_sentence():
    advice = advice_for_position(chess.Board("4k3/pp3ppp/8/8/8/8/PP3PPP/R3K3 w - - 0 25"), None)
    keys = [s["key"].rsplit(".", 1)[0] for s in advice["comment"]]
    assert keys == ["coach.advice.pos_king_active"]


def hint_key(fen: str, best: str | None) -> str:
    comment = hint_for_position(chess.Board(fen), best, step=1)["comment"]
    assert len(comment) == 1 and not comment[0]["params"]  # level 1 does not name squares and pieces
    return comment[0]["key"].rsplit(".", 1)[0]


def test_first_hint_step_names_the_positional_idea_of_the_best_move():
    castle = "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1"
    assert hint_key(castle, "e1g1") == "coach.hint.pos_castle"
    rook = "4k3/pp3ppp/8/8/8/8/PP3PPP/R3K3 w - - 0 25"
    assert hint_key(rook, "a1d1") == "coach.hint.pos_open_file"
    assert hint_key(rook, "a2a3") == "coach.hint.quiet"  # the best move has no positional idea: a generic hint


def test_first_hint_step_without_engine_uses_the_main_feature():
    assert hint_key("4k3/8/8/8/8/8/4P3/4K3 w - - 0 50", None) == "coach.hint.pos_king_active"
