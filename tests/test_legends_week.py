# --- FILE: tests/test_legends_week.py ---
"""Weekly tournament against the legends (task 26.1): the weekly rotation of events and the table of the best runs."""

import datetime as dt

from sqlalchemy import select

from src.models.tournament import TournamentPlayer
from src.services import legends_week, time_machine
from src.services.time_machine import EVENTS

API = "/api/v1/tournaments"
MONDAY = dt.date(2026, 11, 23)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_rotation_is_stable_within_a_week_and_walks_the_registry():
    first = legends_week.event_for_week(MONDAY)
    assert legends_week.event_for_week(MONDAY) is first
    seen = [legends_week.event_for_week(MONDAY + dt.timedelta(weeks=n)).key for n in range(len(EVENTS))]
    # A full cycle visits every event once, and the next week is always a different event.
    assert sorted(seen) == sorted(event.key for event in EVENTS)


def test_week_window_runs_monday_to_monday():
    assert legends_week.week_window(dt.date(2026, 11, 29)) == (MONDAY, dt.date(2026, 11, 30))


async def _finish(db, tournament, place: int, user_id: int) -> None:
    tournament.status = "finished"
    player = await db.scalar(select(TournamentPlayer).where(
        TournamentPlayer.tournament_id == tournament.id, TournamentPlayer.user_id == user_id))
    player.place = place
    await db.commit()


async def test_table_counts_only_finished_runs_of_this_weeks_event(db_session, test_user_1, test_user_2):
    today = dt.datetime.now(dt.UTC).date()
    event = legends_week.event_for_week(legends_week.week_window(today)[0])
    other = next(e for e in EVENTS if e.key != event.key)

    assert (await legends_week.standings(db_session, test_user_1.id))["rows"] == []
    run = await time_machine.start(db_session, test_user_1, event.key, 600_000, 0)
    assert (await legends_week.standings(db_session))["rows"] == []  # still running
    await _finish(db_session, run, 5, test_user_1.id)
    await _finish(db_session, await time_machine.start(db_session, test_user_1, event.key, 600_000, 0), 3, test_user_1.id)
    await _finish(db_session, await time_machine.start(db_session, test_user_2, event.key, 600_000, 0), 3, test_user_2.id)
    await _finish(db_session, await time_machine.start(db_session, test_user_2, other.key, 600_000, 0), 1, test_user_2.id)

    table = await legends_week.standings(db_session, test_user_1.id)
    assert table["event_key"] == event.key
    # The best run of each player counts; the other event is ignored; equal places are shared.
    assert [(row["place"], row["tournament_place"]) for row in table["rows"]] == [(1, 3), (1, 3)]
    assert table["me"]["place"] == 1


async def test_cheater_is_left_out(db_session, test_user_1):
    event = legends_week.event_for_week(legends_week.week_window()[0])
    await _finish(db_session, await time_machine.start(db_session, test_user_1, event.key, 600_000, 0), 2, test_user_1.id)
    test_user_1.is_cheater = True
    await db_session.commit()
    table = await legends_week.standings(db_session, test_user_1.id)
    assert table["rows"] == [] and table["me"] is None


def test_endpoint_is_open_to_a_guest(client):
    body = client.get(f"{API}/legends-week").json()
    assert body["event_key"] in {event.key for event in EVENTS} and body["rows"] == [] and body["me"] is None


async def _dated_run(db, user, monday: dt.date, place: int) -> None:
    """A finished run of that week's event, created on that Monday."""
    run = await time_machine.start(db, user, legends_week.event_for_week(monday).key, 600_000, 0)
    run.status = "finished"
    run.created_at = dt.datetime.combine(monday, dt.time(12), dt.UTC)
    await _finish(db, run, place, user.id)


async def test_week_start_notifies_recent_players_once(db_session, test_user_1, test_user_2, monkeypatch):
    from src.models.social import Notification
    from src.services import notifications

    delivered: list[int] = []

    async def deliver(user_id, notification):
        delivered.append(user_id)

    monkeypatch.setattr(notifications, "deliver", deliver)
    # test_user_1 played two weeks ago (a regular); test_user_2 last played six weeks ago (beyond LOOKBACK_WEEKS).
    await _dated_run(db_session, test_user_1, MONDAY - 2 * legends_week.WEEK, 3)
    await _dated_run(db_session, test_user_2, MONDAY - 6 * legends_week.WEEK, 1)

    assert await legends_week.send_week_start(db_session, MONDAY) == 1
    assert delivered == [test_user_1.id]
    note = await db_session.scalar(select(Notification).where(Notification.user_id == test_user_1.id))
    assert note.kind == legends_week.NOTIFICATION_KIND
    assert note.payload == {"event_key": legends_week.event_for_week(MONDAY).key}
    # A repeated run of the task in the same week sends nothing new.
    assert await legends_week.send_week_start(db_session, MONDAY + dt.timedelta(days=1)) == 0
