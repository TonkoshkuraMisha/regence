"""
"Plan in this position" (task 27.9): the pure plan rules of scripts/dev/build_position_plans.py and the invariants of the
prepared set frontend/src/content/positionPlans.json. The engine is not needed: its evaluations are stored in the set, and
here only their margins are checked.
"""

import json
from pathlib import Path

import chess
import pytest

from scripts.dev.build_position_plans import (
    BEST_TOLERANCE,
    PLANS,
    WRONG_OPTIONS,
    categorise,
    is_quiet,
    master_plan,
)

SET = Path(__file__).resolve().parents[1] / "frontend" / "src" / "content" / "positionPlans.json"
MIN_MARGIN = 100  # the generator's --margin used for the stored set
MIN_QUESTIONS = 40  # enough for several attempts of ten without repeats


def moves(*uci: str) -> list[chess.Move]:
    return [chess.Move.from_uci(u) for u in uci]


@pytest.mark.parametrize(("fen", "uci", "plan"), [
    # The d-pawn has no opponent pawn in front: a passed pawn, whatever the file.
    ("4k3/8/8/3P4/8/8/8/4K3 w - - 0 1", "d5d6", "passed_pawn"),
    # e4-e5 attacks the pawn f6: a break, not a passed pawn (f6 stands in front on the next file).
    ("4k3/8/5p2/8/4P3/8/8/4K3 w - - 0 1", "e4e5", "central_break"),
    # g2-g4 against a king on g8, queens on the board: a storm; g2-g3 attacks nothing.
    ("q5k1/5ppp/8/8/8/8/6P1/Q5K1 w - - 0 1", "g2g4", "pawn_storm"),
    ("q5k1/5ppp/8/8/8/8/6P1/Q5K1 w - - 0 1", "g2g3", None),
    # b2-b4 against a pawn on b7: the queenside pawns.
    ("4k3/1p6/8/8/8/8/1P6/4K3 w - - 0 1", "b2b4", "queenside_pawns"),
    # A rook to a file without own pawns, not to a file with one.
    ("4k3/8/8/8/8/8/4P3/R3K3 w - - 0 1", "a1d1", "rook_file"),
    ("4k3/8/8/8/8/8/3P4/R3K3 w - - 0 1", "a1d1", None),
    # The king marches only without queens.
    ("4k3/8/8/8/8/8/8/4K3 w - - 0 1", "e1d2", "king_march"),
    ("q3k3/8/8/8/8/8/8/Q3K3 w - - 0 1", "e1d2", None),
    # A capture is no plan's first move.
    ("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1", "e4d5", None),
])
def test_categorise(fen, uci, plan):
    assert categorise(chess.Board(fen), chess.Move.from_uci(uci)) == plan


def test_queenside_plan_needs_two_pushes():
    board = chess.Board("4k3/1pp5/8/8/8/8/1P6/4K3 w - - 0 1")
    assert master_plan(board, moves("b2b4", "e8d8", "b4b5", "d8e8")) == "queenside_pawns"
    assert master_plan(board, moves("b2b4", "e8d8", "e1d2", "d8e8")) is None


def test_rook_file_needs_a_follow_up_on_the_same_file():
    board = chess.Board("4k3/8/8/8/8/8/6PP/R4RK1 w - - 0 1")
    # The second rook goes to the e-file, not to d: two files, no plan.
    assert master_plan(board, moves("a1d1", "e8e7", "f1e1", "e7e8")) is None
    assert master_plan(board, moves("a1d1", "e8e7", "d1d5", "e7e8")) == "rook_file"


def test_king_march_must_go_forward_without_shuffling():
    board = chess.Board("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
    forward = moves("e1d2", "e8e7", "d2d3", "e7e6", "d3d4", "e6e7")
    shuffle = moves("e1d2", "e8e7", "d2e1", "e7e8", "e1d2", "e8e7")
    assert master_plan(board, forward) == "king_march"
    assert master_plan(board, shuffle) is None


@pytest.fixture(scope="module")
def questions() -> list[dict]:
    return json.loads(SET.read_text(encoding="utf-8"))


def test_set_is_large_and_covers_every_plan(questions):
    assert len(questions) >= MIN_QUESTIONS
    assert len({q["id"] for q in questions}) == len(questions)
    assert {q["options"][0]["plan"] for q in questions} == set(PLANS)


def test_every_question_is_sound(questions):
    for q in questions:
        board = chess.Board(q["fen"])
        assert board.is_valid() and not board.is_check(), q["id"]
        options = q["options"]
        assert len(options) == WRONG_OPTIONS + 1, q["id"]
        assert len({o["plan"] for o in options}) == len(options), q["id"]
        for option in options:
            move = chess.Move.from_uci(option["move"])
            assert move in board.legal_moves and is_quiet(board, move), q["id"]
            assert categorise(board, move) == option["plan"], q["id"]
        master, *wrong = options
        assert all(master["score"] - o["score"] >= MIN_MARGIN for o in wrong), q["id"]
        game = moves(*q["continuation"])
        assert game[0].uci() == master["move"], q["id"]
        # The rules see the master's plan in the stored game moves (and every stored move is legal).
        assert master_plan(board, game) == master["plan"], q["id"]
        replay = board.copy()
        for move in game:
            assert move in replay.legal_moves, q["id"]
            replay.push(move)


def test_tolerance_is_tighter_than_the_margin():
    """The master's move is "the" plan only if its slack to the best move is well below the gap to the wrong plans."""
    assert BEST_TOLERANCE < MIN_MARGIN
