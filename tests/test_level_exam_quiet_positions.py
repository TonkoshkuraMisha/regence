"""Quiet-position picking of scripts/build_level_exams.py for the strategy branch of the level exams (27.12).

The engine check is not run in CI; the rule that decides which game moves may become a question is pure."""

import random

import chess

from scripts.build_level_exams import QUIET_PLIES, quiet_positions

# Ruy Lopez, Closed: 1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O Be7 6.Re1 b5 7.Bb3 d6 8.c3 O-O 9.h3 Na5 10.Bc2 c5
GAME = [
    "e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6", "e1g1", "f8e7",
    "f1e1", "b7b5", "a4b3", "d7d6", "c2c3", "e8g8", "h2h3", "c6a5", "b3c2", "c7c5",
]


def test_every_pick_is_a_quiet_move_in_the_window() -> None:
    picks = quiet_positions(GAME, random.Random(1), count=99)
    assert picks
    for fen, line in picks:
        previous, answer = line.split()
        board = chess.Board(fen)
        board.push_uci(previous)  # The puzzle format: the opponent's move first, then the answer.
        move = chess.Move.from_uci(answer)
        assert not board.is_check()
        assert not (board.is_capture(move) or board.gives_check(move) or move.promotion)
        played = 2 * (board.fullmove_number - 1) + (board.turn == chess.BLACK) + 1  # Ply of the answer, from 1.
        assert played in QUIET_PLIES


def test_the_count_is_capped_and_the_choice_is_reproducible() -> None:
    assert len(quiet_positions(GAME, random.Random(1), count=2)) == 2
    assert quiet_positions(GAME, random.Random(7)) == quiet_positions(GAME, random.Random(7))


def test_a_short_game_has_no_positions() -> None:
    assert quiet_positions(GAME[:10], random.Random(1)) == []
