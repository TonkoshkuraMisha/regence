# --- FILE: src/services/arena_schedule.py ---
"""
Arena schedule by conference (task 33.4, docs/research/arenas.md §4, §6, §9).

Each conference has a "home" time zone, and the schedule of its arenas is given in its local time (DAY_PLAN):

* evening (18:00-23:00): blitz 3+2 every hour (60 min); an hour later a second arena runs next to it — bullet 2+1 at 18:00 and
  at 22:00
  (45 min), and at 20:00 the evening 5+3 (90 min), the main arena of the day;
* night and day: blitz 3+2 once every three hours;
* Swiss: 10+5 every day at 15:00, 15+10 on Sundays at 11:00 (5 rounds each).

At most two tournaments run at the same time in one conference (checked by a test a week ahead). One may play in the
arena of any conference: the time zone only determines when arenas run more often. There are no arenas "for one's own strength"
in the schedule:
every arena is open to any registered player (owner decision of 17.11.2026). The list of conference countries and the
standing are task 33.6; here only the conference keys and their zones are needed.

The module is pure: for a point in time it returns which arenas must exist; arena.ensure_schedule creates them.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.core.config import settings

# Conference key -> its home time zone (IANA).
CONFERENCE_ZONES: dict[str, str] = {
    "central": "Europe/Kyiv",
    "western": "America/New_York",
    "northern": "Europe/Berlin",
    "southern": "Europe/Istanbul",
    "eastern": "Asia/Kolkata",
}
# Sunday number in date.weekday() (Monday is 0).
SUNDAY = 6


@dataclass(frozen=True)
class Slot:
    """
    Schedule tournament kind: key, time control (base and increment in ms), duration, format ("arena" or "swiss")
    and number of rounds (Swiss only). For a Swiss the duration is a planned window: the end is determined by the rounds
    played.
    """
    key: str
    base_time_ms: int
    increment_ms: int
    duration: timedelta
    format: str = "arena"
    rounds: int = 0


BLITZ = Slot("blitz-3+2", 180_000, 2_000, timedelta(minutes=60))
BULLET = Slot("bullet-2+1", 120_000, 1_000, timedelta(minutes=45))
EVENING = Slot("evening-5+3", 300_000, 3_000, timedelta(minutes=90))
SWISS_DAILY = Slot("swiss-10+5", 600_000, 5_000, timedelta(hours=3), "swiss", 5)
SWISS_WEEKLY = Slot("swiss-15+10", 900_000, 10_000, timedelta(hours=4), "swiss", 5)

# Conference local hour -> tournament. Evening — every hour plus a second arena an hour later; the rest of the time — less
# often.
DAY_PLAN: tuple[tuple[int, Slot], ...] = (
    (0, BLITZ), (3, BLITZ), (6, BLITZ), (9, BLITZ), (12, BLITZ), (15, BLITZ),
    (15, SWISS_DAILY),
    (18, BLITZ), (19, BLITZ), (20, BLITZ), (21, BLITZ), (22, BLITZ),
    (18, BULLET), (20, EVENING), (22, BULLET),
)
# Day of week and local hour -> a tournament once a week.
WEEK_PLAN: tuple[tuple[int, int, Slot], ...] = ((SUNDAY, 11, SWISS_WEEKLY),)


@dataclass(frozen=True)
class Planned:
    """Schedule tournament: key "conference:slot", start in UTC and parameters."""
    schedule_key: str
    conference: str
    slot: Slot
    starts_at: datetime

    @property
    def ends_at(self) -> datetime:
        return self.starts_at + self.slot.duration


def active_conferences() -> tuple[str, ...]:
    """Conferences for which arenas are created: the ARENA_CONFERENCES setting (by default all five)."""
    wanted = [item.strip() for item in settings.ARENA_CONFERENCES.split(",")]
    return tuple(key for key in CONFERENCE_ZONES if key in wanted)


def day_events(conference: str, day: date) -> list[tuple[datetime, Slot]]:
    """Conference tournaments starting on this day of its local time: (start in UTC, slot)."""
    zone = ZoneInfo(CONFERENCE_ZONES[conference])
    plan = list(DAY_PLAN) + [(hour, slot) for weekday, hour, slot in WEEK_PLAN if day.weekday() == weekday]
    events = [(datetime(day.year, day.month, day.day, hour, tzinfo=zone).astimezone(UTC), slot) for hour, slot in plan]
    return sorted(events, key=lambda item: (item[0], item[1].key))


def planned(now: datetime, horizon: timedelta) -> list[Planned]:
    """
    Tournaments that are running now or will start within the nearest horizon, over all active conferences, in start order.
    Local conference days from yesterday to the day after tomorrow are scanned: this covers both a tournament started
    before midnight and a horizon of several hours.
    """
    out: dict[tuple[str, datetime], Planned] = {}
    for conference in active_conferences():
        today = now.astimezone(ZoneInfo(CONFERENCE_ZONES[conference])).date()
        for offset in (-1, 0, 1, 2):
            for starts_at, slot in day_events(conference, today + timedelta(days=offset)):
                if not (starts_at < now + horizon and starts_at + slot.duration > now):
                    continue
                key = f"{conference}:{slot.key}"
                # The switch to winter time repeats an hour: one key and moment is one tournament.
                out.setdefault((key, starts_at), Planned(key, conference, slot, starts_at))
    return sorted(out.values(), key=lambda item: (item.starts_at, item.schedule_key))


def is_evening(schedule_key: str | None) -> bool:
    """The evening 5+3 arena is the main arena of its conference's day; recognised by the key part after ":"."""
    return bool(schedule_key) and str(schedule_key).split(":")[-1] == EVENING.key
