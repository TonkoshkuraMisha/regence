# --- FILE: tests/test_legends_season.py ---
"""Season table of the legends weeks (task 26.1): weekly points, season weeks, ties, the database path and the route."""

import datetime as dt

from sqlalchemy import select

from src.models.tournament import TournamentPlayer
from src.services import legends_season, legends_week, time_machine

API = "/api/v1/tournaments"
TODAY = dt.date(2026, 11, 26)  # a Thursday of the week starting on Monday 23.11


def test_week_points_for_the_top_ten_plus_finishing():
    assert legends_season.week_points(1) == 25 + legends_season.FINISH_POINTS
    assert legends_season.week_points(10) == 1 + legends_season.FINISH_POINTS
    assert legends_season.week_points(11) == legends_season.FINISH_POINTS  # outside the top ten: taking part still counts


def test_season_weeks_start_on_mondays_inside_the_month_up_to_now():
    start, end = dt.date(2026, 11, 1), dt.date(2026, 12, 1)  # 1.11.2026 is a Sunday
    assert legends_season.season_mondays(start, end, TODAY) == [dt.date(2026, 11, d) for d in (2, 9, 16, 23)]
    # A finished month: every Monday in it, including the 30th (that week belongs to November, not split).
    assert legends_season.season_mondays(start, end, dt.date(2027, 1, 5))[-1] == dt.date(2026, 11, 30)
    assert legends_season.season_mondays(dt.date(2027, 1, 1), dt.date(2027, 2, 1), TODAY) == []  # not started yet


def test_points_then_wins_then_name_and_shared_places():
    week = lambda *rows: [{"place": p, "user_id": u, "username": n} for p, u, n in rows]  # noqa: E731
    table = legends_season.season_table([
        week((1, 1, "ann"), (2, 2, "bob")),
        week((1, 2, "bob"), (2, 1, "ann"), (3, 3, "cid")),
        week((2, 4, "dan")),
    ])
    assert [(e["username"], e["points"], e["wins"], e["place"]) for e in table] == [
        ("ann", 45, 1, 1), ("bob", 45, 1, 1), ("dan", 19, 0, 3), ("cid", 16, 0, 4)]
    assert table[0]["weeks"] == 2


async def _run(db, user, monday: dt.date, place: int):
    """A finished run of the week's event, dated on that Monday."""
    run = await time_machine.start(db, user, legends_week.event_for_week(monday).key, 600_000, 0)
    run.status = "finished"
    run.created_at = dt.datetime.combine(monday, dt.time(12), dt.UTC)
    player = await db.scalar(select(TournamentPlayer).where(
        TournamentPlayer.tournament_id == run.id, TournamentPlayer.user_id == user.id))
    player.place = place
    await db.commit()


async def test_season_sums_the_weeks_of_the_month(db_session, test_user_1, test_user_2):
    await _run(db_session, test_user_1, dt.date(2026, 11, 9), 2)
    await _run(db_session, test_user_1, dt.date(2026, 11, 16), 4)
    await _run(db_session, test_user_2, dt.date(2026, 11, 16), 1)
    await _run(db_session, test_user_2, dt.date(2026, 10, 26), 1)  # October's week: another season

    table = await legends_season.standings(db_session, test_user_2.id, "2026-11", TODAY)
    assert table["season"] == "2026-11" and table["weeks"] == ["2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23"]
    # Week 9.11: test_user_1 alone - 1st (26). Week 16.11: test_user_2 1st (26), test_user_1 2nd (19).
    assert [(r["username"], r["points"], r["wins"], r["weeks"]) for r in table["rows"]] == [
        (test_user_1.username, 45, 1, 2), (test_user_2.username, 26, 1, 1)]
    assert table["me"]["username"] == test_user_2.username and table["me"]["place"] == 2


def test_route_is_open_to_a_guest_and_checks_the_season(client):
    body = client.get(f"{API}/legends-week/season").json()
    assert body["rows"] == [] and body["me"] is None and len(body["season"]) == 7
    assert client.get(f"{API}/legends-week/season", params={"season": "2026-11"}).json()["season"] == "2026-11"
    assert client.get(f"{API}/legends-week/season", params={"season": "2026-13"}).status_code == 422
