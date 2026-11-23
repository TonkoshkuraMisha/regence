"""
Coach (src/services/coach.py): internal rules on synthetic motifs and hint levels.

A motif is assembled by hand (code, side, square, targets), so every branch of the description, arrows and
engine-reply confirmation
is checked without hunting for a suitable position. Hint levels use real positions without an engine.
"""

import chess
import pytest

from src.services import coach
from src.services.mentor_service import Motif

# White: Ra1 Qd1 Nf3 Bc4 Kg1; black: Kg8 Qd8 Rh8 Nf6 - only a set of squares with pieces for captions.
BOARD = chess.Board("3q2kr/8/5n2/8/2B5/5N2/8/R2Q2K1 w - - 0 1")


def _motif(code: str, *squares: int, color: bool = chess.WHITE, value: int | None = None) -> Motif:
    return Motif(code, color, squares[0], tuple(squares[1:]), value)  # type: ignore[arg-type]


def test_sentence_rejects_params_not_declared_in_templates():
    with pytest.raises(KeyError):
        coach._sentence("verdict", "blunder", "seed", wrong=1)


def test_move_from_motif_needs_targets_and_a_legal_move():
    assert coach._move_from_motif(BOARD, _motif("mate_in", chess.D1)) is None  # no targets
    assert coach._move_from_motif(BOARD, _motif("mate_in", chess.D1, chess.D8)) is not None
    assert coach._move_from_motif(BOARD, _motif("mate_in", chess.D1, chess.H8)) is None  # no such move


def test_caused_by_rules():
    move = chess.Move(chess.D1, chess.D4)
    after_queen = chess.Board("3q2kr/8/5n2/8/2BQ4/5N2/8/R5K1 b - - 0 1")
    assert coach._caused_by(_motif("double_check", chess.A1), move, after_queen)  # discovery - always the cause
    # Captured piece: the motif square must be attacked by the piece that moved (queen on d4 attacks f6).
    assert coach._caused_by(_motif("trapped", chess.F6), move, after_queen)
    assert not coach._caused_by(_motif("trapped", chess.H8), move, after_queen)
    assert coach._caused_by(_motif("fork", chess.D4, chess.D8, chess.F6), move, after_queen)  # the piece itself moved
    # The move from d1 opens the line for the a1 rook to target h1: it left the segment between them.
    assert coach._caused_by(_motif("skewer", chess.A1, chess.H1), move, after_queen)
    assert not coach._caused_by(_motif("skewer", chess.A1), move, after_queen)  # no targets - cause not proven
    assert not coach._caused_by(_motif("skewer", chess.A8, chess.H8), move, after_queen)


def test_material_lost_compares_value_with_capture():
    board = chess.Board("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1")
    capture = chess.Move(chess.E4, chess.D5)
    assert coach._material_lost(_motif("hanging", chess.D5, value=100), chess.Move(chess.E1, chess.E2), board)
    assert not coach._material_lost(_motif("hanging", chess.D5, value=100), capture, board)  # exchange
    assert coach._material_lost(_motif("hanging", chess.D5, value=900), capture, board)
    ep = chess.Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2")
    assert coach._material_lost(_motif("hanging", chess.D6, value=900), chess.Move(chess.E5, chess.D6), ep)


@pytest.mark.parametrize("code, squares, expected", [
    ("fork", (chess.F3, chess.D8, chess.H8), {"attacker", "target1", "target2"}),
    ("skewer", (chess.A1, chess.D1, chess.G1), {"attacker", "front", "behind"}),
    ("pin_absolute", (chess.A1, chess.D1, chess.G1), {"attacker", "front", "behind"}),
    ("overloaded", (chess.D8, chess.F6, chess.H8), {"defender", "target1", "target2"}),
    ("discovered_attack", (chess.A1, chess.D8), {"attacker", "target"}),
    ("discovered_check", (chess.A1,), {"attacker"}),
    ("mate_threat", (chess.D1, chess.D8), {"piece", "square"}),
    ("trapped", (chess.F6,), {"piece"}),
    ("back_rank", (chess.G1,), set()),
])
def test_tactic_params_by_code(code, squares, expected):
    assert set(coach._tactic_params(BOARD, _motif(code, *squares))) == expected


@pytest.mark.parametrize("code, squares, arrows, highlights", [
    ("fork", (chess.F3, chess.D8, chess.H8), 2, 2),
    ("discovered_attack", (chess.A1, chess.D8, chess.H8), 2, 2),
    ("skewer", (chess.A1, chess.D1, chess.G1), 1, 2),
    ("pin_relative", (chess.A1, chess.D1, chess.G1), 1, 2),
    ("overloaded", (chess.D8, chess.F6, chess.H8), 0, 3),
    ("mate_threat", (chess.D1, chess.D8), 1, 0),
    ("mate_in", (chess.D1, chess.D8), 1, 0),
    ("discovered_check", (chess.A1, chess.G8), 1, 0),
    ("discovered_check", (chess.A1,), 0, 0),
    ("trapped", (chess.F6,), 0, 1),
    ("back_rank", (chess.G1,), 0, 0),
])
def test_tactic_arrows_by_code(code, squares, arrows, highlights):
    found_arrows, found_highlights = coach._tactic_arrows(_motif(code, *squares), "idea")
    assert (len(found_arrows), len(found_highlights)) == (arrows, highlights)


@pytest.mark.parametrize("motif, reply, expected", [
    (_motif("mate_in", chess.D1, chess.D8), None, True),  # mate needs no confirmation
    (_motif("hanging", chess.F6, chess.D8), None, False),  # no engine reply
    (_motif("hanging", chess.F6, chess.D8), chess.Move(chess.D8, chess.F6), True),
    (_motif("fork", chess.F3, chess.D8, chess.H8), chess.Move(chess.A1, chess.H8), True),
    (_motif("pin_absolute", chess.A1, chess.D1, chess.G1), chess.Move(chess.A1, chess.D1), True),
    (_motif("pin_absolute", chess.A1, chess.D1, chess.G1), chess.Move(chess.A1, chess.A2), False),
    (_motif("trapped", chess.F6), chess.Move(chess.D1, chess.F6), True),
    (_motif("back_rank", chess.G1, chess.G8), chess.Move(chess.A1, chess.G8), True),
    (_motif("discovered_check", chess.A1), chess.Move(chess.A1, chess.A2), False),
])
def test_confirmed_by_reply(motif, reply, expected):
    assert coach._confirmed_by_reply(motif, reply) is expected


def test_threat_sentence_for_each_kind_of_motif():
    mate, arrows, _ = coach._threat_sentence(BOARD, _motif("mate_in", chess.D1, chess.D8, value=2), "s")
    assert mate["key"].startswith("coach.threat.mate_in") and len(arrows) == 1
    # Illegal mate move - the sentence has the destination square instead of a move.
    odd, _, _ = coach._threat_sentence(BOARD, _motif("mate_in", chess.D1, chess.H8), "s")
    assert odd["params"]["move"] == "h8"
    hanging, arrows, marks = coach._threat_sentence(BOARD, _motif("hanging", chess.F6, chess.D8), "s")
    assert hanging["key"].startswith("coach.threat.hanging") and len(arrows) == 1 and len(marks) == 1
    back, arrows, marks = coach._threat_sentence(BOARD, _motif("back_rank", chess.G8, chess.G1), "s")
    assert back["key"].startswith("coach.threat.back_rank") and arrows == [] and len(marks) == 1
    fork, arrows, _ = coach._threat_sentence(BOARD, _motif("fork", chess.F3, chess.D8, chess.H8), "s")
    assert fork["key"].startswith("coach.threat.fork") and len(arrows) == 2


# --- hint levels and advice without an engine ----------------------------------------------------------------

MATE_IN_ONE = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
FORK_SETUP = "r2qk2r/ppp2ppp/2n5/4N3/2B5/8/PPP2PPP/R2QK2R w KQkq - 0 10"
SCHOLARS = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"


def _hint(fen: str, best: str | None, step: int) -> str:
    return coach.hint_for_position(chess.Board(fen), best, step)["comment"][0]["key"].rsplit(".", 1)[0]


def test_hint_steps_with_and_without_best_move():
    assert _hint(MATE_IN_ONE, "h5f7", 1) == "coach.hint.mate"  # the move delivers mate
    assert _hint(FORK_SETUP, "e5f7", 1) == "coach.hint.fork"  # idea of the best move
    assert _hint("4k3/8/8/3n4/8/8/8/3QK3 w - - 0 1", "d1d5", 1) == "coach.hint.capture"
    assert _hint(SCHOLARS, "g7g6", 1) == "coach.hint.defend"  # the opponent threatens mate
    assert _hint(chess.STARTING_FEN, None, 1).startswith("coach.hint.")
    step2 = coach.hint_for_position(chess.Board(FORK_SETUP), "e5f7", 2)
    assert step2["comment"][0]["key"].startswith("coach.hint.piece") and step2["highlights"][0]["square"] == "e5"
    assert coach.hint_for_position(chess.Board(FORK_SETUP), None, 9)["comment"]  # a level above the third is not an error
    assert coach.hint_for_position(chess.Board(FORK_SETUP), "e5f7", 0)["comment"][0]["key"].startswith("coach.hint")


def test_hint_without_best_move_uses_detector_facts():
    assert _hint(MATE_IN_ONE, None, 1) == "coach.hint.mate"
    assert _hint("4k3/8/8/3n4/8/8/8/3QK3 w - - 0 1", None, 1) == "coach.hint.capture"


def test_positional_nudge_without_engine_uses_first_feature(monkeypatch):
    from src.services.positional import Feature

    monkeypatch.setattr(coach, "positional_features", lambda board, color: [
        Feature("pawn_majority", {}, ()), Feature("king_center", {}, ())])
    assert coach._positional_nudge(chess.Board(), None) == "castle"
    monkeypatch.setattr(coach, "positional_features", lambda board, color: [])
    assert coach._positional_nudge(chess.Board(), None) is None
