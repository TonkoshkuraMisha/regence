# --- FILE: src/services/conferences.py ---
"""
Conferences (task 33.6, docs/research/arenas.md section 9): a team competition on top of the common arena pool.

The five conferences are named by compass direction from Ukraine; every country in the world is in exactly one (the COUNTRIES
table below,
conference keys are the same as in the schedule: arena_schedule.CONFERENCE_ZONES). Pairings in arenas are still created
by strength from the whole world, but every player's point also counts towards their conference.

Where the data comes from:

* membership -- the country in the player's profile (users.country, a two-letter ISO 3166-1 code; chosen by the player).
  A country is only suggested from the network address: a proxy in front of the server may name it in a header
  (the COUNTRY_HEADER setting, for example "CF-IPCountry"); the server itself does not map addresses to countries and stores
  nothing
  about this. No country -- no conference: the player plays but brings no conference points;
* changing conference -- at most once per season (a season is a calendar month UTC, as in the team league), so that one cannot
  move to the winning one. The first choice does not count as a change; changing country within the same conference is free;
  the country can always be removed (it is personal data), but that also uses up the season's change (users.country_season);
* arena standings -- the player's conference is remembered on entering the arena (arena_players.conference), so a late change
  of country does not rewrite results. A conference's points in an arena are the sum of the points of its TOP_PLAYERS best
  participants (so that
  a large audience does not win by numbers);
* Conference Cup -- the sum of the standings of all arenas started in the season; computed from arena_players on request;
* conference matches (arena format "match", rules in conference_match_rules.py) -- the matches list: matches of the season and
  upcoming ones, with the sides' scores from arena_players.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.errors import DomainError
from src.models.arena import Arena, ArenaPlayer
from src.models.user import User
from src.services.arena_schedule import CONFERENCE_ZONES
from src.services.league import season_bounds

# How many of a conference's best participants count towards its standing in one arena.
TOP_PLAYERS = 10

# Countries by conference -- 250 codes (ISO 3166-1 alpha-2 plus XK, Kosovo, which has no official code), each
# code appears once. The rule comes from the owner's decision:
# Central -- Ukraine and its neighbours up to the Baltics and the Caucasus; Western -- western Europe and both Americas;
# Northern --
# Germany, Britain, Scandinavia; Southern -- Italy, the Balkans, Turkey, the Middle East and all of Africa; Eastern -- Russia,
# Belarus, the rest of Asia, Australia and Oceania. Small states and territories go with the nearest neighbour.
COUNTRIES: dict[str, tuple[str, ...]] = {
    "central": (
        "UA", "PL", "MD", "RO", "SK", "CZ", "HU", "LT", "LV", "EE", "GE", "AM", "AZ",
    ),
    "western": (
        # Europe
        "FR", "ES", "PT", "BE", "NL", "LU", "CH", "AT", "AD", "MC", "LI", "GI",
        # North, Central and South America, the Caribbean
        "AI", "AG", "AR", "AW", "BS", "BB", "BZ", "BM", "BO", "BQ", "BR", "VG", "CA", "KY", "CL", "CO", "CR", "CU",
        "CW", "DM", "DO", "EC", "SV", "FK", "GF", "GD", "GP", "GT", "GY", "HT", "HN", "JM", "MQ", "MX", "MS", "NI",
        "PA", "PY", "PE", "PR", "BL", "KN", "LC", "MF", "PM", "VC", "SX", "SR", "TT", "TC", "US", "UY", "VE", "VI",
        "GL", "GS", "BV",
    ),
    "northern": (
        "DE", "GB", "IE", "DK", "NO", "SE", "FI", "IS", "FO", "AX", "SJ", "IM", "JE", "GG",
    ),
    "southern": (
        # Europe
        "IT", "GR", "AL", "BA", "HR", "ME", "MK", "RS", "SI", "XK", "BG", "SM", "VA", "MT",
        # Turkey, Cyprus, the Middle East
        "TR", "CY", "SY", "LB", "IL", "PS", "JO", "IQ", "IR", "SA", "YE", "OM", "AE", "QA", "BH", "KW",
        # Africa
        "DZ", "AO", "BJ", "BW", "BF", "BI", "CV", "CM", "CF", "TD", "KM", "CG", "CD", "CI", "DJ", "EG", "GQ", "ER",
        "SZ", "ET", "GA", "GM", "GH", "GN", "GW", "KE", "LS", "LR", "LY", "MG", "MW", "ML", "MR", "MU", "YT", "MA",
        "MZ", "NA", "NE", "NG", "RE", "RW", "SH", "ST", "SN", "SC", "SL", "SO", "ZA", "SS", "SD", "TZ", "TG", "TN",
        "UG", "EH", "ZM", "ZW", "IO", "TF",
        # Antarctica
        "AQ",
    ),
    "eastern": (
        "RU", "BY",
        # Central and South Asia
        "KZ", "UZ", "TM", "KG", "TJ", "IN", "PK", "BD", "LK", "NP", "BT", "MV", "AF",
        # East and Southeast Asia
        "CN", "JP", "KR", "KP", "MN", "TW", "HK", "MO", "TH", "VN", "LA", "KH", "MM", "MY", "SG", "ID", "PH", "BN",
        "TL",
        # Australia and Oceania
        "AU", "NZ", "PG", "FJ", "SB", "VU", "NC", "PF", "WS", "TO", "TV", "KI", "NR", "PW", "FM", "MH", "GU", "MP",
        "AS", "CK", "NU", "TK", "WF", "PN", "NF", "CX", "CC", "HM", "UM",
    ),
}
# Reverse table: country code -> conference key.
CONFERENCE_OF: dict[str, str] = {code: key for key, codes in COUNTRIES.items() for code in codes}
# The conferences of the country table and of the arena schedule must match: a mismatch is an error in one of the two modules.
assert set(COUNTRIES) == set(CONFERENCE_ZONES), "conference keys differ between the country table and the schedule"


def conference_of(country: str | None) -> str | None:
    """The country's conference; with no country or an unknown code -- None."""
    return CONFERENCE_OF.get((country or "").upper())


def current_season(now: datetime | None = None) -> str:
    """Key of the current season "YYYY-MM" (calendar month UTC, league.season_bounds)."""
    return season_bounds(None, now)[0]


def membership(user: User, now: datetime | None = None) -> dict:
    """
    The player's country and conference and whether the conference can be changed now (one change per season): a change is
    available while
    users.country_season does not hold the current season.
    """
    return {"country": user.country, "conference": conference_of(user.country),
            "can_change": user.country_season != current_season(now)}


async def set_country(db: AsyncSession, user: User, country: str | None, now: datetime | None = None) -> dict:
    """
    The country in the profile. The first choice and a change of country within the same conference are free; changing
    conference (including
    leaving it) is once per season: a second attempt in the same season is refused with country_change_too_soon. The country
    can be removed
    at any time, but that uses up the season's change. A country code not in COUNTRIES is refused with country_unknown.
    Returns membership.
    """
    code = country.upper() if country else None
    if code is not None and code not in CONFERENCE_OF:
        raise DomainError("country_unknown")
    season = current_season(now)
    old, new = conference_of(user.country), conference_of(code)
    first_choice = user.country is None and user.country_season is None
    if new != old and not first_choice:
        if new is not None and user.country_season == season:
            raise DomainError("country_change_too_soon", season=season)
        user.country_season = season
    user.country = code
    await db.commit()
    return membership(user, now)


def suggested_country(headers: Mapping[str, str]) -> str | None:
    """The country named by a proxy in front of the server (header from the COUNTRY_HEADER setting) -- only as a hint."""
    name = settings.COUNTRY_HEADER
    code = (headers.get(name) or "").strip().upper() if name else ""
    return code if code in CONFERENCE_OF else None


def team_scores(rows: Iterable[tuple[str | None, int]]) -> list[dict]:
    """
    Conference standings of one arena from pairs (the player's conference, their points): the sum of the TOP_PLAYERS best.
    Returns
    rows {"conference", "score", "counted", "players"} -- by descending score (ties -- in the order of the
    COUNTRIES table); a conference with no participants is absent. counted -- how many players entered the sum, players --
    how many played.
    """
    by_conference: dict[str, list[int]] = defaultdict(list)
    for conference, score in rows:
        if conference in COUNTRIES:
            by_conference[conference].append(score)
    table = []
    for conference, scores in by_conference.items():
        best = sorted(scores, reverse=True)[:TOP_PLAYERS]
        table.append({"conference": conference, "score": sum(best), "counted": len(best), "players": len(scores)})
    order = list(COUNTRIES)
    return sorted(table, key=lambda row: (-row["score"], order.index(row["conference"])))


async def arena_table(db: AsyncSession, arena_id: int) -> list[dict]:
    """Arena conference standings -- by the conferences remembered for participants at entry."""
    rows = (await db.execute(select(ArenaPlayer.conference, ArenaPlayer.score).where(
        ArenaPlayer.arena_id == arena_id, ArenaPlayer.conference.is_not(None)))).all()
    return team_scores((conference, score) for conference, score in rows)


async def cup(db: AsyncSession, season: str | None = None, now: datetime | None = None) -> dict:
    """
    Conference Cup for a season: the sum of arena (and Swiss) standings that started in this month. The table always has all
    five
    conferences: {"conference", "score", "arenas"} -- arenas: in how many arenas the conference scored. Participants
    with points above zero are taken; each arena division is a separate arenas entry and is counted separately.
    """
    key, start, end = season_bounds(season, now)
    rows = (await db.execute(
        select(ArenaPlayer.arena_id, ArenaPlayer.conference, ArenaPlayer.score)
        .join(Arena, Arena.id == ArenaPlayer.arena_id)
        .where(Arena.starts_at >= start, Arena.starts_at < end, ArenaPlayer.conference.is_not(None),
               ArenaPlayer.score > 0)
    )).all()
    by_arena: dict[int, list[tuple[str | None, int]]] = defaultdict(list)
    for arena_id, conference, score in rows:
        by_arena[arena_id].append((conference, score))
    scores = dict.fromkeys(COUNTRIES, 0)
    arenas = dict.fromkeys(COUNTRIES, 0)
    for entries in by_arena.values():
        for row in team_scores(entries):
            scores[row["conference"]] += row["score"]
            arenas[row["conference"]] += 1
    order = list(COUNTRIES)
    ranked = sorted(COUNTRIES, key=lambda conference: (-scores[conference], order.index(conference)))
    table = [{"conference": conference, "score": scores[conference], "arenas": arenas[conference]}
             for conference in ranked]
    return {"season": key, "top_players": TOP_PLAYERS, "table": table}


async def matches(db: AsyncSession, season: str | None = None, now: datetime | None = None) -> list[dict]:
    """
    Conference matches of the season and not yet started: {"arena_id", "home", "guest", "starts_at", "status", "home_score",
    "guest_score", "players"} in start order. Score -- the sides' arena points in match units (win 1, draw 1/2).
    """
    from src.services import arena as arena_service
    from src.services import conference_match_rules as match_rules

    now = now or datetime.now(UTC)
    _, start, end = season_bounds(season, now)
    rows = list((await db.execute(select(Arena).where(
        Arena.format == "match", or_(Arena.starts_at.between(start, end), Arena.starts_at > now))
        .order_by(Arena.starts_at, Arena.id))).scalars())
    if not rows:
        return []
    totals = (await db.execute(select(ArenaPlayer.arena_id, ArenaPlayer.conference, func.sum(ArenaPlayer.score),
                                      func.count()).where(ArenaPlayer.arena_id.in_([a.id for a in rows]))
                               .group_by(ArenaPlayer.arena_id, ArenaPlayer.conference))).all()
    score = {(arena_id, conference): (int(points), int(count)) for arena_id, conference, points, count in totals}
    out = []
    for item in rows:
        home, guest = score.get((item.id, item.conference), (0, 0)), score.get((item.id, item.opponent_conference), (0, 0))
        out.append({"arena_id": item.id, "home": item.conference, "guest": item.opponent_conference,
                    "starts_at": arena_service._aware(item.starts_at).isoformat(),
                    "status": arena_service.status(item, now), "home_score": match_rules.side_score(home[0]),
                    "guest_score": match_rules.side_score(guest[0]), "players": home[1] + guest[1]})
    return out
