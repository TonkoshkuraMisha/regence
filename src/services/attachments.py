# --- FILE: src/services/attachments.py ---
"""
Player attachment cards (tasks 30.1 and 30.2): a game, position, puzzle, lesson, tournament, library game — in direct
messages and the feed; one's own achievement — only in the feed. The server validates the reference and snapshots the data at
send time (names,
result, puzzle rating); captions in three languages are built by the client — there are no UI strings here.

A library game is attached only if it lies in a public collection: materials with restricted visibility
(one's own private ones, internal ones) do not go out, even if the author can see them.

What is checked per kind: game, puzzle, tournament and library game — a record with such an id exists in the database (games,
puzzles, tournaments, library_games); position — the FEN is readable and the position is possible; achievement — unlocked for
the author
(user_achievements); lesson — only the identifier format: lessons live in client files, the server does not store them.
Callers: src/services/direct_messages.py (kinds MESSAGE_KINDS) and src/services/feed.py (POST_KINDS).
"""

import re

import chess
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainError
from src.models.achievement import UserAchievement
from src.models.game import Game
from src.models.library import LibraryCollection, LibraryGame, LibraryGameCollection
from src.models.puzzle import Puzzle
from src.models.tournament import Tournament
from src.models.user import User

# Card kinds that can be attached to a direct message, and to a feed post (which also allows one's own achievement).
MESSAGE_KINDS = ("game", "position", "puzzle", "lesson", "tournament", "library")
POST_KINDS = (*MESSAGE_KINDS, "achievement")
# Valid format of a lesson identifier and an achievement code (checked before touching the database).
LESSON_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
ACHIEVEMENT_CODE = re.compile(r"^[a-z0-9_]{1,32}$")


def clean_text(text: str | None, limit: int) -> str:
    """
    Trims the edges and extra blank lines; line breaks inside are kept. Several blank lines in a row become one,
    trailing spaces on lines are removed, the result is cut to limit characters.
    """
    lines = [line.rstrip() for line in (text or "").strip().splitlines()]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out)[:limit]


async def _usernames(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = await db.execute(select(User.id, User.username).where(User.id.in_(ids)))
    return {uid: name for uid, name in rows.all()}


def _invalid() -> DomainError:
    return DomainError("attachment_invalid")


async def _numeric(db: AsyncSession, kind: str, key: int) -> dict:
    """
    Card for kinds with a record id: a game (player names, result, status), a puzzle (position and rating),
    a library game (only from a public collection) and a tournament with bots (format, size, status, owner). No record
    — attachment_invalid.
    """
    if kind == "game":
        game = await db.get(Game, key)
        if game is None:
            raise _invalid()
        names = await _usernames(db, {game.white_player_id, game.black_player_id})
        return {"kind": kind, "ref": str(game.id), "white": names.get(game.white_player_id),
                "black": names.get(game.black_player_id), "result": game.result,
                "status": game.status.value if hasattr(game.status, "value") else str(game.status)}
    if kind == "puzzle":
        puzzle = await db.get(Puzzle, key)
        if puzzle is None:
            raise _invalid()
        return {"kind": kind, "ref": str(puzzle.id), "fen": puzzle.fen, "rating": puzzle.rating}
    if kind == "library":
        public = exists().where(LibraryGameCollection.game_id == LibraryGame.id,
                                LibraryGameCollection.collection_id == LibraryCollection.id,
                                LibraryCollection.visibility == "public")
        item = await db.scalar(select(LibraryGame).where(LibraryGame.id == key, public))
        if item is None:
            raise _invalid()
        return {"kind": kind, "ref": str(item.id), "white": item.white, "black": item.black,
                "result": item.result, "year": item.year, "event": item.event}
    tournament = await db.get(Tournament, key)
    if tournament is None:
        raise _invalid()
    owner = (await _usernames(db, {tournament.owner_id})).get(tournament.owner_id)
    return {"kind": kind, "ref": str(tournament.id), "format": tournament.format, "size": tournament.size,
            "status": tournament.status, "owner": owner, "event_key": tournament.event_key,
            "career_stage": tournament.career_stage}


async def build_attachment(db: AsyncSession, kind: str, ref: str, *, author: User,
                           kinds: tuple[str, ...] = MESSAGE_KINDS) -> dict:
    """
    Validates the reference and snapshots the card. Error — attachment_invalid. kind is the card kind (must be in kinds),
    ref is a record id, a position FEN, a lesson identifier or an achievement code (at most 100 characters); author is needed
    only for an achievement: only one's own can be attached. Returns a dict with "kind", "ref" and a data snapshot — it
    is stored together with the message and is not updated later.
    """
    ref = (ref or "").strip()
    if kind not in kinds or not ref or len(ref) > 100:
        raise _invalid()
    if kind in ("game", "puzzle", "tournament", "library"):
        if not ref.isdigit():
            raise _invalid()
        return await _numeric(db, kind, int(ref))
    if kind == "position":
        try:
            board = chess.Board(ref)
        except ValueError:
            raise _invalid() from None
        if not board.is_valid():
            raise _invalid()
        return {"kind": kind, "ref": board.fen()}
    if kind == "achievement":
        earned = await db.scalar(select(UserAchievement.earned_at).where(
            UserAchievement.user_id == author.id, UserAchievement.code == ref)) if ACHIEVEMENT_CODE.match(ref) else None
        if earned is None:
            raise _invalid()
        return {"kind": kind, "ref": ref, "earned_at": earned.isoformat()}
    if not LESSON_ID.match(ref):
        raise _invalid()
    return {"kind": kind, "ref": ref}
