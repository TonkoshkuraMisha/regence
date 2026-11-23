# --- FILE: src/services/account.py ---
"""
Player account (tasks 17.5 and 23.1, GDPR): export of one's own data and account deletion.

The export (export_data, games_pgn) reads the tables games, bot_personalities, lesson_progress, theme_progress,
puzzle_attempts, personal_puzzles, drill_records, tournaments and imported_games; routes are in src/api/account.py.

Deletion is anonymisation, not row removal: games are shared with opponents and stay in their history, but without the
player's name (deleted_<id>). Personal data is erased: personas, lesson and puzzle progress, personal puzzles, imported games,
records, tournaments with bots, email links (email_tokens), product events, arena reminders, e-mail and
country in the profile, ladder and tournament sessions in Redis. The password is replaced with an unusable hash, all tokens are
revoked
(users.token_version + 1), open WebSockets are closed. The exact list of erased tables is the tuple in delete_account;
tables not listed there are left untouched by deletion.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import ApiError
from src.core.security import get_password_hash
from src.models.arena import ArenaReminder
from src.models.email_token import EmailToken
from src.models.game import Game, GameStatus
from src.models.imported_game import ImportedGame
from src.models.lesson import LessonProgress
from src.models.personality import BotPersonality
from src.models.product_event import ProductEvent
from src.models.puzzle import DrillRecord, PersonalPuzzle, PuzzleAttempt, ThemeProgress
from src.models.tournament import Tournament
from src.models.user import User

# Version of the export document structure ("format" field): bumped when the set or meaning of the fields changes.
EXPORT_FORMAT = 1


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def export_data(db: AsyncSession, user: User) -> dict:
    """
    The player's data as one JSON document: profile with ratings, games (with PGN and opponent name), bot personas,
    lesson and theme progress, puzzle attempts, personal puzzles, imported games, drill records and tournaments with
    bots. Only the listed sections are included; the password and internal profile fields are not exported.
    """
    games = (await db.execute(
        select(Game).where(or_(Game.white_player_id == user.id, Game.black_player_id == user.id))
        .order_by(Game.created_at)
    )).scalars().all()
    opponent_ids = {g.black_player_id if g.white_player_id == user.id else g.white_player_id for g in games}
    names: dict[int, str] = {}
    if opponent_ids:
        rows = await db.execute(select(User.id, User.username).where(User.id.in_(opponent_ids)))
        names = {row.id: row.username for row in rows}

    personalities = (await db.execute(
        select(BotPersonality).where(BotPersonality.owner_id == user.id))).scalars().all()
    lessons = (await db.execute(select(LessonProgress).where(LessonProgress.user_id == user.id))).scalars().all()
    themes = (await db.execute(select(ThemeProgress).where(ThemeProgress.user_id == user.id))).scalars().all()
    attempts = (await db.execute(select(PuzzleAttempt).where(PuzzleAttempt.user_id == user.id)
                                 .order_by(PuzzleAttempt.created_at))).scalars().all()
    personal = (await db.execute(select(PersonalPuzzle).where(PersonalPuzzle.user_id == user.id))).scalars().all()
    records = (await db.execute(select(DrillRecord).where(DrillRecord.user_id == user.id))).scalars().all()
    tournaments = (await db.execute(select(Tournament).where(Tournament.owner_id == user.id))).scalars().all()
    imported = (await db.execute(select(ImportedGame).where(ImportedGame.user_id == user.id)
                                 .order_by(ImportedGame.id))).scalars().all()

    return {
        "format": EXPORT_FORMAT,
        "exported_at": datetime.now(UTC).isoformat(),
        "profile": {
            "id": user.id, "username": user.username, "email": user.email, "created_at": _iso(user.created_at),
            "ratings": {
                "bullet": user.bullet_rating, "blitz": user.blitz_rating,
                "rapid": user.rapid_rating, "classical": user.classical_rating,
                "ladder": user.ladder_rating, "puzzles": user.puzzle_rating,
            },
            "games_played": {
                "bullet": user.bullet_games_played, "blitz": user.blitz_games_played,
                "rapid": user.rapid_games_played, "classical": user.classical_games_played,
                "ladder": user.ladder_games, "puzzles": user.puzzle_games,
            },
        },
        "games": [
            {
                "id": g.id, "color": "white" if g.white_player_id == user.id else "black",
                "opponent": names.get(g.black_player_id if g.white_player_id == user.id else g.white_player_id),
                "result": g.result, "termination": g.termination, "status": g.status.value,
                "base_time_ms": g.base_time_ms, "increment_ms": g.increment_ms, "is_rated": g.is_rated,
                "created_at": _iso(g.created_at), "finished_at": _iso(g.finished_at), "pgn": g.pgn,
            }
            for g in games
        ],
        "personalities": [
            {"name": p.name, "config_json": p.config_json, "created_at": _iso(p.created_at)} for p in personalities
        ],
        "lessons": [
            {"lesson": lp.lesson_id, "step": lp.step, "steps_total": lp.steps_total,
             "completed_at": _iso(lp.completed_at), "exam_score": lp.exam_score, "exam_total": lp.exam_total}
            for lp in lessons
        ],
        "puzzle_themes": [
            {"theme": tp.theme, "stage": tp.stage, "solved": tp.solved, "mastered": tp.mastered} for tp in themes
        ],
        "puzzle_attempts": [
            {"puzzle_id": a.puzzle_id, "solved": a.solved, "hints_used": a.hints_used,
             "rating_before": a.rating_before, "rating_after": a.rating_after, "at": _iso(a.created_at)}
            for a in attempts
        ],
        "personal_puzzles": [
            {"game_id": pp.game_id, "imported_game_id": pp.imported_game_id, "ply": pp.ply, "fen": pp.fen,
             "played": pp.played, "solution": pp.solution, "done": pp.done}
            for pp in personal
        ],
        # Games from other sites (task 24.1): brought by the player, so they are returned to the same player.
        "imported_games": [
            {"id": g.id, "source": g.source, "external_id": g.external_id, "color": g.color, "white": g.white_name,
             "black": g.black_name, "result": g.result, "speed": g.speed, "played_at": _iso(g.played_at),
             "imported_at": _iso(g.created_at), "pgn": g.pgn}
            for g in imported
        ],
        "drill_records": [{"combo": r.combo, "best": r.best} for r in records],
        "tournaments": [
            {"id": t.id, "format": t.format, "size": t.size, "status": t.status,
             "created_at": _iso(t.created_at), "finished_at": _iso(t.finished_at)}
            for t in tournaments
        ],
    }


# How many games one PGN export request returns; the client requests the rest with an offset.
GAMES_PGN_LIMIT = 5000


async def games_pgn(db: AsyncSession, user: User, offset: int = 0) -> tuple[str, int]:
    """
    All completed games of the player as one PGN document (task 24.3), oldest to newest; at most GAMES_PGN_LIMIT per
    request (further ones via offset). Games with status COMPLETED and a non-empty games.pgn are taken (aborted ones are
    excluded).
    Returns the text and the total number of such games.
    """
    conditions = (
        or_(Game.white_player_id == user.id, Game.black_player_id == user.id),
        Game.status == GameStatus.COMPLETED, Game.pgn.is_not(None), Game.pgn != "",
    )
    total = await db.scalar(select(func.count(Game.id)).where(*conditions)) or 0
    rows = (await db.scalars(
        select(Game.pgn).where(*conditions).order_by(Game.finished_at, Game.id).offset(offset).limit(GAMES_PGN_LIMIT)
    )).all()
    text = "\n\n".join((pgn or "").strip() for pgn in rows)
    return (text + "\n" if text else ""), total


async def delete_account(db: AsyncSession, user: User) -> None:
    """
    Anonymises the account and erases personal data; a game in progress or awaiting start is refused with 409 account_in_game
    (it must be finished first). The users row stays: name and username_key become deleted_<id>, deleted_at is set, a new
    random password is assigned; bumping token_version revokes all issued tokens. After the database write, the fair-play
    sessions in Redis are dropped and the player's open connections are closed.
    """
    active = await db.scalar(select(Game.id).where(
        or_(Game.white_player_id == user.id, Game.black_player_id == user.id),
        Game.status.in_((GameStatus.PENDING, GameStatus.IN_PROGRESS)),
    ).limit(1))
    if active is not None:
        raise ApiError(409, "account_in_game")

    for model, column in (
            (BotPersonality, BotPersonality.owner_id), (LessonProgress, LessonProgress.user_id),
            (ThemeProgress, ThemeProgress.user_id), (PuzzleAttempt, PuzzleAttempt.user_id),
            (PersonalPuzzle, PersonalPuzzle.user_id), (ImportedGame, ImportedGame.user_id),
            (DrillRecord, DrillRecord.user_id),
            (Tournament, Tournament.owner_id), (EmailToken, EmailToken.user_id),
            (ProductEvent, ProductEvent.user_id), (ArenaReminder, ArenaReminder.user_id),
    ):
        await db.execute(delete(model).where(column == user.id))

    anonymous = f"deleted_{user.id}"
    user.username = anonymous
    user.username_key = anonymous
    user.email = None
    # Country from the profile (task 33.6) is personal data; points already earned for a conference in arenas stay.
    user.country = None
    user.country_season = None
    user.hashed_password = get_password_hash(secrets.token_urlsafe(32))
    user.deleted_at = datetime.now(UTC)
    user.token_version = (user.token_version or 0) + 1
    await db.commit()

    # Fair-play sessions (ladder, tournament) and open WebSockets.
    from src.services import ladder
    from src.services.connection_manager import manager

    for scope in ladder.SCOPES:
        await ladder.clear_session(user.id, scope)
    await manager.revoke_sessions(user.id)
