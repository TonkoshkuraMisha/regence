# --- FILE: tests/test_personality_storage.py ---
"""
Opponent workshop (task 10.2): storing personalities, importing them from the guest localStorage,
a saved personality's move and a game with it in the archive (not in the leaderboard).
"""

import pytest
from sqlalchemy import select

from src.api.bots import CUSTOM_BOT_USERNAME
from src.api.personalities import MAX_PERSONALITIES_PER_USER
from src.models.game import Game
from src.services.bots import base as bots_base

API = "/api/v1/bots/personalities"
FOOLS_MATE = ["f2f3", "e7e5", "g2g4", "d8h4"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def create(client, token, name="Vanguard", **config):
    return client.post(API, headers=auth(token), json={"name": name, "config": config})


@pytest.fixture(autouse=True)
def no_engine(monkeypatch):
    """Personality moves via the static analyser, without Stockfish."""
    monkeypatch.setattr(bots_base, "analyse_with_stockfish", lambda **kwargs: {})


# --- CRUD -----------------------------------------------------------------------------------------

def test_crud_round_trip(client, token_user_1):
    created = create(client, token_user_1, aggression=80, target_elo=1100)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Vanguard"
    assert body["config"]["aggression"] == 80 and body["config"]["center_control"] == 100

    assert [p["name"] for p in client.get(API, headers=auth(token_user_1)).json()] == ["Vanguard"]

    updated = client.put(f"{API}/{body['id']}", headers=auth(token_user_1),
                         json={"name": "Prophylactic", "config": {"aggression": -90}})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Prophylactic"
    assert updated.json()["config"]["aggression"] == -90

    assert client.delete(f"{API}/{body['id']}", headers=auth(token_user_1)).status_code == 204
    assert client.get(API, headers=auth(token_user_1)).json() == []


def test_requires_login(client):
    assert client.get(API).status_code == 401
    assert client.post(API, json={"name": "Guest"}).status_code == 401


def test_other_players_personalities_are_invisible(client, token_user_1, token_user_2):
    pid = create(client, token_user_1).json()["id"]

    assert client.get(API, headers=auth(token_user_2)).json() == []
    assert client.put(f"{API}/{pid}", headers=auth(token_user_2), json={"name": "Stranger"}).status_code == 404
    assert client.delete(f"{API}/{pid}", headers=auth(token_user_2)).status_code == 404
    assert len(client.get(API, headers=auth(token_user_1)).json()) == 1


def test_name_is_unique_per_owner_ignoring_case(client, token_user_1, token_user_2):
    assert create(client, token_user_1, name="Tactician").status_code == 201
    assert create(client, token_user_1, name="tactician").status_code == 409
    # Another player may have an opponent with the same name.
    assert create(client, token_user_2, name="Tactician").status_code == 201

    other = create(client, token_user_1, name="Positional").json()["id"]
    rename = client.put(f"{API}/{other}", headers=auth(token_user_1), json={"name": "TACTICIAN"})
    assert rename.status_code == 409


def test_limit_per_player(client, token_user_1):
    for i in range(MAX_PERSONALITIES_PER_USER):
        assert create(client, token_user_1, name=f"Bot_{i}").status_code == 201
    over = create(client, token_user_1, name="OneTooMany")
    assert over.status_code == 409
    assert over.json()["detail"]["code"] == "personality_limit"
    assert over.json()["detail"]["params"] == {"max": 20}


@pytest.mark.parametrize("name", [
    "Morphy",  # historical bot
    "philidor",  # bot id
    "Kasparov",  # champion
    CUSTOM_BOT_USERNAME,  # the shared bot for workshop games
    "two words",  # a space
    "\u041corphy",  # mixed alphabets (Cyrillic capital Em followed by Latin letters)
    "12345",  # no letters
    "ab",  # shorter than 3
])
def test_name_follows_username_rules_and_reserved_names(client, token_user_1, name):
    assert create(client, token_user_1, name=name).status_code == 422


def test_config_bounds_are_enforced(client, token_user_1):
    assert create(client, token_user_1, aggression=150).status_code == 422
    assert create(client, token_user_1, piece_values={"queen": 20}).status_code == 422


def test_custom_bot_username_cannot_be_registered(client):
    response = client.post("/api/v1/auth/register", json={"username": CUSTOM_BOT_USERNAME, "password": "S3cure-pass!"})
    assert response.status_code == 400


# --- Import from the guest localStorage ------------------------------------------------------------

def test_import_creates_new_and_reports_skipped(client, token_user_1):
    create(client, token_user_1, name="Existing")
    result = client.post(f"{API}/import", headers=auth(token_user_1), json={"items": [
        {"name": "Fresh", "config": {"aggression": 50}},
        {"name": "existing"},  # the player already has it
        {"name": "Fresh"},  # a repeat within the import itself
        {"name": "Another"},
    ]})
    assert result.status_code == 200, result.text
    body = result.json()
    assert [p["name"] for p in body["created"]] == ["Fresh", "Another"]
    assert [s["name"] for s in body["skipped"]] == ["existing", "Fresh"]
    assert len(client.get(API, headers=auth(token_user_1)).json()) == 3


def test_import_respects_the_limit(client, token_user_1):
    for i in range(MAX_PERSONALITIES_PER_USER - 1):
        create(client, token_user_1, name=f"Bot_{i}")
    body = client.post(f"{API}/import", headers=auth(token_user_1), json={"items": [
        {"name": "Last"}, {"name": "Overflow"},
    ]}).json()
    assert [p["name"] for p in body["created"]] == ["Last"]
    assert body["skipped"][0] == {"name": "Overflow", "reason": "personality_limit", "params": {"max": 20}}


def test_import_rejects_invalid_items_entirely(client, token_user_1):
    response = client.post(f"{API}/import", headers=auth(token_user_1), json={"items": [{"name": "Morphy"}]})
    assert response.status_code == 422
    assert client.get(API, headers=auth(token_user_1)).json() == []


# --- Move of a saved personality --------------------------------------------------------------------

def test_custom_move_by_saved_personality(client, token_user_1, token_user_2):
    pid = create(client, token_user_1, aggression=100).json()["id"]
    fen = "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1"
    url = "/api/v1/bots/custom-move"

    own = client.post(url, headers=auth(token_user_1), json={"fen": fen, "personality_id": pid})
    assert own.status_code == 200 and own.json()["san"] == "Ra8#"

    assert client.post(url, json={"fen": fen, "personality_id": pid}).status_code == 401
    assert client.post(url, headers=auth(token_user_2), json={"fen": fen, "personality_id": pid}).status_code == 404
    both = client.post(url, headers=auth(token_user_1), json={"fen": fen, "personality_id": pid, "config": {}})
    assert both.status_code == 422


# --- Game in the archive -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_game_with_saved_personality_goes_to_archive_under_its_name(
        client, db_session, token_user_1, test_user_1,
):
    pid = create(client, token_user_1, name="Vanguard", target_elo=1100).json()["id"]
    saved = client.post("/api/v1/bots/save-game", headers=auth(token_user_1), json={
        "bot_id": "custom", "personality_id": pid, "player_color": "white", "result": "0-1", "moves_uci": FOOLS_MATE,
    })
    assert saved.status_code == 200, saved.text

    game = (await db_session.execute(select(Game).where(Game.id == saved.json()["game_id"]))).scalar_one()
    assert game.personality_name == "Vanguard"
    assert game.is_rated is False
    assert '[Black "Vanguard"]' in game.pgn and '[BlackElo "1100"]' in game.pgn

    archive = client.get(f"/api/v1/profile/{test_user_1.username}/games").json()["items"]
    assert archive[0]["black_username"] == "Vanguard"
    assert archive[0]["white_username"] == test_user_1.username

    names = {row["username"] for row in client.get("/api/v1/profile/leaderboard").json()}
    assert CUSTOM_BOT_USERNAME not in names and "Vanguard" not in names


def test_unsaved_personality_game_uses_given_name(client, token_user_1):
    saved = client.post("/api/v1/bots/save-game", headers=auth(token_user_1), json={
        "bot_id": "custom", "personality_name": "Draft", "player_color": "black", "result": "0-1",
        "moves_uci": FOOLS_MATE,
    })
    assert saved.status_code == 200, saved.text
    pgn = client.get(f"/api/v1/profile/games/{saved.json()['game_id']}/pgn").text
    assert '[White "Draft"]' in pgn


@pytest.mark.parametrize("extra, code", [
    ({}, 400),  # neither id nor name
    ({"personality_name": "Morphy"}, 400),  # a reserved name
    ({"personality_id": 999999}, 404),  # no such personality
])
def test_custom_game_save_validation(client, token_user_1, extra, code):
    response = client.post("/api/v1/bots/save-game", headers=auth(token_user_1), json={
        "bot_id": "custom", "player_color": "white", "result": "0-1", "moves_uci": FOOLS_MATE, **extra,
    })
    assert response.status_code == code, response.text
