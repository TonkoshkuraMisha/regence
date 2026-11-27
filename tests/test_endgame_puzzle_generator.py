# --- FILE: tests/test_endgame_puzzle_generator.py ---
"""
Rules of the own endgame puzzle generator (scripts/dev/build_endgame_puzzles.py) that need no tablebases: the queen-vs-pawn
setup of the stalemate defence (task 27.9), its theme rule and keeping the other themes on a partial rebuild.
"""

import csv
import gzip
import random

import chess

from scripts.dev import build_endgame_puzzles as gen


def test_queen_vs_pawn_setups_are_legal_and_on_stalemate_files():
    rng = random.Random(3)
    boards = [b for b in (gen.gen_q_vs_pawn(rng) for _ in range(300)) if b is not None]
    assert boards
    for board in boards:
        assert board.is_valid() and board.turn == chess.BLACK and not board.is_check()
        (pawn,) = board.pieces(chess.PAWN, chess.BLACK)
        assert chess.square_file(pawn) in gen.STALEMATE_PAWN_FILES and chess.square_rank(pawn) == 1
        assert len(board.pieces(chess.QUEEN, chess.WHITE)) == 1


def test_only_a_king_move_makes_the_stalemate_theme():
    # Black: Kb2, pawn c2; White: Qd2 (watching c1), Kh8. ...Ka1 is the stalemate defence; a promotion is not.
    board = chess.Board("7K/8/8/8/8/8/1kpQ4/8 b - - 0 1")
    assert gen.classify(board, chess.Move.from_uci("b2a1"), "q_vs_pawn") == "save_by_stalemate"
    assert gen.classify(board, chess.Move.from_uci("c2c1q"), "q_vs_pawn") is None


def test_partial_rebuild_keeps_the_other_themes(tmp_path):
    path = tmp_path / "puzzles.csv.gz"
    old = [{**dict.fromkeys(gen.FIELDS, "x"), "Themes": "endgame regence:opposition"},
           {**dict.fromkeys(gen.FIELDS, "y"), "Themes": "endgame regence:save_by_stalemate"}]
    gen.save(path, {}, old)
    kept = gen.kept_rows(path, {"save_by_stalemate"})
    assert [row["Themes"] for row in kept] == ["endgame regence:opposition"]
    new = {**dict.fromkeys(gen.FIELDS, "z"), "Themes": "endgame regence:save_by_stalemate"}
    assert gen.save(path, {"save_by_stalemate": [new]}, kept) == 2
    with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
        assert sorted(row["PuzzleId"] for row in csv.DictReader(source)) == ["x", "z"]
