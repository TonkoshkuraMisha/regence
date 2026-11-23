"""The "beautiful game" label (task 27.5): a material sacrifice and the winner's mate; `beautiful` library search."""

import pytest

from src.services import library
from src.services.beauty import is_beautiful

API = "/api/v1/library"
# Legal's mate: the queen is given up for the mate.
LEGAL = ["e2e4", "e7e5", "g1f3", "d7d6", "f1c4", "c8g4", "b1c3", "g7g6", "f3e5", "g4d1", "c4f7", "e8e7", "c3d5"]  # Legal
SCHOLAR = ["e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6", "h5f7"]  # mate without a sacrifice
FOOL = ["f2f3", "e7e5", "g2g4", "d8h4"]  # mate, material unchanged


def test_queen_sacrifice_before_mate_is_beautiful():
    assert is_beautiful(None, LEGAL)


def test_mate_without_sacrifice_is_not_beautiful():
    assert not is_beautiful(None, SCHOLAR)
    assert not is_beautiful(None, FOOL)


def test_no_mate_and_broken_moves_are_not_beautiful():
    assert not is_beautiful(None, LEGAL[:-1])  # no mate on the board
    assert not is_beautiful(None, ["e2e5"])  # illegal move
    assert not is_beautiful(None, [])


def test_sacrifice_outside_window_is_ignored():
    """A sacrifice made long before the mate is no longer a combination: the window cuts it off."""
    filler = ["g1f3", "g8f6", "f3g1", "f6g8"] * 5
    # The queen is given up on the first move (Qxd8 Kxd8), then 20 plies of shuffling; the rook mate never arrives, so no mate.
    assert not is_beautiful("3k4/8/8/8/8/8/8/3QK3 w - - 0 1", ["d1d8", "e8d8"] + filler)


@pytest.mark.asyncio
async def test_beautiful_tag_is_stored_and_searchable(client, db_session):
    pgn = ('[White "Legal"]\n[Black "Saint-Brie"]\n[Result "1-0"]\n\n'
           '1. e4 e5 2. Nf3 d6 3. Bc4 Bg4 4. Nc3 g6 5. Nxe5 Bxd1 6. Bxf7+ Ke7 7. Nd5# 1-0\n\n'
           '[White "Anon"]\n[Black "Anon2"]\n[Result "1-0"]\n\n1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0\n')
    collection = await library.ensure_collection(db_session, "Games/Beautiful")
    await library.import_games(db_session, collection, library.read_text(pgn))
    await db_session.commit()
    found = client.get(f"{API}/games", params={"beautiful": "true"}).json()
    assert found["total"] == 1 and found["games"][0]["white"] == "Legal"
    assert client.get(f"{API}/games").json()["total"] == 2
