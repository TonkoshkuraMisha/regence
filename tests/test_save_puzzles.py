"""The pure "save the game" rule of scripts/dev/build_save_puzzles.py (the engine check is not run in CI)."""

from scripts.dev.build_save_puzzles import is_save

# Spassky - Janosevic 1964: Black's bishop came to d1, White (a rook down) saves with Qg6+ / Qh6+.
BEFORE = "5rk1/2p1qp2/7Q/1p2p1p1/8/1B4P1/PP2bPP1/6K1 b - - 0 23"
PERPETUAL = "e2d1 h6g6 g8h8 g6h6"


def _row(moves: str, themes: str, fen: str = BEFORE) -> dict:
    return {"FEN": fen, "Moves": moves, "Themes": themes}


def test_checks_by_the_side_that_is_down_are_a_save() -> None:
    assert is_save(_row(PERPETUAL, "equality middlegame long"))


def test_without_the_equality_tag_it_is_not_a_save() -> None:
    assert not is_save(_row(PERPETUAL, "crushing middlegame"))


def test_a_quiet_solver_move_is_not_a_perpetual() -> None:
    assert not is_save(_row("e2d1 h6g6 g8h8 g1h2", "equality middlegame"))


def test_material_balance_means_no_save() -> None:
    # The same line, but Black has no extra rook: a draw is then not a save.
    level = "6k1/2p1qp2/7Q/1p2p1p1/8/1B4P1/PP2bPP1/6K1 b - - 0 23"
    assert not is_save(_row(PERPETUAL, "equality middlegame", fen=level))
