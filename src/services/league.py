# --- FILE: src/services/league.py ---
"""
Teams and the seasonal league (task 17.2). A season is a calendar month (UTC). Points are given by finished rated games
between humans from DIFFERENT teams played in the season (the team roster is the current one):

* win: 2 + (opponent's rating - own) / 200, rounded, from 1 to 4 -- a win over a strong opponent is worth more;
* draw: 1, and against an opponent stronger by DRAW_BONUS_GAP or more -- 2;
* loss: 0.

Ratings are at the start of the game (games.white_initial_rating / black_initial_rating); if the rating is not recorded in
the game,
1200 is used. A game belongs to a season by its end time (games.finished_at). There are no points tables: points
are computed on every request from the games table and the current rosters (teams, team_members), so a player's move to
another team carries their season points with them. The season key and its bounds (season_bounds) are also used by the
Conference
Cup (src/services/conferences.py).
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainError
from src.models.game import Game, GameStatus
from src.models.team import Team, TeamMember
from src.models.user import User

# A draw against an opponent stronger by this many rating points or more brings 2 points instead of 1.
DRAW_BONUS_GAP = 200
# The allowed team name length in characters (after collapsing spaces).
NAME_MIN, NAME_MAX = 3, 30


def win_points(mine: int, opponent: int) -> int:
    """
    League points for a win: 2 plus a point for every 200 points of the opponent's rating advantage (minus -- for one's own
    advantage), within 1 to 4. Rounding is Python's round: exactly a half rounds to even.
    """
    return max(1, min(4, 2 + round((opponent - mine) / 200)))


def draw_points(mine: int, opponent: int) -> int:
    """League points for a draw: 1, and against an opponent stronger by DRAW_BONUS_GAP or more -- 2."""
    return 2 if opponent - mine >= DRAW_BONUS_GAP else 1


# A season key in requests: "YYYY-MM" (season_bounds); the team league and the legends season table accept it.
SEASON_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


def season_bounds(season: str | None = None, now: datetime | None = None) -> tuple[str, datetime, datetime]:
    """
    (the key "YYYY-MM", start, end) of the season; by default -- the current month. The start is the first day of the month
    at 00:00 UTC,
    the end is the first day of the next month (not part of the season).
    """
    if season:
        year, month = (int(part) for part in season.split("-"))
    else:
        now = now or datetime.now(UTC)
        year, month = now.year, now.month
    start = datetime(year, month, 1, tzinfo=UTC)
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=UTC)
    return f"{year:04d}-{month:02d}", start, end


async def team_of(db: AsyncSession, user_id: int) -> Team | None:
    """The player's team (a player belongs to at most one) or None."""
    return (await db.execute(
        select(Team).join(TeamMember, TeamMember.team_id == Team.id).where(TeamMember.user_id == user_id)
    )).scalar_one_or_none()


async def create_team(db: AsyncSession, user: User, name: str) -> Team:
    """
    Creates a team: a name from NAME_MIN to NAME_MAX characters, unique case-insensitively; the player must not belong to
    another team. The creator becomes the owner and the first member.
    """
    clean = " ".join(name.split())
    if not NAME_MIN <= len(clean) <= NAME_MAX:
        raise DomainError("team_name_invalid", min=NAME_MIN, max=NAME_MAX)
    if await team_of(db, user.id) is not None:
        raise DomainError("team_already_member")
    if await db.scalar(select(Team.id).where(func.lower(Team.name) == clean.lower())) is not None:
        raise DomainError("team_name_taken")
    team = Team(name=clean, owner_id=user.id)
    db.add(team)
    await db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id))
    await db.commit()
    await db.refresh(team)
    return team


async def join_team(db: AsyncSession, user: User, team_id: int) -> Team:
    """Joining a team; a player who already belongs to any team is refused."""
    team = await db.get(Team, team_id)
    if team is None:
        raise DomainError("team_not_found")
    if await team_of(db, user.id) is not None:
        raise DomainError("team_already_member")
    db.add(TeamMember(team_id=team.id, user_id=user.id))
    await db.commit()
    return team


async def leave_team(db: AsyncSession, user: User) -> None:
    """
    Leave a team. When the last member leaves, the team is deleted; when the owner leaves, the member who joined earlier than
    the others becomes
    the owner. A player without a team -- refusal team_not_member.
    """
    member = (await db.execute(select(TeamMember).where(TeamMember.user_id == user.id))).scalar_one_or_none()
    if member is None:
        raise DomainError("team_not_member")
    team = await db.get(Team, member.team_id)
    await db.delete(member)
    await db.flush()
    rest = (await db.execute(
        select(TeamMember).where(TeamMember.team_id == member.team_id).order_by(TeamMember.joined_at, TeamMember.id)
    )).scalars().first()
    if team is not None:
        if rest is None:
            await db.delete(team)
        elif team.owner_id == user.id:
            team.owner_id = rest.user_id
    await db.commit()


async def season_points(db: AsyncSession, season: str | None = None) -> tuple[str, dict[int, int], dict[int, int]]:
    """
    (season, points by teams, points by players) -- from the season's games between different teams. Finished rated
    games (not simulations) are taken where both players currently belong to teams; games within one team and
    games without an ordinary result are skipped.
    """
    key, start, end = season_bounds(season)
    team_by_user = {uid: tid for uid, tid in (await db.execute(select(TeamMember.user_id, TeamMember.team_id))).all()}
    if not team_by_user:
        return key, {}, {}
    rows = (await db.execute(
        select(Game.white_player_id, Game.black_player_id, Game.result, Game.white_initial_rating,
               Game.black_initial_rating)
        .where(Game.status == GameStatus.COMPLETED, Game.is_rated.is_(True), Game.is_simulation.is_(False),
               Game.finished_at >= start, Game.finished_at < end,
               Game.white_player_id.in_(team_by_user), Game.black_player_id.in_(team_by_user))
    )).all()
    teams: dict[int, int] = {}
    players: dict[int, int] = {}
    for white, black, result, white_rating, black_rating in rows:
        if team_by_user[white] == team_by_user[black] or result not in ("1-0", "0-1", "1/2-1/2"):
            continue
        wr, br = white_rating or 1200, black_rating or 1200
        if result == "1-0":
            earned = {white: win_points(wr, br)}
        elif result == "0-1":
            earned = {black: win_points(br, wr)}
        else:
            earned = {white: draw_points(wr, br), black: draw_points(br, wr)}
        for user_id, value in earned.items():
            players[user_id] = players.get(user_id, 0) + value
            teams[team_by_user[user_id]] = teams.get(team_by_user[user_id], 0) + value
    return key, teams, players


async def table(db: AsyncSession, season: str | None = None) -> dict:
    """The league table for a season: teams by descending points, with the number of members and the place."""
    key, team_points, _ = await season_points(db, season)
    rows = (await db.execute(
        select(Team.id, Team.name, func.count(TeamMember.id)).join(TeamMember, TeamMember.team_id == Team.id)
        .group_by(Team.id, Team.name)
    )).all()
    standings = sorted(({"id": tid, "name": name, "members": count, "points": team_points.get(tid, 0)}
                        for tid, name, count in rows), key=lambda r: (-r["points"], r["name"].lower()))
    for place, row in enumerate(standings, 1):
        row["place"] = place
    return {"season": key, "teams": standings}


async def team_view(db: AsyncSession, team_id: int, season: str | None = None) -> dict:
    """A team page: the roster by descending season points and the team's total points."""
    team = await db.get(Team, team_id)
    if team is None:
        raise DomainError("team_not_found")
    key, team_points, player_points = await season_points(db, season)
    members = (await db.execute(
        select(User.id, User.username).join(TeamMember, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == team_id).order_by(User.username)
    )).all()
    roster = sorted(({"username": name, "points": player_points.get(uid, 0), "owner": uid == team.owner_id}
                     for uid, name in members), key=lambda m: (-m["points"], m["username"].lower()))
    return {"id": team.id, "name": team.name, "season": key, "points": team_points.get(team.id, 0), "members": roster}
