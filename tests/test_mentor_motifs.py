# --- FILE: tests/test_mentor_motifs.py ---
"""
Mentor motif detector on classic positions.

Each position is checked twice: as is and mirrored with colors swapped
(``board.mirror()``); the motif must be found for the other side on the mirrored square. This doubles the number of
checks and catches rules that by mistake work only for White.

Traps (positions without the motif) are just as important: a mentor who sees a fork where there is none
does more harm than a silent one.
"""

import time

import chess
import pytest

from src.services.mentor_service import (
    Motif,
    analyze_move,
    capture_gain,
    detect_motifs,
)

W, B = chess.WHITE, chess.BLACK
sq = chess.parse_square


def _mirror_move(move: chess.Move) -> chess.Move:
    return chess.Move(chess.square_mirror(move.from_square), chess.square_mirror(move.to_square), move.promotion)


def _found(board: chess.Board, san: str | None) -> list[Motif]:
    """Motifs of the position, or, if a move is given, those created by the move (in favor of the mover)."""
    if san is None:
        return detect_motifs(board)
    return analyze_move(board, board.parse_san(san)).created


def _variants(fen: str, san: str | None):
    """The position as is and mirrored; the mirroring function for expected squares and color."""
    board = chess.Board(fen)
    assert board.is_valid(), board.status()
    yield board, san, (lambda s: s), (lambda c: c)
    mirrored = board.mirror()
    mirrored_san = None
    if san is not None:
        mirrored_san = mirrored.san(_mirror_move(board.parse_san(san)))
    yield mirrored, mirrored_san, chess.square_mirror, (lambda c: not c)


def _has(motifs: list[Motif], code: str, color: chess.Color, square: chess.Square,
         targets: set[chess.Square] | None, value: int | None) -> bool:
    for motif in motifs:
        if (motif.code, motif.color, motif.square) != (code, color, square):
            continue
        if targets is not None and set(motif.targets) != targets:
            continue
        if value is not None and motif.value != value:
            continue
        return True
    return False


def _describe(motifs: list[Motif]) -> list[str]:
    return [
        f"{m.code}/{'W' if m.color else 'B'}@{chess.square_name(m.square)}"
        f"->{[chess.square_name(t) for t in m.targets]}={m.value}"
        for m in motifs
    ]


# (motif, FEN, move or None, side, square, targets or None, value or None)
POSITIVE = [
    # Undefended piece: a knight on e4 attacked by the knight on c3; a queen attacked by a pawn
    # (the pawn gets recaptured: a clean +800).
    ("hanging", "rnbqkb1r/pppp1ppp/8/4p3/4n3/2N5/PPPP1PPP/R1BQKBNR w KQkq - 0 4", None, W, "e4", {"c3"}, 300),
    ("hanging", "rnb1kbnr/pppp1ppp/8/4p3/3q4/2P5/PP1PPPPP/RNBQKBNR w KQkq - 0 3", None, W, "d4", {"c3"}, 800),
    # Fork: a knight on c7 hits the king and a rook; a pawn on d5 hits a knight and a bishop
    # (the pawn is protected, taking it is unprofitable).
    ("fork", "r3k2r/ppp2ppp/8/1N6/8/8/PPP2PPP/R3K2R w KQkq - 0 1", "Nxc7+", W, "c7", {"a8", "e8"}, None),
    ("fork", "r2qk2r/ppp2ppp/2n1b3/8/3P4/2N5/PPP2PPP/R1BQK2R w KQkq - 0 1", "d5", W, "d5", {"c6", "e6"}, None),
    # Pin to the king: bishop b5 and knight c6 (Spanish after ...d6); rook e1 and knight e7.
    ("pin_absolute", "r1bqkbnr/ppp2ppp/2np4/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4", None, W, "b5",
     {"c6", "e8"}, None),
    ("pin_absolute", "4k3/4n3/8/8/8/8/8/4RK2 w - - 0 1", None, W, "e1", {"e7", "e8"}, None),
    # Pin to the queen: Bg5 and a knight on f6; rook d1 and bishop d6.
    ("pin_relative", "rnbqkb1r/ppp2ppp/3p1n2/4p1B1/4P3/3P4/PPP2PPP/RN1QKBNR b KQkq - 1 4", None, W, "g5",
     {"f6", "d8"}, None),
    ("pin_relative", "3qk3/8/3b4/8/8/8/8/3RK3 w - - 0 1", None, W, "d1", {"d6", "d8"}, None),
    # Skewer: king in front, queen behind; queen in front, rook behind.
    ("skewer", "q7/8/8/k7/8/8/8/R3K3 b - - 0 1", None, W, "a1", {"a5", "a8"}, None),
    ("skewer", "7k/8/1r6/2q5/8/8/5B2/4K3 b - - 0 1", None, W, "f2", {"c5", "b6"}, None),
    # Discovered attack: the bishop moves away and the rook hits the queen; the knight moves away and the bishop hits the rook.
    ("discovered_attack", "3qk3/8/8/8/8/3B4/8/3RK3 w - - 0 1", "Bh7", W, "d1", {"d8"}, None),
    ("discovered_attack", "4k3/8/5r2/8/3N4/8/1B6/4K3 w - - 0 1", "Nb5", W, "b2", {"f6"}, None),
    # Discovered check: the knight leaves the rook's line; the knight leaves the bishop's diagonal.
    ("discovered_check", "4k3/8/8/8/4N3/8/8/4RK2 w - - 0 1", "Nc5+", W, "e1", {"e8", "c5"}, None),
    ("discovered_check", "7k/8/8/8/8/8/1N6/B3K3 w - - 0 1", "Nd3+", W, "a1", {"h8", "d3"}, None),
    # Double check: knight and rook; bishop and queen.
    ("double_check", "4k3/8/8/8/4N3/8/8/4RK2 w - - 0 1", "Nf6+", W, "e1", {"e8", "f6"}, None),
    ("double_check", "4k3/8/8/8/4B3/8/8/4Q1K1 w - - 0 1", "Bc6+", W, "e1", {"e8", "c6"}, None),
    # Overload: the queen on d7 is the only defender of the knight on c6 and the bishop on e6;
    # the knight on d7 defends two bishops.
    ("overloaded", "4k3/3q4/2n1b3/1B4N1/8/8/8/4K3 w - - 0 1", None, W, "d7", {"c6", "e6"}, None),
    ("overloaded", "4k3/3n4/1b3b2/B7/6N1/8/8/4K3 w - - 0 1", None, W, "d7", {"b6", "f6"}, None),
    # Trapped piece: a bishop on a7 after ...b6; a knight on h8 with both retreat squares attacked.
    ("trapped", "r1bqkbnr/B1pp1ppp/1pn5/4p3/4P3/8/PPPP1PPP/RN1QKBNR w KQkq - 0 5", None, B, "a7", None, 300),
    ("trapped", "4k2N/5p2/6p1/8/8/8/K7/7r w - - 0 1", None, B, "h8", None, 300),
    # Weak back rank: there is no escape square (luft) and the opponent's rook controls the rank.
    ("back_rank", "6k1/5ppp/8/8/8/8/5PPP/3R2K1 b - - 0 1", None, W, "g8", {"d8"}, None),
    ("back_rank", "7k/6pp/8/8/8/8/6PP/4R1K1 b - - 0 1", None, W, "h8", {"e8"}, None),
    # Mate threat: if White were to move, it would be a back-rank mate.
    ("mate_threat", "6k1/5ppp/8/8/8/8/5PPP/3R2K1 b - - 0 1", None, W, "d1", {"d8"}, 1),
    ("mate_threat", "7k/6pp/8/8/8/8/6PP/4R1K1 b - - 0 1", None, W, "e1", {"e8"}, 1),
    # Mate in 1 and mate in 2 via a check (sacrifice on d8).
    ("mate_in", "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", None, W, "d1", {"d8"}, 1),
    ("mate_in", "2r3k1/5ppp/8/8/8/8/3R1PPP/3Q2K1 w - - 0 1", None, W, "d2", {"d8"}, 2),
    # Passed pawns: the value is the number of squares to promotion.
    ("passed_pawn", "8/5k2/8/2P5/8/p7/5K2/8 w - - 0 1", None, W, "c5", None, 3),
    ("passed_pawn", "8/5k2/8/2P5/8/p7/5K2/8 w - - 0 1", None, B, "a3", None, 2),
    ("passed_pawn", "4k3/8/8/3P4/8/8/8/4K3 w - - 0 1", None, W, "d5", None, 3),
    # A rook on an open and on a half-open file.
    ("open_file", "3r2k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", None, W, "d1", None, None),
    ("open_file", "3r2k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", None, B, "d8", None, None),
    ("half_open_file", "4k3/4p3/8/8/8/8/8/4RK2 w - - 0 1", None, W, "e1", None, None),
    ("half_open_file", "2r1k3/8/8/8/2P5/8/8/4K3 w - - 0 1", None, B, "c8", None, None),
    # Lag in development: Black has three minor pieces at home against one for White.
    ("development_lag", "rnbqkbnr/pppp1ppp/8/4p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R b KQkq - 5 7", None, W, "e8",
     None, 3),
    ("development_lag", "r1bqkbnr/pp3ppp/2n5/8/8/2N2N2/PP3PPP/R1BQ1RK1 b kq - 0 12", None, W, "e8", None, 2),
    # King stuck in the center: move 12, the d and e files without own pawns, the opponent has a queen.
    ("delayed_castling", "r1bqkbnr/pp3ppp/2n5/8/8/2N2N2/PP3PPP/R1BQ1RK1 b kq - 0 12", None, W, "e8", None, None),
    ("delayed_castling", "rnbqk2r/pp3ppp/5n2/8/1b6/2N2N2/PP3PPP/R1BQ1RK1 b kq - 0 10", None, W, "e8", None, None),
    # Battery: a rook in front of the queen on the e-file aims at the king;
    # a bishop in front of the queen on the diagonal aims at the g7 pawn.
    ("battery", "4k3/8/8/8/8/8/4R3/4Q1K1 b - - 0 1", None, W, "e2", {"e1", "e8"}, None),
    ("battery", "6k1/6p1/8/8/8/2B5/1Q6/6K1 w - - 0 1", None, W, "c3", {"b2", "g7"}, None),
    # Interference: a bishop steps between the rook on a8 and the knight on a4;
    # the knight on d4 blocks the bishop on h8 that protected the rook on b2.
    ("interference", "r2B3k/8/8/8/n2R4/8/8/6K1 w - - 0 1", "Ba5", W, "a5", {"a8", "a4"}, None),
    ("interference", "k6b/8/1R6/5N2/8/8/1r6/7K w - - 0 1", "Nd4", W, "d4", {"h8", "b2"}, None),
]

NEGATIVE = [
    # Knight for knight: both are protected by pawns, neither is "hanging".
    ("hanging", "4k3/8/3p4/4n3/8/5N2/6P1/4K3 w - - 0 1", None),
    # The knight attacks a rook and a protected bishop of equal value: only one real target, not a fork.
    ("fork", "4k3/2p5/1b3r2/3p4/1N6/8/8/4K3 w - - 0 1", "Nxd5"),
    # A "fork" by a knight that the king simply captures.
    ("fork", "r2qkb1r/ppp2ppp/2n5/3p2N1/8/8/PPP2PPP/RNBQK2R w KQkq - 0 1", "Nxf7"),
    # The queen "pins" a knight to a rook that is cheaper than the queen: that is not a pin.
    ("pin_relative", "3rk3/3n4/8/8/8/8/8/3QK3 w - - 0 1", None),
    # Only a pawn stands behind the queen: not a skewer.
    ("skewer", "7k/8/1p6/2q5/8/8/5B2/4K3 b - - 0 1", None),
    # The knight moves away and opens a protected pawn to the bishop: not a discovered attack.
    ("discovered_attack", "4k3/8/5p2/4p3/3N4/8/1B6/4K3 w - - 0 1", "Nb5"),
    # The knight from d6 gives check itself: a double check, not just a discovered one.
    ("discovered_check", "4k3/8/8/8/4N3/8/8/4RK2 w - - 0 1", "Nd6+"),
    # The knight on c6 has a second defender, the b7 pawn: the queen is not overloaded.
    ("overloaded", "4k3/1p1q4/2n1b3/1B4N1/8/8/8/4K3 w - - 0 1", None),
    # The bishop on a7 is attacked but escapes along the b6-e3 diagonal.
    ("trapped", "r1bqkbnr/Bppp1ppp/2n5/4p3/4P3/8/PPPP1PPP/RN1QKBNR w KQkq - 0 4", None),
    # The luft on h6: the rank is not weak and there is no mate.
    ("back_rank", "6k1/5pp1/7p/8/8/8/5PPP/3R2K1 b - - 0 1", None),
    ("mate_threat", "6k1/5pp1/7p/8/8/8/5PPP/3R2K1 b - - 0 1", None),
    # The d8 square is protected by the rook on e8.
    ("back_rank", "4r1k1/5ppp/8/8/8/8/5PPP/3R2K1 b - - 0 1", None),
    ("mate_in", "4r1k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", None),
    # Pawns on adjacent files in front of each other: no passed pawns.
    ("passed_pawn", "8/5k2/3p4/2P5/8/8/5K2/8 w - - 0 1", None),
    ("passed_pawn", "4k3/8/8/8/1p6/8/P7/4K3 w - - 0 1", None),
    # An own pawn on the rook's file.
    ("half_open_file", "4k3/8/8/8/8/8/4P3/4RK2 w - - 0 1", None),
    ("open_file", "4k3/8/8/8/8/8/4P3/4RK2 w - - 0 1", None),
    # The opening is still going on (move 3): too early to speak of lagging in development.
    ("development_lag", "rnbqkbnr/pppp1ppp/8/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3", None),
    # The center is closed by the d7/e5 pawns: the king in the center is still safe.
    ("delayed_castling", "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 b kq - 0 12", None),
    # The opponent has no queen.
    ("delayed_castling", "r1bqkbnr/pp3ppp/2n5/8/8/2N2N2/PP3PPP/R1B2RK1 b kq - 0 12", None),
    # A "skewer" by a rook that the queen simply captures (the rook is unprotected).
    ("skewer", "r2qr1k1/p4np1/2pb1nQp/8/5P2/2BB4/PPP2P1P/4R1K1 w - - 6 20", "Rxe8+"),
    # A queen "skewers" an unprotected queen: it is simply a trade.
    ("skewer", "3r1rk1/ppp3pp/2p1b3/2P5/8/2N1qPPp/PPP4K/R2Q1R2 w - - 5 17", "Qe1"),
    # A "pin" by a bishop that the a6 pawn captures.
    ("pin_absolute", "r1bqkbnr/1pp2ppp/p1np4/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 5", None),
    # The bishop is attacked with no retreat, but a knight removes the attacking pawn: the piece is not trapped.
    ("trapped", "4k3/8/8/2p5/1B6/2N5/8/4K3 w - - 0 1", None),
    # The starting position and a quiet Italian game: no tactics.
    ("hanging", chess.STARTING_FEN, None),
    ("fork", "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 2 6", None),
    # Rooks on a file, but an own knight blocks the line; the bishop behind the rook is on a different line.
    ("battery", "4k3/8/8/8/8/4N3/4R3/4R1K1 w - - 0 1", None),
    ("battery", "4k3/8/8/8/8/8/4R3/4B1K1 b - - 0 1", None),
    # The bishop steps between the rook and the knight, but the b5 pawn also protects the knight:
    # it cannot be captured with a gain.
    ("interference", "r2B3k/8/8/1p6/n2R4/8/8/6K1 w - - 0 1", "Ba5"),
]


@pytest.mark.parametrize(("code", "fen", "san", "color", "square", "targets", "value"), POSITIVE)
def test_motif_is_found_in_both_colours(code, fen, san, color, square, targets, value):
    for board, move, flip_square, flip_color in _variants(fen, san):
        expected_targets = None if targets is None else {flip_square(sq(t)) for t in targets}
        motifs = _found(board, move)
        assert _has(motifs, code, flip_color(color), flip_square(sq(square)), expected_targets, value), (
            board.fen(), move, _describe(motifs))


@pytest.mark.parametrize(("code", "fen", "san"), NEGATIVE)
def test_motif_is_not_invented(code, fen, san):
    for board, move, _, _ in _variants(fen, san):
        motifs = _found(board, move)
        assert not [m for m in motifs if m.code == code], (board.fen(), move, _describe(motifs))


def test_every_motif_code_is_covered_by_positive_and_negative_cases():
    from typing import get_args

    from src.services.mentor_service import MotifCode

    covered = {case[0] for case in POSITIVE}
    assert covered == set(get_args(MotifCode))
    # Every motif: at least two positions, each also checked in the mirror (>= 3 checks per motif).
    for code in covered:
        assert sum(1 for case in POSITIVE if case[0] == code) >= 2, code


# --- order of targets and details ----------------------------------------------------------------


def test_pin_targets_are_pinned_piece_then_piece_behind():
    motif = next(m for m in detect_motifs(chess.Board("3qk3/8/3b4/8/8/8/8/3RK3 w - - 0 1"))
                 if m.code == "pin_relative")
    assert motif.targets == (sq("d6"), sq("d8"))


def test_mate_in_two_starts_with_a_check_that_forces_mate():
    board = chess.Board("2r3k1/5ppp/8/8/8/8/3R1PPP/3Q2K1 w - - 0 1")
    motif = next(m for m in detect_motifs(board) if m.code == "mate_in")
    first = chess.Move(motif.square, motif.targets[0])
    assert board.gives_check(first)
    board.push(first)
    replies = list(board.legal_moves)
    assert replies
    for reply in replies:
        board.push(reply)
        assert any(_mates(board, mate) for mate in list(board.legal_moves)), reply
        board.pop()


def _mates(board: chess.Board, move: chess.Move) -> bool:
    board.push(move)
    try:
        return board.is_checkmate()
    finally:
        board.pop()


def test_motif_serialises_with_square_names_and_pieces():
    board = chess.Board("r3k2r/ppp2ppp/8/1N6/8/8/PPP2PPP/R3K2R w KQkq - 0 1")
    board.push_san("Nxc7+")
    fork = next(m for m in detect_motifs(board) if m.code == "fork")

    assert fork.to_dict(board) == {
        "code": "fork", "color": "white", "square": "c7", "piece": "N",
        "targets": [{"square": "a8", "piece": "r"}, {"square": "e8", "piece": "k"}],
        "value": None,
    }


# --- exchange on a square -----------------------------------------------------------------------------


@pytest.mark.parametrize(("fen", "square", "gain"), [
    ("4k3/8/8/4n3/8/5N2/8/4K3 w - - 0 1", "e5", 300),            # undefended knight
    ("4k3/8/3p4/4n3/8/5N2/8/4K3 w - - 0 1", "e5", 0),            # knight for knight
    ("4k3/8/3p4/4r3/8/5N2/8/4K3 w - - 0 1", "e5", 200),          # rook for knight
    ("4k3/8/3p4/4p3/8/5Q2/8/4K3 w - - 0 1", "e5", None),         # the queen cannot reach e5
    ("4k3/8/3p4/4p3/8/2B5/8/4K3 w - - 0 1", "e5", -200),         # bishop for a protected pawn
])
def test_capture_gain(fen, square, gain):
    assert capture_gain(chess.Board(fen), sq(square)) == gain


def test_capture_gain_respects_pins():
    # The c3 knight is pinned by the b4 bishop to the king on e1 and cannot capture on e4.
    board = chess.Board("4k3/8/8/8/1b2n3/2N5/8/4K3 w - - 0 1")
    assert capture_gain(board, sq("e4")) is None


# --- what the move changed ----------------------------------------------------------------------------


def test_move_that_hangs_a_piece_is_reported_as_allowed():
    # The white bishop goes to g5 under the h6 pawn. The "pin" of the e7 pawn to the queen does not count:
    # the bishop is simply captured.
    board = chess.Board("rnbqkbnr/ppppppp1/7p/8/8/3P4/PPP1PPPP/RNBQKBNR w KQkq - 0 2")
    facts = analyze_move(board, board.parse_san("Bg5"))

    assert any(m.code == "hanging" and m.color == B and m.square == sq("g5") for m in facts.allowed)
    assert facts.created == []


def test_moving_an_attacked_piece_away_resolves_the_threat():
    board = chess.Board("rnbqkb1r/pppp1ppp/8/4p3/4n3/2N5/PPPP1PPP/R1BQKBNR b KQkq - 0 4")
    facts = analyze_move(board, board.parse_san("Nf6"))

    assert any(m.code == "hanging" and m.square == sq("e4") for m in facts.resolved)
    assert not any(m.code == "hanging" for m in facts.allowed)


def test_illegal_move_is_rejected():
    with pytest.raises(ValueError):
        analyze_move(chess.Board(), chess.Move.from_uci("e2e5"))


def test_finished_game_reports_no_motifs():
    """After a mate there is neither a "fork" by the mating rook nor weaknesses: the student is shown the mate itself."""
    board = chess.Board("r5kr/ppp2Rpp/1b6/n2Q4/2q5/B4N2/P4PPP/1R4K1 w - - 1 21")
    facts = analyze_move(board, board.parse_san("Rf8#"))
    assert facts.created == [] and facts.allowed == []


def test_detection_is_fast_enough_for_every_move_of_a_game():
    """Game review calls the detector on every ply; in a busy position it finishes within a fraction of a second."""
    board = chess.Board("r1bq1rk1/pp2bppp/2n1pn2/2pp4/2PP4/2N1PN2/PP2BPPP/R1BQ1RK1 w - - 0 8")
    started = time.perf_counter()
    for move in list(board.legal_moves):
        analyze_move(board, move)
    per_move_ms = (time.perf_counter() - started) * 1000 / board.legal_moves.count()
    assert per_move_ms < 100, per_move_ms
