# --- FILE: tests/test_arena_schedule.py ---
"""Arena schedule by conferences, the lobby announcement and start reminders (task 33.4)."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from src.core.config import settings
from src.models.arena import Arena, ArenaPlayer, ArenaReminder
from src.models.social import Notification
from src.services import arena, notifications
from src.services import arena_schedule as plan
from src.services import conference_match_rules as match_rules

API = "/api/v1/arenas"
NOW = datetime(2026, 11, 18, 17, 30, tzinfo=UTC)          # Wednesday, 19:30 in Kyiv


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _home_hours(conference: str, day: date) -> dict[str, list[int]]:
    """Tournaments of a conference day: slot -> start hours in its local time."""
    zone = ZoneInfo(plan.CONFERENCE_ZONES[conference])
    hours: dict[str, list[int]] = {}
    for starts_at, slot in plan.day_events(conference, day):
        hours.setdefault(slot.key, []).append(starts_at.astimezone(zone).hour)
    return hours


# --- Schedule ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("conference", list(plan.CONFERENCE_ZONES))
def test_day_plan_is_the_same_in_every_home_zone(conference):
    """In the evening local time — blitz every hour, bullet and an evening 5+3; otherwise — blitz once every three hours."""
    assert _home_hours(conference, date(2026, 11, 18)) == {
        "blitz-3+2": [0, 3, 6, 9, 12, 15, 18, 19, 20, 21, 22],
        "bullet-2+1": [18, 22],
        "evening-5+3": [20],
        "swiss-10+5": [15],
    }
    assert _home_hours(conference, date(2026, 11, 22))["swiss-15+10"] == [11]   # Sunday — Swiss 15+10


def test_evening_arena_follows_the_home_clock():
    def evening(conference: str, day: date) -> list[datetime]:
        return [starts_at for starts_at, slot in plan.day_events(conference, day) if slot is plan.EVENING]

    assert evening("central", date(2026, 11, 18)) == [datetime(2026, 11, 18, 18, 0, tzinfo=UTC)]   # 20:00 in Kyiv in winter
    assert evening("central", date(2026, 7, 15)) == [datetime(2026, 7, 15, 17, 0, tzinfo=UTC)]     # and in summer
    assert evening("northern", date(2026, 11, 18)) == [datetime(2026, 11, 18, 19, 0, tzinfo=UTC)]  # Berlin
    assert evening("southern", date(2026, 11, 18)) == [datetime(2026, 11, 18, 17, 0, tzinfo=UTC)]  # Istanbul
    assert evening("western", date(2026, 11, 18)) == [datetime(2026, 11, 19, 1, 0, tzinfo=UTC)]    # New York
    assert evening("eastern", date(2026, 11, 18)) == [datetime(2026, 11, 18, 14, 30, tzinfo=UTC)]  # Delhi


@pytest.mark.parametrize("conference", list(plan.CONFERENCE_ZONES))
@pytest.mark.parametrize("first_day", [date(2026, 11, 15), date(2026, 3, 6), date(2026, 3, 27), date(2026, 10, 23),
                                       date(2026, 10, 30)])
def test_never_more_than_two_tournaments_at_once_in_a_conference(conference, first_day):
    """A schedule week, including the weeks of daylight-saving changes in Europe and America."""
    events = [event for offset in range(9) for event in plan.day_events(conference, first_day + timedelta(days=offset))]
    assert len(events) > 100
    for starts_at, _slot in events:
        running = [slot.key for other, slot in events if other <= starts_at < other + slot.duration]
        assert len(running) <= 2, (starts_at, running)


def test_planned_window_keys_and_active_conferences(monkeypatch):
    items = plan.planned(NOW, timedelta(hours=6))
    assert {item.conference for item in items} == set(plan.CONFERENCE_ZONES)
    assert all(item.starts_at < NOW + timedelta(hours=6) and item.ends_at > NOW for item in items)
    central = {(item.schedule_key, item.starts_at.hour) for item in items if item.conference == "central"}
    # Kyiv, 19:30: the blitz started at 19:00 is running; ahead: evening 5+3 at 20:00, blitz every hour, bullet at 22:00.
    assert central == {("central:blitz-3+2", 17), ("central:blitz-3+2", 18), ("central:evening-5+3", 18),
                       ("central:blitz-3+2", 19), ("central:blitz-3+2", 20), ("central:bullet-2+1", 20),
                       ("central:blitz-3+2", 22)}
    assert len({(item.schedule_key, item.starts_at) for item in items}) == len(items)

    assert max(len(item.schedule_key) for item in items) <= 32                 # length of the arenas.schedule_key field
    # The schedule has no arenas "up to such-and-such rating": the key is "conference:slot", with no cap.
    assert all(item.schedule_key == f"{item.conference}:{item.slot.key}" for item in items)

    monkeypatch.setattr(settings, "ARENA_CONFERENCES", "central, eastern, unknown")
    assert {item.conference for item in plan.planned(NOW, timedelta(hours=6))} == {"central", "eastern"}


async def test_schedule_is_created_once_with_its_conference(db_session):
    await arena.ensure_schedule(db_session, NOW)
    first = await db_session.scalar(select(func.count()).select_from(Arena))
    await arena.ensure_schedule(db_session, NOW)
    # Arenas LOOKAHEAD ahead and conference matches a week and a bit ahead (match_rules.MATCH_LOOKAHEAD).
    assert await db_session.scalar(select(func.count()).select_from(Arena)) == first == len(
        plan.planned(NOW, arena.LOOKAHEAD)) + len(match_rules.planned_matches(NOW, match_rules.MATCH_LOOKAHEAD))
    evening = (await db_session.execute(select(Arena).where(Arena.schedule_key == "central:evening-5+3"))).scalar_one()
    assert (evening.conference, evening.base_time_ms, evening.increment_ms) == ("central", 300_000, 3_000)
    view = arena.view(evening, NOW)
    assert (view["conference"], view["evening"], view["status"], view["berserk"]) == ("central", True, "scheduled", True)
    blitz = (await db_session.execute(select(Arena).where(Arena.schedule_key == "northern:blitz-3+2")
                                      .order_by(Arena.starts_at))).scalars().first()
    assert arena.view(blitz, NOW)["evening"] is False and blitz.conference == "northern"


async def test_retired_empty_arenas_are_removed_but_joined_ones_stay(db_session, test_user_1, monkeypatch):
    def old(key: str | None, starts_in: timedelta) -> Arena:
        return Arena(schedule_key=key, base_time_ms=60_000, increment_ms=0, starts_at=NOW + starts_in,
                     ends_at=NOW + starts_in + timedelta(minutes=30))

    # Arenas of the former schedule (before 33.4): empty future, future with a participant, already running; and a one-off.
    empty, joined, running, one_off = (old("bullet-1+0", timedelta(hours=1)), old("rapid-10+0", timedelta(hours=2)),
                                       old("blitz-3+2", timedelta(minutes=-10)), old(None, timedelta(hours=1)))
    db_session.add_all([empty, joined, running, one_off])
    await db_session.commit()
    db_session.add_all([ArenaPlayer(arena_id=joined.id, user_id=test_user_1.id, rating=1500),
                        ArenaReminder(arena_id=empty.id, user_id=test_user_1.id)])
    await db_session.commit()

    await arena.ensure_schedule(db_session, NOW)
    left = set((await db_session.execute(select(Arena.id))).scalars())
    assert empty.id not in left and {joined.id, running.id, one_off.id} <= left
    assert await db_session.scalar(select(func.count()).select_from(ArenaReminder)) == 0

    # The conference was disabled: its future empty arenas go away, those already running are played out.
    monkeypatch.setattr(settings, "ARENA_CONFERENCES", "central")
    await arena.ensure_schedule(db_session, NOW)
    rows = (await db_session.execute(select(Arena.conference, Arena.starts_at).where(
        Arena.conference.is_not(None)))).all()
    future = {conference for conference, starts_at in rows if arena._aware(starts_at) > NOW}
    assert future == {"central"}
    assert {conference for conference, _ in rows} > {"central"}


# --- List and lobby announcement -----------------------------------------------------------------------------


async def test_lobby_banner_points_to_an_arena_one_can_play_in(client, db_session, test_user_1, monkeypatch):
    monkeypatch.setattr(settings, "ARENA_CONFERENCES", "")                      # only the arenas of this test
    now = datetime.now(UTC)

    def blitz(started: timedelta, left: timedelta) -> Arena:
        return Arena(base_time_ms=180_000, increment_ms=2_000, starts_at=now - started, ends_at=now + left,
                     conference="central")

    assert client.get(f"{API}/current").json() == {"arena": None}
    closing, upcoming = (blitz(timedelta(minutes=50), timedelta(minutes=5)),
                         blitz(timedelta(minutes=-10), timedelta(minutes=70)))
    finished_empty, finished_played = (blitz(timedelta(hours=2), timedelta(hours=-1)),
                                       blitz(timedelta(hours=3), timedelta(hours=-2)))
    db_session.add_all([closing, upcoming, finished_empty, finished_played])
    await db_session.commit()
    db_session.add(ArenaPlayer(arena_id=finished_played.id, user_id=test_user_1.id, rating=1500))
    await db_session.commit()

    # The running arena's last start has passed — the announcement leads to the nearest future one, with its start time.
    current = client.get(f"{API}/current").json()["arena"]
    assert (current["id"], current["status"], current["conference"]) == (upcoming.id, "scheduled", "central")
    assert datetime.fromisoformat(current["starts_at"]) == upcoming.starts_at

    quiet, busy = blitz(timedelta(minutes=5), timedelta(minutes=55)), blitz(timedelta(minutes=5), timedelta(minutes=55))
    db_session.add_all([quiet, busy])
    await db_session.commit()
    db_session.add(ArenaPlayer(arena_id=busy.id, user_id=test_user_1.id, rating=1500))
    await db_session.commit()
    current = client.get(f"{API}/current").json()["arena"]
    assert (current["id"], current["players"], current["status"]) == (busy.id, 1, "running")

    # List: a finished arena without participants is not shown, a played one stays.
    listed = {item["id"]: item for item in client.get(API).json()["arenas"]}
    assert set(listed) == {closing.id, upcoming.id, finished_played.id, quiet.id, busy.id}
    assert (listed[busy.id]["players"], listed[finished_played.id]["status"]) == (1, "finished")


# --- Reminders -----------------------------------------------------------------------------------------------


async def test_reminder_through_the_real_client_path(client, db_session, test_user_1, token_user_1, monkeypatch):
    monkeypatch.setattr(settings, "ARENA_CONFERENCES", "")
    delivered = []

    async def fake_deliver(user_id, notification):
        delivered.append((user_id, notification["kind"], notification["payload"]))

    monkeypatch.setattr(notifications, "deliver", fake_deliver)
    now = datetime.now(UTC)
    soon = Arena(base_time_ms=180_000, increment_ms=2_000, starts_at=now + timedelta(minutes=20),
                 ends_at=now + timedelta(minutes=80), conference="central")
    running = Arena(base_time_ms=180_000, increment_ms=2_000, starts_at=now - timedelta(minutes=5),
                    ends_at=now + timedelta(minutes=55))
    db_session.add_all([soon, running])
    await db_session.commit()
    headers = auth(token_user_1)

    assert client.post(f"{API}/{soon.id}/remind").status_code == 401            # without login — nobody to remind
    assert client.get(f"{API}/{soon.id}", headers=headers).json()["me"]["reminder"] is False
    for _ in range(2):                                                          # a repeat does not create a second reminder
        assert client.post(f"{API}/{soon.id}/remind", headers=headers).json() == {"reminder": True}
    assert await db_session.scalar(select(func.count()).select_from(ArenaReminder)) == 1
    assert client.get(f"{API}/{soon.id}", headers=headers).json()["me"]["reminder"] is True
    late = client.post(f"{API}/{running.id}/remind", headers=headers)
    assert late.status_code == 409 and late.json()["detail"]["code"] == "arena_reminder_too_late"
    assert client.post(f"{API}/999999/remind", headers=headers).status_code == 404

    # 20 minutes before the start — too early; 5 minutes before — a notification, and only one.
    assert await arena.send_reminders(db_session, now) == 0
    assert await arena.send_reminders(db_session, soon.starts_at - arena.REMIND_BEFORE) == 1
    assert await arena.send_reminders(db_session, soon.starts_at - timedelta(minutes=1)) == 0
    assert delivered == [(test_user_1.id, "arena_reminder", {
        "arena_id": soon.id, "base_time_ms": 180_000, "increment_ms": 2_000, "starts_at": soon.starts_at.isoformat()})]
    bell = client.get("/api/v1/social/notifications", headers=headers).json()
    assert (bell["unread"], [item["kind"] for item in bell["items"]]) == (1, ["arena_reminder"])

    # "Do not remind" removes the reminder; the arena ended — a late reminder no longer goes out.
    assert client.delete(f"{API}/{soon.id}/remind", headers=headers).json() == {"reminder": False}
    assert client.get(f"{API}/{soon.id}", headers=headers).json()["me"]["reminder"] is False
    db_session.add(ArenaReminder(arena_id=soon.id, user_id=test_user_1.id))
    await db_session.commit()
    assert await arena.send_reminders(db_session, soon.ends_at + timedelta(minutes=1)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Notification)) == 1


def test_arena_reminders_run_every_minute():
    from celery.schedules import crontab

    from src.worker.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["arena-reminders"]
    assert entry["task"] == "arena_reminders" and entry["schedule"] == crontab()
    assert "arena_reminders" in celery_app.tasks
    assert celery_app.conf.task_routes["arena_reminders"] == {"queue": "analysis"}
