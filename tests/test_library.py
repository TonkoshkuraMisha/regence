"""Game library (tasks 27.1-27.2): PGN parsing, merging of identical games, collections, visibility, search, PGN."""

import pytest

from src.services import library

API = "/api/v1/library"

PGN = """[Event "Hastings"]
[Site "Hastings (England)"]
[Date "1934.??.??"]
[White "Botvinnik"]
[Black "Euwe"]
[Result "0-1"]
[ECO "D42"]

1. c4 {comment} c6 (1... e5 2. Nc3) 2. e4 d5 $1 3. exd5 cxd5 0-1

[White "Anon"]
[Black "Anon2"]
[Result "1-0"]

1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0

[White "Broken"]
[Black "Game"]
[Result "*"]

1. e4 e5 2. Ke3 Nf6 *
"""


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_parse_strips_comments_and_variations():
    games = [library.parse_game(g) for g in library.read_text(PGN)]
    first = games[0]
    assert first.moves == ["c2c4", "c7c6", "e2e4", "d7d5", "e4d5", "c6d5"]
    assert (first.year, first.eco, first.result, first.date) == (1934, "D42", "0-1", "1934.??.??")
    assert games[1].eco == "C20" and games[1].opening  # no code in the file: it is determined from the openings table
    assert games[2].moves == ["e2e4", "e7e5"]  # an illegal move truncates the game, not the import
    assert games[0].moves_hash != games[1].moves_hash


def test_open_pgn_reads_cp1251(tmp_path):
    path = tmp_path / "cp1251.pgn"
    path.write_bytes('[White "Ботвинник"]\n[Black "Ласкер"]\n\n1. e4 e5 *\n'.encode("cp1251"))
    with library.open_pgn(str(path)) as handle:
        parsed = library.parse_game(next(library.read_games(handle)))
    assert parsed.white == "Ботвинник"


@pytest.fixture
async def seeded(db_session, test_user_1, test_user_2):
    public = await library.ensure_collection(db_session, "Games/Classics")
    stats = await library.import_games(db_session, public, library.read_text(PGN))
    again = await library.import_games(db_session, public, library.read_text(PGN))
    private = await library.ensure_collection(db_session, "Personal", visibility="owner", owner_id=test_user_1.id)
    await library.import_games(db_session, private, library.read_text(PGN.split("\n\n[White \"Anon\"]")[0]))
    staff = await library.ensure_collection(db_session, "Staff", visibility="staff")
    await library.import_games(db_session, staff, library.read_text(
        '[White "Secret"]\n[Black "X"]\n[Result "1-0"]\n\n1. d4 d5 1-0\n'))
    test_user_2.is_moderator = True
    await db_session.commit()
    return {"public": public.id, "private": private.id, "stats": stats, "again": again}


async def test_import_merges_duplicates(seeded):
    assert (seeded["stats"].added, seeded["stats"].linked) == (3, 3)
    assert (seeded["again"].added, seeded["again"].duplicates, seeded["again"].linked) == (0, 3, 0)


async def test_collections_tree_and_visibility(client, seeded, token_user_1, token_user_2):
    names = lambda body: sorted(c["name"] for c in body["collections"])  # noqa: E731
    guest = client.get(f"{API}/collections").json()
    assert names(guest) == ["Classics", "Games"]
    by_name = {c["name"]: c for c in guest["collections"]}
    assert by_name["Classics"]["parent_id"] == by_name["Games"]["id"] and by_name["Classics"]["games"] == 3
    assert names(client.get(f"{API}/collections", headers=auth(token_user_1)).json()) == ["Classics", "Games", "Personal"]
    assert names(client.get(f"{API}/collections", headers=auth(token_user_2)).json()) == ["Classics", "Games", "Staff"]
    hidden = client.get(f"{API}/collections/{seeded['private']}/games", headers=auth(token_user_2))
    assert hidden.status_code == 404 and hidden.json()["detail"]["code"] == "library_collection_not_found"


async def test_collection_games_search_and_pgn(client, seeded, token_user_2):
    listed = client.get(f"{API}/collections/{seeded['public']}/games").json()
    assert listed["total"] == 3 and [g["white"] for g in listed["games"]] == ["Botvinnik", "Anon", "Broken"]
    assert client.get(f"{API}/games", params={"player": "euw"}).json()["total"] == 1
    assert client.get(f"{API}/games", params={"eco": "c", "result": "1-0"}).json()["games"][0]["white"] == "Anon"
    assert client.get(f"{API}/games", params={"year_from": 1900, "year_to": 1950}).json()["total"] == 1
    assert client.get(f"{API}/games", params={"max_plies": 4}).json()["total"] == 1
    assert client.get(f"{API}/games", params={"player": "secret"}).json()["total"] == 0
    assert client.get(f"{API}/games", params={"structure": "isolated_pawn"}).json()["total"] == 0  # task 27.5
    # The "miniature" tag (27.5): decisive games up to 25 moves; the unfinished "Broken" and the hidden "Secret" do not get it.
    minis = client.get(f"{API}/games", params={"miniature": "true"}).json()
    assert minis["total"] == 2 and {g["white"] for g in minis["games"]} == {"Botvinnik", "Anon"}
    by_moves = client.get(f"{API}/games", params={"moves": "e2e4 e7e5 d1h5"}).json()  # task 27.10
    assert [g["white"] for g in by_moves["games"]] == ["Anon"]
    assert client.get(f"{API}/games", params={"moves": "e2e4 e7e"}).json()["total"] == 0  # whole moves only
    assert client.get(f"{API}/games", params={"moves": "e2e4%"}).status_code == 422
    assert listed["games"][0]["structure"] is None  # short games have no structure
    assert client.get(f"{API}/games", params={"player": "secret"}, headers=auth(token_user_2)).json()["total"] == 1

    game_id = listed["games"][0]["id"]
    full = client.get(f"{API}/games/{game_id}").json()
    assert full["moves"][:2] == ["c2c4", "c7c6"] and [c["name"] for c in full["collections"]] == ["Classics"]
    pgn = client.get(f"{API}/games/{game_id}/pgn").text
    assert '[White "Botvinnik"]' in pgn and "comment" not in pgn and "1. c4 c6 2. e4 d5 3. exd5 cxd5 0-1" in pgn
    secret = client.get(f"{API}/games", params={"player": "secret"}, headers=auth(token_user_2)).json()["games"][0]["id"]
    missing = client.get(f"{API}/games/{secret}/pgn")
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "library_game_not_found"


# --- Extra coverage: rare branches of parsing, import and PGN output ---

CUSTOM_FEN = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"


def test_to_cp1251_leaves_unconvertible_text():
    assert library._to_cp1251("日本") == "日本"  # not encodable in either cp1252 or latin-1


def test_parse_game_rejects_other_variants_bad_fen_and_empty_games():
    games = list(library.read_text(
        '[Variant "Chess960"]\n\n1. e4 e5 *\n\n'
        '[SetUp "1"]\n[FEN "garbage"]\n\n1. e4 *\n\n'
        '[White "NoMoves"]\n\n*\n'))
    assert [library.parse_game(g) for g in games] == [None, None, None]


def test_open_pgn_keeps_utf8_when_multibyte_char_is_cut_by_head(tmp_path):
    path = tmp_path / "long.pgn"
    # A Cyrillic letter (two bytes) cut by the 65536-byte boundary is no reason to treat the file as cp1251.
    path.write_bytes(b"{" + b"a" * 65534 + "й}".encode() + b"\n[White \"X\"]\n\n1. e4 e5 *\n")
    with library.open_pgn(str(path)) as handle:
        assert handle.encoding.lower().replace("_", "-") == "utf-8-sig"


def test_import_stats_add_up():
    total = library.ImportStats(games=1, added=1)
    total += library.ImportStats(games=2, duplicates=1, linked=3, skipped=1)
    assert (total.games, total.added, total.duplicates, total.linked, total.skipped) == (3, 1, 1, 3, 1)


async def test_empty_collection_path_and_small_batches(db_session):
    with pytest.raises(ValueError):
        await library.ensure_collection(db_session, " / ")
    collection = await library.ensure_collection(db_session, "Batches")
    text = PGN + '\n[Variant "Chess960"]\n\n1. d4 d5 *\n'
    stats = await library.import_games(db_session, collection, library.read_text(text), batch=1)
    assert (stats.games, stats.added, stats.skipped) == (4, 3, 1)


def test_structure_and_mate_helpers_for_custom_start_and_bad_moves():
    parsed = library.parse_game(next(library.read_text(f'[SetUp "1"]\n[FEN "{CUSTOM_FEN}"]\n\n1. e4 *\n')))
    assert parsed.start_fen == CUSTOM_FEN
    assert library.structure_of(parsed) is None  # structure comes only from the initial position
    assert library.ends_in_mate(None, ["zzzz"]) is False  # an unparseable move does not break the tag
    assert library.ends_in_mate(None, ["f2f3", "e7e5", "g2g4", "d8h4"]) is True


def test_to_pgn_writes_custom_start_position():
    game = library.LibraryGame(white="A", black="B", moves="e2e4", start_fen=CUSTOM_FEN, white_elo=None, black_elo=None,
                               event="", site="", date="", round="", result="*", eco="", opening="")
    text = library.to_pgn(game)
    assert f'[FEN "{CUSTOM_FEN}"]' in text and "1. e4" in text
