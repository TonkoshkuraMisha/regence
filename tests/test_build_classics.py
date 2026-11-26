"""
Chosen master games with stops (task 27.6, scripts/build_classics.py --library / --pgn): which "Guess the move"
positions become stops, a game with too few of them is skipped, the source of the game is kept, and the files of a PGN
are read as the library import reads them. The engine is not used: the selection is substituted.
"""

from pathlib import Path

import pytest

import scripts.build_classics as build
import scripts.build_guess_positions as guess

PGN = """[Event "Test"]
[White "White, A"]
[Black "Black, B"]
[Date "1950.01.01"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1-0
"""


def _position(ply: int, move: str = "e2e4") -> dict:
    """A "Guess the move" position as analyse_game returns it, with fields the stops do not keep."""
    return {"ply": ply, "fen": "?", "move": move, "best_cp": 50, "gap_cp": 200, "lines": [[move, 50]],
            "difficulty": 1200, "themes": []}


def test_winner_stops_only_sorted_and_trimmed():
    stops = build.chosen_stops([_position(5), _position(2), _position(3), _position(0)], "1-0")
    assert [s["ply"] for s in stops] == [0, 2]
    assert set(stops[0]) == {"ply", "move", "best_cp", "gap_cp", "lines"}
    assert [s["ply"] for s in build.chosen_stops([_position(2), _position(3)], "0-1")] == [3]


def test_draw_keeps_both_sides():
    assert [s["ply"] for s in build.chosen_stops([_position(3), _position(2)], "1/2-1/2")] == [2, 3]


def test_a_game_with_too_few_stops_is_skipped(monkeypatch):
    monkeypatch.setattr(guess, "analyse_game", lambda *_: (0, [_position(0)]))
    monkeypatch.setattr(build, "analyse", lambda *_: pytest.fail("a skipped game is not marked up"))
    assert build.analyse_chosen({"pgn": PGN, "source": {"pgn": "x.pgn"}}, 10, 8, 0.1) is None


def test_a_chosen_game_keeps_its_stops_and_source(monkeypatch):
    monkeypatch.setattr(guess, "analyse_game", lambda *_: (0, [_position(4, "f1b5"), _position(1), _position(0)]))
    seen = {}

    def fake_analyse(item, depth):
        seen.update(item)
        return {"id": "white-black-1950", "stops": item["stops"]}

    monkeypatch.setattr(build, "analyse", fake_analyse)
    data = build.analyse_chosen({"pgn": PGN, "source": {"library": "ab" * 32}}, 10, 8, 0.1)
    assert data is not None
    assert [s["ply"] for s in data["stops"]] == [0, 4]
    assert data["source"] == {"library": "ab" * 32}
    assert seen["pgn"] == PGN


def test_every_game_of_a_pgn_file(tmp_path: Path):
    path = tmp_path / "games.pgn"
    path.write_text(PGN + "\n" + PGN.replace("White, A", "Other, C"), encoding="utf-8")
    items = build._pgn_items(path)
    assert len(items) == 2
    assert all(item["source"] == {"pgn": "games.pgn"} for item in items)
    assert "Other, C" in items[1]["pgn"]


def test_short_library_prefix_is_refused():
    import asyncio

    with pytest.raises(SystemExit, match="shorter than"):
        asyncio.run(build._library_items(["abc"]))
