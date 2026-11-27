"""Theme marks of library games (task 27.5): tactics that paid off, storage form and the `theme` library search."""

import pytest

from src.services import library
from src.services.game_themes import GAME_THEMES, MOTIF_THEME, decode, encode, game_themes

API = "/api/v1/library"
FURMAN_SIMAGIN = [
    "d2d4", "c7c5", "d4d5", "e7e5", "e2e4", "d7d6", "b1c3", "f8e7", "f1b5",
    "b8d7", "f2f4", "e7h4", "g2g3", "h4f6", "g1f3", "g8e7", "f4e5", "f6e5",
    "f3e5", "d6e5", "c1e3", "b7b6", "d5d6", "e7g6", "h2h4", "e8g8", "e3g5",
    "d8e8", "h4h5", "f7f6", "d1d5", "g8h8", "d5a8",
]
QUIET_GAME = ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6"]


def test_every_game_theme_has_a_detector_motif():
    assert set(MOTIF_THEME.values()) == set(GAME_THEMES)


def test_a_quiet_game_has_no_themes():
    assert game_themes(None, QUIET_GAME) == []


def test_broken_moves_give_no_themes():
    assert game_themes(None, ["e2e5"]) == []


def test_a_fork_that_wins_material_is_a_theme():
    # Furman - Simagin (library game 19): the detector finds a fork and White's material gain follows within three plies.
    assert "fork" in game_themes(None, FURMAN_SIMAGIN)


def test_material_must_follow_the_motif():
    # The same fork where Black simply captures the knight back at once: nothing is won, so no mark.
    fen = "8/4k3/8/8/8/2n5/1N6/4K3 w - - 0 1"
    assert game_themes(fen, ["b2d3", "e7d6"]) == []


def test_storage_form_round_trips():
    assert encode([]) == "" and decode("") == []
    assert encode(["fork", "pin"]) == ",fork,pin," and decode(",fork,pin,") == ["fork", "pin"]


@pytest.mark.asyncio
async def test_theme_is_stored_and_searchable(client, db_session):
    pgn = ('[White "Legal"]\n[Black "Saint-Brie"]\n[Result "1-0"]\n\n'
           '1. e4 e5 2. Nf3 d6 3. Bc4 Bg4 4. Nc3 g6 5. Nxe5 Bxd1 6. Bxf7+ Ke7 7. Nd5# 1-0\n\n'
           '[White "Quiet"]\n[Black "Quiet2"]\n[Result "1/2-1/2"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 1/2-1/2\n')
    collection = await library.ensure_collection(db_session, "Games/Themes")
    await library.import_games(db_session, collection, library.read_text(pgn))
    await db_session.commit()
    everything = client.get(f"{API}/games").json()
    assert everything["total"] == 2
    quiet = next(g for g in everything["games"] if g["white"] == "Quiet")
    assert quiet["themes"] == []
    listed = {code for g in everything["games"] for code in g["themes"]}
    for code in listed:
        found = client.get(f"{API}/games", params={"theme": code}).json()
        assert found["total"] >= 1 and all(code in g["themes"] for g in found["games"])
    # An unknown theme is ignored, as an unknown structure is.
    assert client.get(f"{API}/games", params={"theme": "nonsense"}).json()["total"] == 2
