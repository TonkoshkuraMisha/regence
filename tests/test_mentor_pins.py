import chess

from src.services.mentor_service import _is_defended, _overloaded


def test_pinned_defender_does_not_defend():
    # The d5 bishop is "protected" by the e3 knight, but the knight is pinned by the e8 rook to the king on e1.
    board = chess.Board("4r2k/8/1n6/3B4/8/4N3/8/4K3 w - - 0 1")
    assert not _is_defended(board, chess.D5)


def test_pinned_piece_defends_along_the_pin_line():
    # The e3 rook is pinned by the e8 rook but protects the e5 knight on the same file.
    board = chess.Board("4r2k/8/3n4/4N3/8/4R3/8/4K3 w - - 0 1")
    assert _is_defended(board, chess.E5)


def test_free_defender_defends():
    board = chess.Board("4k3/8/1n6/3B4/4P3/8/8/4K3 w - - 0 1")
    assert _is_defended(board, chess.D5)


def test_pinned_second_defender_does_not_hide_an_overload():
    # The d4 knight is the only real defender of the b3 rook (attacked by the b8 rook) and of the f5 bishop
    # (attacked by the f8 rook). The e4 bishop also
    # looks at f5, but is pinned by the e8 rook to the king on e1 and cannot defend: the d4 knight is overloaded.
    board = chess.Board("1r2rr1k/8/8/5B2/3NB3/1R6/8/4K3 b - - 0 1")
    assert any(m.square == chess.D4 for m in _overloaded(board))
