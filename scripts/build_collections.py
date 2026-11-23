# --- FILE: scripts/build_collections.py ---
"""
"Fun collections" of the archive (task 16.3): computes metrics of all archive games (src/services/collections.py) and
replaces the contents of collection_entries. A re-run recomputes the collections entirely.

    python scripts/build_collections.py [--workers 4]
"""

import argparse
import asyncio
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ARCHIVE_PASSWORD = "!historical_archive_no_login!"


def _metrics(item: tuple[int, str]):
    """Computes game metrics: number of moves, checks, captures, promotions and passed pawns."""
    from src.services.collections import game_metrics

    game_id, pgn = item
    return game_id, game_metrics(pgn)


async def _load():
    """Loads finished archive games without duplicates for the thematic collections."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.orm import aliased
    from sqlalchemy.pool import NullPool

    from src.core.config import settings
    from src.models.game import Game, GameStatus
    from src.models.user import User

    engine = create_async_engine(settings.async_database_url, poolclass=NullPool)
    white, black = aliased(User), aliased(User)
    async with async_sessionmaker(engine)() as db:
        rows = (await db.execute(
            select(Game.id, Game.pgn).join(white, white.id == Game.white_player_id)
            .join(black, black.id == Game.black_player_id)
            .where(white.hashed_password == ARCHIVE_PASSWORD, black.hashed_password == ARCHIVE_PASSWORD,
                   Game.status == GameStatus.COMPLETED, Game.pgn.is_not(None))
        )).all()
    await engine.dispose()
    return [(gid, pgn) for gid, pgn in rows]


async def _save(ranked: dict[str, list[tuple[int, int]]]) -> int:
    """Saves the formed thematic game collections into a JSON file."""
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from src.core.config import settings
    from src.models.collection import CollectionEntry

    engine = create_async_engine(settings.async_database_url, poolclass=NullPool)
    count = 0
    async with async_sessionmaker(engine)() as db:
        await db.execute(delete(CollectionEntry))
        for collection, entries in ranked.items():
            for rank, (game_id, value) in enumerate(entries, 1):
                db.add(CollectionEntry(collection=collection, rank=rank, game_id=game_id, value=value))
                count += 1
        await db.commit()
    await engine.dispose()
    return count


def main() -> None:
    """Builds seven fun game collections from the historical archive."""
    from src.services.collections import rank_collections

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    started = time.monotonic()
    games = asyncio.run(_load())
    print(f"Games in the archive: {len(games)}", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        metrics = {gid: m for gid, m in pool.map(_metrics, games, chunksize=200) if m is not None}
    ranked = rank_collections(metrics)
    saved = asyncio.run(_save(ranked))
    print(f"Collections: {len(ranked)}, entries: {saved} in {time.monotonic() - started:.0f} s", flush=True)


if __name__ == "__main__":
    main()
