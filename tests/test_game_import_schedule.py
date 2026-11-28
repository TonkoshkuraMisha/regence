# --- FILE: tests/test_game_import_schedule.py ---
"""
Import on a schedule (task 24.1): subscribing through the API, the scheduled run (due once a day, a busy site is left
for the next hour, a refusal is recorded, fair play and deletion skip the player) and the personal-data rules. The sites
are the stubs of test_game_import.py; the network and the engine are never touched.
"""

import datetime as dt

from sqlalchemy import func, select

from src.models.imported_game import ImportedGame, ImportSubscription
from src.services import account, game_import_schedule
from src.worker.celery_app import celery_app
from tests.test_game_import import _auth, _pgn, sites  # noqa: F401 - the stubbed sites fixture is used by name

API = "/api/v1/imports/subscriptions"
NOW = dt.datetime(2026, 11, 28, 6, 29, tzinfo=dt.UTC)


async def _subscription(db, user, source="lichess", username="player1", last_run_at=None) -> ImportSubscription:
    row = ImportSubscription(user_id=user.id, source=source, username=username, last_added=0, last_run_at=last_run_at)
    db.add(row)
    await db.commit()
    return row


async def test_subscribe_list_change_and_cancel(client, sites, token_user_1):  # noqa: F811
    on = client.put(f"{API}/lichess", json={"username": "player1"}, headers=_auth(token_user_1))
    assert on.status_code == 200, on.text
    assert on.json() == {"source": "lichess", "username": "player1", "last_run_at": None, "last_added": 0,
                         "last_error": None}
    assert sites["requests"] == []  # nothing is fetched at subscription time: the schedule does it
    client.put(f"{API}/chesscom", json={"username": "Other_1"}, headers=_auth(token_user_1))
    client.put(f"{API}/lichess", json={"username": "player2"}, headers=_auth(token_user_1))
    listed = client.get(API, headers=_auth(token_user_1)).json()["subscriptions"]
    assert [(s["source"], s["username"]) for s in listed] == [("chesscom", "Other_1"), ("lichess", "player2")]
    assert client.delete(f"{API}/chesscom", headers=_auth(token_user_1)).status_code == 204
    assert [s["source"] for s in client.get(API, headers=_auth(token_user_1)).json()["subscriptions"]] == ["lichess"]


async def test_subscription_input_is_validated(client, token_user_1):
    assert client.put(f"{API}/fide", json={"username": "player1"}, headers=_auth(token_user_1)).status_code == 422
    assert client.put(f"{API}/lichess", json={"username": "a b"}, headers=_auth(token_user_1)).status_code == 422
    assert client.get(API).status_code == 401


async def test_due_subscription_imports_once_a_day(db_session, sites, test_user_1):  # noqa: F811
    sites["lichess"] = _pgn("player1", "rival")
    row = await _subscription(db_session, test_user_1)
    first = await game_import_schedule.run_due(db_session, now=NOW)
    assert first["runs"] == 1 and len(first["added"]) == 1
    await db_session.refresh(row)
    assert row.last_added == 1 and row.last_error is None and row.last_run_at is not None
    # An hour later it is not due; a day later it runs again and the same game is a duplicate.
    assert (await game_import_schedule.run_due(db_session, now=NOW + dt.timedelta(hours=1)))["runs"] == 0
    again = await game_import_schedule.run_due(db_session, now=NOW + game_import_schedule.IMPORT_INTERVAL)
    assert again == {"runs": 1, "added": []}
    assert await db_session.scalar(select(func.count()).select_from(ImportedGame)) == 1


async def test_busy_site_is_left_for_the_next_run(db_session, sites, test_user_1, test_user_2):  # noqa: F811
    sites["status"] = 429
    first = await _subscription(db_session, test_user_1)
    second = await _subscription(db_session, test_user_2, username="player2")
    result = await game_import_schedule.run_due(db_session, now=NOW)
    assert result == {"runs": 0, "added": []}
    assert len(sites["requests"]) == 1  # the second player's import does not knock on a busy site
    for row in (first, second):
        await db_session.refresh(row)
        assert row.last_run_at is None  # still due: tried again in an hour


async def test_player_refusal_is_recorded(db_session, sites, test_user_1):  # noqa: F811
    sites["status"] = 404
    row = await _subscription(db_session, test_user_1, username="nobody")
    assert (await game_import_schedule.run_due(db_session, now=NOW))["runs"] == 1
    await db_session.refresh(row)
    assert row.last_error == "import_player_not_found" and row.last_run_at is not None


async def test_players_in_a_game_or_leaving_are_skipped(db_session, sites, test_user_1, test_user_2,  # noqa: F811
                                                       monkeypatch):
    async def in_game(user_id: int) -> bool:
        return user_id == test_user_1.id

    monkeypatch.setattr(game_import_schedule, "_in_game_with_human", in_game)
    sites["lichess"] = _pgn("player2", "rival")
    await _subscription(db_session, test_user_1)
    await _subscription(db_session, test_user_2, username="player2")
    test_user_2.deletion_requested_at = NOW
    await db_session.commit()
    assert await game_import_schedule.run_due(db_session, now=NOW) == {"runs": 0, "added": []}
    assert sites["requests"] == []


async def test_usernames_are_exported_and_erased(db_session, test_user_1):
    await _subscription(db_session, test_user_1)
    exported = await account.export_data(db_session, test_user_1)
    assert [(s["source"], s["username"]) for s in exported["import_subscriptions"]] == [("lichess", "player1")]
    await account.anonymise(db_session, test_user_1, now=NOW)
    assert await db_session.scalar(select(func.count()).select_from(ImportSubscription)) == 0


def test_beat_runs_the_import_every_hour():
    import src.worker.tasks  # noqa: F401 - registers the tasks with the Celery app

    entry = celery_app.conf.beat_schedule["import-subscriptions"]
    assert entry["task"] == "import_subscriptions" and "import_subscriptions" in celery_app.tasks
