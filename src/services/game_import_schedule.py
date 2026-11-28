# --- FILE: src/services/game_import_schedule.py ---
"""
Import on a schedule (task 24.1): a player who opts in gets his new games from lichess or chess.com every day, without
pressing "import". The imported games go to the same review with the mentor and personal puzzles as a manual import.

Rules:
* Opt-in per site: the player gives his own username there (the same check as a manual import); one subscription per
  site, a new username replaces the old one. Nothing is fetched at subscription time - the first run comes with the
  schedule.
* A subscription is due once IMPORT_INTERVAL has passed since its last run. The beat task (src/worker/tasks.py,
  import_subscriptions, every hour) takes at most RUN_BATCH due subscriptions, the longest waiting first, and imports up to
  GAMES_PER_RUN recent games for each - through game_import.import_from_site, so the same politeness to the sites holds
  (one request per site at a time, a 429 pauses the site for everyone).
* A site that is busy or down (SITE_PROBLEMS) is skipped for the rest of the run, and its subscriptions stay due:
  they are tried again in an hour. Any other refusal (unknown user, storage full) is recorded as last_error and the
  subscription waits for the next day.
* Fair play (rule 2): a player in a game with a human is skipped in this run - the review of imported games is an engine
  review, and during a game it is closed for manual imports too.
* An account waiting for deletion is not imported for; on deletion the rows are erased (account.PERSONAL_TABLES).

Data: the import_subscriptions table (models/imported_game.py, ImportSubscription), the user's active game in Redis
(game_state.state_manager). Called by src/api/game_import.py (subscribe, list, cancel) and the worker task.
"""

import datetime as dt
import logging

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.imported_game import ImportSubscription
from src.models.user import User
from src.services import game_import

logger = logging.getLogger(__name__)

# A subscription runs once a day: the player's new games arrive by the next morning, the sites see one request a day.
IMPORT_INTERVAL = dt.timedelta(hours=24)
# Recent games fetched per run: a day of active play; repeats are skipped by game_import as duplicates.
GAMES_PER_RUN = 10
# Due subscriptions handled per hourly run: keeps one run short and spreads the requests to the sites over the day.
RUN_BATCH = 50
# Refusals that belong to the site, not to the player: the site is left alone until the next run.
SITE_PROBLEMS = frozenset({"import_source_busy", "import_source_unavailable"})


def view(subscription: ImportSubscription) -> dict:
    """A subscription for the client: the site, the username and how the last run went."""
    last = subscription.last_run_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=dt.UTC)
    return {"source": subscription.source, "username": subscription.username,
            "last_run_at": last.isoformat() if last else None, "last_added": subscription.last_added,
            "last_error": subscription.last_error}


async def list_for(db: AsyncSession, user: User) -> list[dict]:
    """The player's subscriptions, by site."""
    rows = (await db.scalars(select(ImportSubscription).where(ImportSubscription.user_id == user.id)
                             .order_by(ImportSubscription.source))).all()
    return [view(row) for row in rows]


async def subscribe(db: AsyncSession, user: User, source: str, username: str) -> dict:
    """Turns the daily import from a site on (or changes the username); refusals are GameImportError codes."""
    if source not in game_import.SOURCES:
        raise game_import.GameImportError("import_source_unknown")
    if not game_import.USERNAME_RE.match(username):
        raise game_import.GameImportError("import_username_invalid")
    row = await db.scalar(select(ImportSubscription).where(ImportSubscription.user_id == user.id,
                                                           ImportSubscription.source == source))
    if row is None:
        row = ImportSubscription(user_id=user.id, source=source, username=username, last_added=0)
        db.add(row)
    elif row.username != username:
        # Another account on the site: the next run should come soon, and the old result does not describe it.
        row.username, row.last_run_at, row.last_added, row.last_error = username, None, 0, None
    await db.commit()
    return view(row)


async def unsubscribe(db: AsyncSession, user: User, source: str) -> None:
    """Turns the daily import from a site off; already imported games stay."""
    await db.execute(delete(ImportSubscription).where(ImportSubscription.user_id == user.id,
                                                      ImportSubscription.source == source))
    await db.commit()


async def _in_game_with_human(user_id: int) -> bool:
    from src.services.game_state import state_manager

    return await state_manager.get_active_game_id(user_id) is not None


async def run_due(db: AsyncSession, now: dt.datetime | None = None, limit: int = RUN_BATCH) -> dict:
    """
    One scheduled run: imports for up to limit due subscriptions. Returns {"runs", "added": [imported game ids]} - the
    caller sends the new games to the background review.
    """
    now = now or dt.datetime.now(dt.UTC)
    rows = (await db.execute(
        select(ImportSubscription, User).join(User, User.id == ImportSubscription.user_id)
        .where(User.deletion_requested_at.is_(None), User.deleted_at.is_(None),
               or_(ImportSubscription.last_run_at.is_(None), ImportSubscription.last_run_at <= now - IMPORT_INTERVAL))
        .order_by(ImportSubscription.last_run_at.asc().nulls_first(), ImportSubscription.id)
        .limit(limit)
    )).all()
    busy: set[str] = set()
    added: list[int] = []
    runs = 0
    for subscription, user in rows:
        if subscription.source in busy or await _in_game_with_human(user.id):
            continue
        try:
            result = await game_import.import_from_site(db, user, subscription.source, subscription.username,
                                                        GAMES_PER_RUN)
        except game_import.GameImportError as exc:
            if exc.code in SITE_PROBLEMS:
                busy.add(subscription.source)
                continue
            logger.info("Scheduled import refused: user %s, %s, %s", user.id, subscription.source, exc.code)
            subscription.last_added, subscription.last_error = 0, exc.code
        else:
            subscription.last_added, subscription.last_error = len(result["added"]), None
            added.extend(result["added"])
        subscription.last_run_at = now
        runs += 1
        await db.commit()
    return {"runs": runs, "added": added}
