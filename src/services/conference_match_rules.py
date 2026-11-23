# --- FILE: src/services/conference_match_rules.py ---
"""
Conference matches (task 33.6, "later"; scheme approved by the owner on 18.11.2026). Pure rules with no database or network --
a simple test checks them (tests/test_conference_matches.py); games and standings are handled by src/services/arena.py (arena
format "match"), and matches are created on schedule by arena.ensure_schedule.

* Schedule: once a week -- a match between two conferences in a round-robin. Five conferences give PAIRS (ten pairs),
  so a cycle is ten weeks. The week is counted from EPOCH (a Monday); in an odd cycle host and guest swap places,
  so that every conference hosts matches in turn.
* Time: Saturday MATCH_WEEKDAY, evening, convenient for both. The earliest EVENING_HOURS hour in the host's time that is
  also evening for the guest is chosen; if there is no common evening -- DEFAULT_HOUR in the host's time (and the host
  alternates by cycle, so the next meeting of these two conferences will be in the other side's evening).
* Sign-up: any player of one of the two conferences (country in the profile), no strength thresholds (rule 7 of CLAUDE.md:
  a conference is a team, not a division by strength). Sign-up closes LINEUP_BEFORE before the start: by then the
  line-ups are already known.
* Line-ups: each side's sign-ups by rating at entry (ties -- earlier sign-up first); board 1 plays board 1 and so on,
  boards -- by the smaller side, the rest are reserves with no games.
* Games: two rounds, on each board one game as White and one as Black (in the first round the host has White on odd boards,
  in the second the colours swap). Time control MATCH_SLOT (5+3), games are rated.
* Score: win -- 1, draw -- 1/2; the match score is the sum over boards. In arena_players points are stored in arena units
  (win 2, draw 1), so a side's score is their sum divided by POINTS_PER_WIN.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from src.services.arena_schedule import CONFERENCE_ZONES, Slot

# Time control, duration (planned window of the two rounds) and number of rounds of a match.
MATCH_SLOT = Slot("match-5+3", 300_000, 3_000, timedelta(hours=2), "match", 2)
# The Monday from which the weeks of the cycle are counted.
EPOCH = date(2026, 1, 5)
# Match day is Saturday (date.weekday(): Monday is 0).
MATCH_WEEKDAY = 5
# Evening start hours in local time (18:00-22:00) and the default hour when there is no common evening.
EVENING_HOURS = range(18, 23)
DEFAULT_HOUR = 19
# How long before the start sign-up closes and line-ups become known.
LINEUP_BEFORE = timedelta(hours=1)
# How far ahead schedule matches are created: the next match is visible for sign-up all week.
MATCH_LOOKAHEAD = timedelta(days=8)
# Arena points per win: match score = arena points / POINTS_PER_WIN (win 1, draw 1/2).
POINTS_PER_WIN = 2

# Conferences in CONFERENCE_ZONES order (arena_schedule): the line-up and the order of the cycle's pairs depend on it.
_ORDER = tuple(CONFERENCE_ZONES)


def round_robin(teams: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """
    All pairs of the cycle by the circle method: the first team stays put, the others (with an empty slot for odd count)
    rotate;
    pairs of the rounds go in sequence, so different conferences play in adjacent weeks.
    """
    seats: list[str | None] = [*teams, None] if len(teams) % 2 else list(teams)
    rest, pairs = seats[1:], []
    for _ in range(len(seats) - 1):
        current = [seats[0], *rest]
        for i in range(len(seats) // 2):
            a, b = current[i], current[-1 - i]
            if a and b:
                pairs.append((a, b))
        rest = [rest[-1], *rest[:-1]]
    return tuple(pairs)


# The ten pairs of the cycle of five conferences (each plays each other once per cycle).
PAIRS = round_robin(_ORDER)


def fixture(week: int) -> tuple[str, str]:
    """(host, guest) of the match of week number week from EPOCH; in an odd cycle the sides swap."""
    home, guest = PAIRS[week % len(PAIRS)]
    return (guest, home) if (week // len(PAIRS)) % 2 else (home, guest)


def match_start(home: str, guest: str, saturday: date) -> datetime:
    """
    Match start in UTC: the host's earliest evening hour that is also evening for the guest; else the host's DEFAULT_HOUR.
    """
    home_zone, guest_zone = ZoneInfo(CONFERENCE_ZONES[home]), ZoneInfo(CONFERENCE_ZONES[guest])
    for hour in EVENING_HOURS:
        moment = datetime(saturday.year, saturday.month, saturday.day, hour, tzinfo=home_zone)
        if moment.astimezone(guest_zone).hour in EVENING_HOURS:
            return moment.astimezone(UTC)
    return datetime(saturday.year, saturday.month, saturday.day, DEFAULT_HOUR, tzinfo=home_zone).astimezone(UTC)


@dataclass(frozen=True)
class PlannedMatch:
    """A schedule match: key, host, guest, start in UTC."""
    schedule_key: str
    home: str
    guest: str
    starts_at: datetime

    @property
    def ends_at(self) -> datetime:
        """Planned end of the match: start + duration of the MATCH_SLOT window."""
        return self.starts_at + MATCH_SLOT.duration


def planned_matches(now: datetime, horizon: timedelta, active: Sequence[str] = _ORDER) -> list[PlannedMatch]:
    """
    Matches that are running now or start within the next horizon. A match of a pair where one of the conferences is not in
    active
    (the ARENA_CONFERENCES setting) is not created.
    """
    out = []
    today = now.astimezone(UTC).date()
    first_week = (today - EPOCH).days // 7 - 1
    for week in range(first_week, first_week + horizon.days // 7 + 3):
        home, guest = fixture(week)
        if home not in active or guest not in active:
            continue
        saturday = EPOCH + timedelta(weeks=week, days=MATCH_WEEKDAY)
        starts_at = match_start(home, guest, saturday)
        if starts_at < now + horizon and starts_at + MATCH_SLOT.duration > now:
            out.append(PlannedMatch(f"{home}-{guest}:{MATCH_SLOT.key}", home, guest, starts_at))
    return out


def entry_open(starts_at: datetime, now: datetime) -> bool:
    """Sign-up is open: more than LINEUP_BEFORE remains until the start."""
    return now < starts_at - LINEUP_BEFORE


class Member(Protocol):
    """A signed-up player (ArenaPlayer): only the fields the rules need."""
    user_id: int
    rating: int
    conference: str | None


def lineup(members: Sequence[Member], home: str, guest: str,
           joined_order: Sequence[int] | None = None) -> list[tuple[Member, Member]]:
    """
    Match boards: [(host's player, guest's player)] -- sides by rating at entry (ties -- by joined_order,
    the list of user_ids in sign-up order), boards -- by the smaller side.
    """
    rank = {uid: i for i, uid in enumerate(joined_order or [m.user_id for m in members])}

    def side(conference: str) -> list[Member]:
        return sorted((m for m in members if m.conference == conference),
                      key=lambda m: (-m.rating, rank.get(m.user_id, len(rank))))

    return list(zip(side(home), side(guest), strict=False))


def board_colors(board: int, round_no: int) -> bool:
    """
    Whether the host of board board (from 1) in round round_no (from 1) plays White: odd boards in round one, even in round
    two.
    """
    return (board % 2 == 1) == (round_no % 2 == 1)


def side_score(points: int) -> float:
    """Arena points of a side -> match score (win 1, draw 1/2)."""
    return points / POINTS_PER_WIN
