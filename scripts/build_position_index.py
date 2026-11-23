# --- FILE: scripts/build_position_index.py ---
"""
Position index (task 16.1) over already played games: the archive and everything finished before the index appeared. New games
are indexed by a Celery task on completion - the script is needed once (and is safe to repeat: a game with the
games.positions_indexed flag is skipped).

    python scripts/build_position_index.py [--batch 500]
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main(batch: int) -> None:
    """Indexes the first 30 plies of archive games into the position tables."""
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from src.core.config import settings
    from src.models.game import Game, GameStatus
    from src.services.position_index import index_game

    engine = create_async_engine(settings.async_database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    pending = (Game.status == GameStatus.COMPLETED) & Game.positions_indexed.is_(False)
    started = time.monotonic()
    async with sessions() as db:
        total = await db.scalar(select(func.count()).select_from(Game).where(pending)) or 0
        done = added = 0
        last_id = 0
        while True:
            games = (await db.execute(
                select(Game).where(pending, Game.id > last_id).order_by(Game.id).limit(batch)
            )).scalars().all()
            if not games:
                break
            for game in games:
                added += await index_game(db, game)
            await db.commit()
            last_id = games[-1].id
            done += len(games)
            print(f"{done}/{total} games, {added} in the index ({time.monotonic() - started:.0f} s)", flush=True)
    await engine.dispose()


async def main_library(batch: int) -> None:
    """Puts library games without the positions_indexed mark into position_library_games."""
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from src.core.config import settings
    from src.models.library import LibraryGame
    from src.services.position_index import index_library_game

    engine = create_async_engine(settings.async_database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    pending = LibraryGame.positions_indexed.is_(False)
    started = time.monotonic()
    async with sessions() as db:
        total = await db.scalar(select(func.count()).select_from(LibraryGame).where(pending)) or 0
        done = added = last_id = 0
        while True:
            games = (await db.execute(
                select(LibraryGame).where(pending, LibraryGame.id > last_id).order_by(LibraryGame.id).limit(batch)
            )).scalars().all()
            if not games:
                break
            for game in games:
                added += await index_library_game(db, game)
            await db.commit()
            last_id = games[-1].id
            done += len(games)
            print(f"{done}/{total} library games, {added} in the index ({time.monotonic() - started:.0f} s)", flush=True)
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch", type=int, default=500)
    parser.add_argument("--library", action="store_true", help="library games instead of site and archive games")
    args = parser.parse_args()
    asyncio.run(main_library(args.batch) if args.library else main(args.batch))
