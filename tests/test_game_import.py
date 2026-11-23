# --- FILE: tests/test_game_import.py ---
"""
Importing games from lichess, chess.com and PGN (task 24.1). Third-party sites are replaced by httpx.MockTransport; the
tests never touch the network; the engine is not called (the analysis is a ready-made JSON).
"""

import datetime as dt
import json

import chess.pgn
import httpx
import pytest
from sqlalchemy import func, select

from src.api import fair_play
from src.core.config import settings
from src.core.errors import DomainValueError
from src.db import redis as redis_module
from src.models.imported_game import ImportedGame
from src.models.puzzle import PersonalPuzzle
from src.services import analysis_service as analysis_module
from src.services import game_import
from src.services import personal_puzzles as puzzles_service
from src.services.engine_pool import EngineBusyError

API = "/api/v1/imports"
# 1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6?? 4. Qxf7# - Black blunders into mate on ply 6.
UCI = ["e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"]


def _pgn(white: str, black: str, site: str = "https://lichess.org/abcd1234", event: str = "Rated Blitz game",
         variant: str = "Standard") -> str:
    return (f'[Event "{event}"]\n[Site "{site}"]\n[White "{white}"]\n[Black "{black}"]\n[Result "1-0"]\n'
            f'[UTCDate "2026.11.01"]\n[UTCTime "10:00:00"]\n[WhiteElo "1500"]\n[BlackElo "1480"]\n'
            f'[TimeControl "180+0"]\n[Variant "{variant}"]\n\n'
            '1. e4 { [%clk 0:03:00] } e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0\n\n')


def _analysis() -> str:
    moves = []
    for ply, uci in enumerate(UCI, start=1):
        bad = ply == 6
        moves.append({"ply": ply, "move_number": (ply + 1) // 2, "color": "white" if ply % 2 else "black",
                      "san": "", "uci": uci, "eval_cp": 0, "eval_display": "0", "best_move_uci": "g7g6" if bad else uci,
                      "cp_loss": 950 if bad else 0, "classification": "Blunder" if bad else "Best", "symbol": ""})
    return json.dumps({"format_version": 2, "engine": "t", "moves": moves})


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sites(monkeypatch):
    """Stubbed lichess and chess.com: responses by request path; requests records what was requested."""
    state: dict = {"requests": [], "lichess": "", "status": 200, "archives": {}}

    def handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        if state["status"] != 200:
            return httpx.Response(state["status"])
        url = str(request.url)
        if url.startswith(settings.GAME_IMPORT_LICHESS_URL):
            return httpx.Response(200, text=state["lichess"])
        if url.endswith("/games/archives"):
            return httpx.Response(200, json={"archives": list(state["archives"])})
        if url in state["archives"]:
            return httpx.Response(200, json={"games": state["archives"][url]})
        return httpx.Response(404)

    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(game_import.httpx, "AsyncClient", client_factory)
    return state


async def test_lichess_games_are_imported_once(client, sites, token_user_1, db_session):
    sites["lichess"] = _pgn("Player1", "rival") + _pgn("rival", "player1", site="https://lichess.org/zzzz9999")
    response = client.post(f"{API}/fetch", json={"source": "lichess", "username": "player1", "max": 5},
                           headers=_auth(token_user_1))
    assert response.status_code == 200, response.text
    body = response.json()
    assert [game["color"] for game in body["added"]] == ["white", "black"]
    assert body["added"][0]["speed"] == "blitz" and body["added"][0]["white_rating"] == 1500
    request = sites["requests"][0]
    assert request.url.path == "/api/games/user/player1"
    assert request.headers["user-agent"] == game_import.USER_AGENT and "authorization" not in request.headers
    # PGN is stored without clocks and comments.
    stored = await db_session.scalar(select(ImportedGame).where(ImportedGame.external_id == "abcd1234"))
    assert "%clk" not in stored.pgn and "Qxf7#" in stored.pgn

    again = client.post(f"{API}/fetch", json={"source": "lichess", "username": "player1"}, headers=_auth(token_user_1))
    assert again.json()["added"] == [] and again.json()["duplicates"] == 2


async def test_variants_and_foreign_games_are_skipped(client, sites, token_user_1):
    sites["lichess"] = _pgn("player1", "rival", variant="Crazyhouse") + _pgn("a", "b", site="https://lichess.org/x2")
    response = client.post(f"{API}/fetch", json={"source": "lichess", "username": "player1"}, headers=_auth(token_user_1))
    assert response.json() == {"added": [], "duplicates": 0, "skipped": 1}


async def test_chesscom_reads_latest_archive_and_only_standard_chess(client, sites, token_user_1):
    base = settings.GAME_IMPORT_CHESSCOM_URL
    old, new = f"{base}/pub/player/player1/games/2026/10", f"{base}/pub/player/player1/games/2026/11"
    sites["archives"] = {
        old: [{"rules": "chess", "uuid": "u-old", "time_class": "rapid", "pgn": _pgn("player1", "x", site="cc")}],
        new: [
            {"rules": "chess960", "uuid": "u960", "pgn": _pgn("player1", "y", site="cc")},
            {"rules": "chess", "uuid": "u-new", "time_class": "bullet", "pgn": _pgn("z", "Player1", site="cc")},
        ],
    }
    response = client.post(f"{API}/fetch", json={"source": "chesscom", "username": "Player1", "max": 2},
                           headers=_auth(token_user_1))
    added = response.json()["added"]
    assert [(game["color"], game["speed"]) for game in added] == [("black", "bullet"), ("white", "rapid")]


async def test_chesscom_does_not_follow_foreign_archive_links(client, sites, token_user_1):
    sites["archives"] = {"https://evil.example/pub/player/player1/games/2026/11": []}
    response = client.post(f"{API}/fetch", json={"source": "chesscom", "username": "player1"}, headers=_auth(token_user_1))
    assert response.status_code == 200
    assert all("evil.example" not in str(request.url) for request in sites["requests"])


@pytest.mark.parametrize(("status", "code", "http"), [
    (404, "import_player_not_found", 404), (429, "import_source_busy", 503), (500, "import_source_unavailable", 502),
])
async def test_site_errors_have_codes(client, sites, token_user_1, status, code, http):
    sites["status"] = status
    response = client.post(f"{API}/fetch", json={"source": "lichess", "username": "player1"}, headers=_auth(token_user_1))
    assert response.status_code == http and response.json()["detail"]["code"] == code


async def test_rate_limited_site_pauses_requests(client, sites, token_user_1):
    sites["status"] = 429
    client.post(f"{API}/fetch", json={"source": "lichess", "username": "player1"}, headers=_auth(token_user_1))
    sites["status"] = 200
    response = client.post(f"{API}/fetch", json={"source": "lichess", "username": "player1"}, headers=_auth(token_user_1))
    assert response.status_code == 503 and response.headers["Retry-After"]
    assert len(sites["requests"]) == 1


async def test_pgn_import_matches_player_by_name(client, token_user_1):
    pgn = _pgn("Misha", "rival") + _pgn("other", "someone")
    response = client.post(f"{API}/pgn", json={"pgn": pgn, "player": "misha"}, headers=_auth(token_user_1))
    assert response.status_code == 200
    assert len(response.json()["added"]) == 1 and response.json()["skipped"] == 1
    assert client.post(f"{API}/pgn", json={"pgn": pgn, "player": "misha"},
                       headers=_auth(token_user_1)).json()["duplicates"] == 1
    missing = client.post(f"{API}/pgn", json={"pgn": pgn, "player": "nobody"}, headers=_auth(token_user_1))
    assert missing.json()["detail"]["code"] == "import_player_not_in_pgn"
    empty = client.post(f"{API}/pgn", json={"pgn": "not a game"}, headers=_auth(token_user_1))
    assert empty.json()["detail"]["code"] == "import_pgn_empty"


async def test_stored_games_are_capped(client, token_user_1, monkeypatch):
    monkeypatch.setattr(settings, "GAME_IMPORT_MAX_STORED", 1)
    client.post(f"{API}/pgn", json={"pgn": _pgn("player1", "a")}, headers=_auth(token_user_1))
    response = client.post(f"{API}/pgn", json={"pgn": _pgn("player1", "b")}, headers=_auth(token_user_1))
    assert response.status_code == 409 and response.json()["detail"]["code"] == "import_limit_reached"


async def test_import_is_rate_limited_per_player(client, token_user_1, monkeypatch, freeze_rate_limit_window):
    monkeypatch.setattr(settings, "RATE_LIMIT_GAME_IMPORT", 1)
    client.post(f"{API}/pgn", json={"pgn": _pgn("player1", "a")}, headers=_auth(token_user_1))
    response = client.post(f"{API}/pgn", json={"pgn": _pgn("player1", "b")}, headers=_auth(token_user_1))
    assert response.status_code == 429 and response.json()["detail"]["code"] == "import_rate_limited"


async def test_import_and_analysis_are_closed_during_a_game(client, token_user_1, monkeypatch):
    async def in_game(user_id: int) -> int:
        return 77

    monkeypatch.setattr(fair_play, "active_rated_game_id", in_game)
    response = client.post(f"{API}/pgn", json={"pgn": _pgn("player1", "a")}, headers=_auth(token_user_1))
    assert response.status_code == 409 and response.json()["detail"]["code"] == "engine_locked_in_game"


async def test_imported_games_belong_to_their_owner(client, token_user_1, token_user_2):
    added = client.post(f"{API}/pgn", json={"pgn": _pgn("player1", "a")}, headers=_auth(token_user_1)).json()["added"]
    game_id = added[0]["id"]
    assert client.get(f"{API}/games/{game_id}/pgn", headers=_auth(token_user_1)).status_code == 200
    assert client.get(f"{API}/games/{game_id}/pgn", headers=_auth(token_user_2)).status_code == 404
    assert client.delete(f"{API}/games/{game_id}", headers=_auth(token_user_2)).status_code == 404
    listing = client.get(f"{API}/games", headers=_auth(token_user_1)).json()
    assert listing["total"] == 1 and listing["games"][0]["analyzed"] is False
    assert client.get(f"{API}/games", headers=_auth(token_user_2)).json()["total"] == 0


async def test_blunder_in_imported_game_becomes_a_personal_puzzle(client, db_session, token_user_1, test_user_1,
                                                                  monkeypatch):
    monkeypatch.setattr(puzzles_service, "top_two", lambda board: [("g7g6", 0), ("d8e7", -350)])
    added = client.post(f"{API}/pgn", json={"pgn": _pgn("rival", "player1")}, headers=_auth(token_user_1)).json()["added"]
    imported = await db_session.get(ImportedGame, added[0]["id"])
    imported.analysis_json = _analysis()
    await db_session.commit()

    assert await puzzles_service.extract_for_imported(db_session, imported.id) == 1
    assert await puzzles_service.extract_for_imported(db_session, imported.id) == 0
    puzzle = await db_session.scalar(select(PersonalPuzzle))
    assert puzzle.imported_game_id == imported.id and puzzle.game_id is None and puzzle.solution == "g7g6"

    context = await puzzles_service.game_context(db_session, puzzle, test_user_1)
    assert context["opponent"] == "rival" and context["source"] == "pgn" and context["played_at"].startswith("2026-11-01")
    game = client.get(f"{API}/games/{imported.id}", headers=_auth(token_user_1)).json()
    assert game["puzzle_plies"] == [6]

    # Deleting a game also removes the puzzles derived from it.
    assert client.delete(f"{API}/games/{imported.id}", headers=_auth(token_user_1)).status_code == 204
    assert await db_session.scalar(select(func.count()).select_from(PersonalPuzzle)) == 0


async def test_white_mistakes_in_imported_game_are_not_the_players(db_session, client, token_user_1, monkeypatch):
    """A game where the player is White: Black's (the opponent's) blunder does not become a puzzle."""
    monkeypatch.setattr(puzzles_service, "top_two", lambda board: [("g7g6", 0), ("d8e7", -350)])
    added = client.post(f"{API}/pgn", json={"pgn": _pgn("player1", "rival")}, headers=_auth(token_user_1)).json()["added"]
    imported = await db_session.get(ImportedGame, added[0]["id"])
    imported.analysis_json = _analysis()
    await db_session.commit()
    assert await puzzles_service.extract_for_imported(db_session, imported.id) == 0


def test_speed_from_time_control():
    assert game_import.speed_from_time_control("60+0") == "bullet"
    assert game_import.speed_from_time_control("180+2") == "blitz"
    assert game_import.speed_from_time_control("600+0") == "rapid"
    assert game_import.speed_from_time_control("1800+20") == "classical"
    assert game_import.speed_from_time_control("1/86400") == "daily"
    assert game_import.speed_from_time_control("?") is None


# --- Additional coverage: header parsing, sites, saving and on-demand analysis ---------------------------





def test_speed_rating_and_date_helpers_reject_garbage():
    assert game_import.speed_from_time_control("-") == "daily"
    assert game_import.speed_from_time_control("abc+x") is None
    assert game_import._rating("abc") is None and game_import._rating("5000") is None
    assert game_import._rating("2100") == 2100
    headers = chess.pgn.Headers()
    assert game_import._played_at(headers) is None
    headers["UTCDate"], headers["UTCTime"] = "2026.11.01", "10:00:00"
    assert game_import._played_at(headers) == dt.datetime(2026, 11, 1, 10, tzinfo=dt.UTC)
    headers["UTCDate"] = "not a date"
    assert game_import._played_at(headers) is None


def test_read_games_skips_variants_empty_and_broken_games():
    text = (_pgn("a", "b", variant="Crazyhouse") + '[White "x"]\n[Black "y"]\n\n*\n\n'
            + _pgn("c", "d") + "\n\n" + _pgn("e", "f"))
    games = game_import.read_games(text, 5)
    assert [g.headers["White"] for g in games] == ["c", "e"]
    assert len(game_import.read_games(text, 1)) == 1  # game count limit
    assert game_import._color_of(games[0], "  ") is None and game_import._color_of(games[0], "D") == "black"
    assert game_import._color_of(games[0], "nobody") is None


async def test_fetch_validates_source_and_username():
    with pytest.raises(game_import.GameImportError) as unknown:
        await game_import.fetch_games("nowhere", "player1", 5)
    assert unknown.value.code == "import_source_unknown"
    with pytest.raises(game_import.GameImportError) as bad:
        await game_import.fetch_games("lichess", "bad name!", 5)
    assert bad.value.code == "import_username_invalid"


async def test_cooldown_survives_unavailable_redis(monkeypatch):
    class Broken:
        async def get(self, *a, **k):
            raise ConnectionError("no connection")

        async def set(self, *a, **k):
            raise ConnectionError("no connection")

    monkeypatch.setattr(redis_module, "redis_client", Broken())
    await game_import._ensure_source_available("lichess")  # does not fail, the pause simply has no effect
    await game_import._pause_source("lichess")


async def test_lichess_speed_comes_from_event_name(client, sites, token_user_1):
    sites["lichess"] = (_pgn("player1", "a", site="https://lichess.org/aaaa1111", event="Rated Correspondence game")
                        + _pgn("player1", "b", site="https://lichess.org/bbbb2222", event="Casual tournament"))
    response = client.post(f"{API}/fetch", json={"source": "lichess", "username": "player1"}, headers=_auth(token_user_1))
    assert response.status_code == 200, response.text
    listing = client.get(f"{API}/games", headers=_auth(token_user_1)).json()["games"]
    speeds = {g["id"]: g["speed"] for g in listing}
    assert sorted(speeds.values(), key=str) == ["blitz", "daily"]  # no speed in the name: taken from TimeControl


async def test_chesscom_bad_archives_and_odd_items(client, sites, token_user_1, monkeypatch):
    base = settings.GAME_IMPORT_CHESSCOM_URL.rstrip("/")
    archive = f"{base}/pub/player/player1/games/2026/11"
    sites["archives"] = {archive: [
        "not a dict",
        {"rules": "chess", "pgn": ""},
        {"rules": "chess", "pgn": "garbage"},
        {"rules": "chess", "pgn": _pgn("player1", "a", site="x"), "time_class": "rapid"},
    ]}
    response = client.post(f"{API}/fetch", json={"source": "chesscom", "username": "player1"}, headers=_auth(token_user_1))
    assert response.status_code == 200, response.text
    assert len(response.json()["added"]) == 1
    listing = client.get(f"{API}/games", headers=_auth(token_user_1)).json()["games"]
    assert listing[0]["speed"] == "rapid"


async def test_chesscom_non_json_answers_are_site_errors(client, token_user_1, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(game_import.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    response = client.post(f"{API}/fetch", json={"source": "chesscom", "username": "player1"}, headers=_auth(token_user_1))
    assert response.status_code == 502 and response.json()["detail"]["code"] == "import_source_unavailable"


async def test_save_stops_at_room_and_counts_duplicates(client, token_user_1, monkeypatch):
    monkeypatch.setattr(settings, "GAME_IMPORT_MAX_STORED", 2)
    pgn = _pgn("player1", "a", site="https://lichess.org/a1") + _pgn("player1", "b", site="https://lichess.org/b2")
    pgn = pgn.replace("Nf6", "Nh6", 1)  # the second game differs in moves: a different hash for the pasted PGN
    body = client.post(f"{API}/pgn", json={"pgn": _pgn("player1", "a") + _pgn("player1", "a") + pgn},
                       headers=_auth(token_user_1)).json()
    assert len(body["added"]) <= 2 and body["duplicates"] >= 1


async def test_pgn_too_large(client, token_user_1, monkeypatch):
    monkeypatch.setattr(game_import, "MAX_PGN_CHARS", 100)
    response = client.post(f"{API}/pgn", json={"pgn": _pgn("player1", "a")}, headers=_auth(token_user_1))
    assert response.json()["detail"]["code"] == "import_pgn_too_large"


def _no_stockfish(monkeypatch):
    monkeypatch.setattr(analysis_module, "resolve_stockfish_path", lambda *a, **k: None)


async def test_analysis_on_demand_is_cached_and_listed(client, token_user_1, monkeypatch):
    _no_stockfish(monkeypatch)
    monkeypatch.setattr(puzzles_service, "top_two", lambda board: None)
    added = client.post(f"{API}/pgn", json={"pgn": _pgn("player1", "a")}, headers=_auth(token_user_1)).json()["added"]
    game_id = added[0]["id"]
    assert client.get(f"{API}/games/{game_id}/analysis", headers=_auth(token_user_1)).json() is None
    first = client.post(f"{API}/games/{game_id}/analysis", headers=_auth(token_user_1))
    assert first.status_code == 200, first.text
    assert first.json()["game_id"] == game_id and first.json()["summary"] is not None
    cached = client.get(f"{API}/games/{game_id}/analysis", headers=_auth(token_user_1))
    assert cached.status_code == 200 and cached.json()["format_version"] == first.json()["format_version"]
    again = client.post(f"{API}/games/{game_id}/analysis", params={"force": "true"}, headers=_auth(token_user_1))
    assert again.status_code == 200


async def test_analysis_engine_busy_and_domain_errors(client, token_user_1, monkeypatch):
    added = client.post(f"{API}/pgn", json={"pgn": _pgn("player1", "a")}, headers=_auth(token_user_1)).json()["added"]
    game_id = added[0]["id"]

    async def busy(*a, **k):
        raise EngineBusyError("busy")

    monkeypatch.setattr(game_import, "analyze", busy)
    assert client.post(f"{API}/games/{game_id}/analysis", headers=_auth(token_user_1)).status_code == 503

    async def refused(*a, **k):
        raise DomainValueError("illegal_move", move="e2e5")

    monkeypatch.setattr(game_import, "analyze", refused)
    assert client.post(f"{API}/games/{game_id}/analysis", headers=_auth(token_user_1)).status_code == 400


async def test_puzzle_extraction_busy_does_not_spoil_analysis(client, token_user_1, monkeypatch):
    _no_stockfish(monkeypatch)
    added = client.post(f"{API}/pgn", json={"pgn": _pgn("player1", "a")}, headers=_auth(token_user_1)).json()["added"]

    async def busy(*a, **k):
        raise EngineBusyError("busy")

    monkeypatch.setattr(puzzles_service, "extract_for_imported", busy)
    response = client.post(f"{API}/games/{added[0]['id']}/analysis", headers=_auth(token_user_1))
    assert response.status_code == 200


async def test_cached_analysis_ignores_broken_json(db_session, test_user_1):
    record = game_import._record(test_user_1, "pgn", "x", next(iter(game_import.read_games(_pgn("a", "b"), 1))), "white")
    record.analysis_json = "{not json"
    assert game_import.cached_analysis(record) is None
    record.analysis_json = None
    assert game_import.cached_analysis(record) is None
