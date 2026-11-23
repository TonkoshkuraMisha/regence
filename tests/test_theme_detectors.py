"""Theme recognition without a database tag (task 27.8): each rule on a built position, empty answer on an ordinary one."""

import chess

from src.services.theme_detectors import _passed, detect


def test_greek_gift():
    fen = "r1bq1rk1/pppn1ppp/4p3/3pP3/1b1P4/2NB1N2/PPP2PPP/R1BQK2R b KQ - 0 8"
    codes = detect(fen, ["a7a6", "d3h7", "g8h7", "f3g5"], ["kingsideAttack", "sacrifice"])
    assert "greek_gift" in codes and "sacrifice" in codes


def test_lucena_material_and_placement():
    assert "lucena" in detect("1K1k4/1P6/8/8/8/8/r7/2R5 b - - 0 1", ["d8e7", "c1e1"], ["rookEndgame"])


def test_basic_mate():
    assert "basic_mates" in detect("6k1/8/6K1/8/8/8/8/R7 b - - 0 1", ["g8h8", "a1a8"], ["mate", "mateIn1"])


def test_opening_trap():
    fen = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"
    assert "opening_trap" in detect(fen, ["g8f6", "h5f7"], ["opening", "mate", "mateIn1"])


def test_tag_combinations():
    fen = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"
    moves = ["g8f6", "h5f7"]
    assert "combination" in detect(fen, moves, ["fork", "pin"])
    assert "unstoppable_threat" in detect(fen, moves, ["quietMove", "mate"])
    assert "combination" not in detect(fen, moves, ["fork"])


def test_ordinary_position_gets_nothing_and_bad_input_is_safe():
    assert detect("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", ["f1c4", "g8f6"], []) == []
    assert detect("not a fen", ["e2e4"], []) == []
    assert detect("6k1/8/6K1/8/8/8/8/R7 b - - 0 1", ["g8h8", "a1a7"], []) == []  # not a mate - no theme


# --- Additional coverage: each rule on a minimal constructed position ---




def test_passed_pawn_blocked_by_enemy_neighbour():
    board = chess.Board("8/p7/8/1P6/8/8/8/4K2k w - - 0 1")
    assert not _passed(board, chess.B5, chess.WHITE)  # the black pawn on a7 is ahead on the adjacent file
    assert _passed(chess.Board("8/7p/8/1P6/8/8/8/4K2k w - - 0 1"), chess.B5, chess.WHITE)


def test_illegal_or_short_line_is_ignored():
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"
    assert detect(fen, ["g8f6", "a1a8"], ["opening"]) == []  # an illegal solution move
    assert detect(fen, ["g8f6"], ["opening"]) == []  # there is no solution at all


def test_double_bishop_sacrifice():
    fen = "6k1/p5pp/8/4B3/8/3B4/8/4K3 b - - 0 1"
    codes = detect(fen, ["a7a6", "d3h7", "g8h7", "e5g7"], [])
    assert "double_bishop_sacrifice" in codes


def test_perpetual_check_and_stalemate_trick():
    fen = "6k1/p7/8/7Q/8/8/8/K7 b - - 0 1"
    codes = detect(fen, ["a7a6", "h5d5", "g8h8", "d5e5", "h8g8"], ["equality"])
    assert "perpetual_check" in codes and "save_by_perpetual" in codes
    stale = detect("8/5K1k/8/8/8/8/8/6Q1 b - - 0 1", ["h7h8", "g1g6"], [])
    assert "stalemate_trick" in stale and "save_by_stalemate" in stale


def test_pawn_endgame_breakthrough_race_and_opposition():
    breakthrough = "7k/ppp5/8/PPP5/8/8/8/4K3 b - - 0 1"
    codes = detect(breakthrough, ["h8g8", "b5b6", "a7b6", "c5c6", "b7c6", "a5a6", "g8f8", "a6a7", "f8e8", "a7a8q"], [])
    assert "pawn_breakthrough" in codes
    race = detect("8/7p/P7/8/4k3/8/8/4K3 b - - 0 1", ["e4d4", "a6a7", "d4c4", "a7a8q"], [])
    assert "pawn_race" in race
    opposition = detect("8/7p/2k5/8/4K3/8/P7/8 b - - 0 1", ["c6d6", "e4d4"], [])
    assert "opposition" in opposition


def test_rook_endgames_philidor_and_rook_behind_passer():
    philidor = detect("4k3/3r4/4p3/7R/8/8/8/4K3 b - - 0 1", ["d7d6", "h5h8"], ["equality"])
    assert "philidor_position" in philidor
    behind = detect("8/7k/8/P7/8/8/8/1R2K3 b - - 0 1", ["h7h6", "b1a1"], ["rookEndgame"])
    assert "rook_behind_passer" in behind


def test_opening_early_queen_and_development_lag():
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"
    codes = detect(fen, ["d8h4", "f3h4"], ["opening", "crushing"])
    assert "opening_trap" in codes and "early_queen" in codes and "development_lag" in codes


def test_domination_undermining_and_pin_exploit():
    fen = "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    assert "domination" in detect(fen, ["g8f6", "e4d5"], ["trappedPiece", "quietMove"])
    assert "undermining" in detect(fen, ["g8f6", "e4d5"], ["capturingDefender"])
    assert "pin_exploit" in detect("4k3/p7/8/4n3/8/8/8/4R1K1 b - - 0 1", ["a7a6", "e1e5"], ["pin"])


def test_rook_lift():
    codes = detect("4k3/7p/8/8/8/8/8/R3K3 b - - 0 1", ["h7h6", "a1a3", "e8d8", "a3h3"], [])
    assert "rook_lift" in codes


def test_wrong_bishop_seventh_rank_and_isolated_pawn():
    # White: bishop c1 (dark-squared) and pawn a5, the promotion square a8 is light - the "wrong" bishop, Black defends.
    assert "wrong_bishop" in detect("8/8/1K6/P7/8/8/8/2B4k w - - 0 1", ["b6c6", "h1g1"], [])
    codes = detect("4k3/p6p/8/8/3P4/8/8/R3K3 b - - 0 1", ["h7h6", "a1a7"], [])
    assert "seventh_rank" in codes and "isolated_pawn" in codes
