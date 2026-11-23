"""
Import of PGN into the game library (task 27.2). The folder is read recursively: the folder tree -> a tree of collections under
`--collection`, a file's games go into its folder's collection. Only headers and the main line are taken; identical games
are merged, a re-run creates no duplicates.

    python scripts/import_library.py <folder> --collection "Pawn structures" [--visibility public|owner|staff]
                                     [--owner <name>] [--source <code>] [--dry-run]

What and how to import from the owner's folder - ToDo, task 27.2. The data is not put into the repository.
"""

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services import library  # noqa: E402


def pgn_files(root: Path) -> list[tuple[str, Path]]:
    """(folder relative path with "/", file) - alphabetically, folders in traversal order."""
    found = []
    for directory, subdirs, files in os.walk(root):
        subdirs.sort()
        rel = Path(directory).relative_to(root).as_posix()
        for name in sorted(files):
            if name.lower().endswith(".pgn"):
                found.append(("" if rel == "." else rel, Path(directory) / name))
    return found


def dry_run(root: Path) -> None:
    """Checks reading and validation of the folder's PGN files without writing to the DB."""
    total = library.ImportStats()
    for _, path in pgn_files(root):
        stats = library.ImportStats()
        with library.open_pgn(str(path)) as handle:
            for game in library.read_games(handle):
                stats.games += 1
                if library.parse_game(game) is None:
                    stats.skipped += 1
        total += stats
    print(f"files: {len(pgn_files(root))}, games: {total.games}, skipped: {total.skipped}")


async def run(root: Path, collection: str, visibility: str, owner: str | None, source: str) -> None:
    """Imports the folder's PGN files into library collections with deduplication."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from src.core.config import settings
    from src.models.user import User

    engine = create_async_engine(settings.async_database_url, poolclass=NullPool)
    total = library.ImportStats()
    started = time.monotonic()
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        owner_id = None
        if owner:
            owner_id = await db.scalar(select(User.id).where(User.username == owner))
            if owner_id is None:
                raise SystemExit(f"user not found: {owner}")
        for rel, path in pgn_files(root):
            target = await library.ensure_collection(db, f"{collection}/{rel}" if rel else collection,
                                                     visibility=visibility, owner_id=owner_id, source=source)
            with library.open_pgn(str(path)) as handle:
                stats = await library.import_games(db, target, library.read_games(handle))
            await db.commit()
            total += stats
            print(f"{rel or '.'}/{path.name}: +{stats.added} new, {stats.duplicates} dup, {stats.skipped} skipped")
    await engine.dispose()
    print(f"done in {time.monotonic() - started:.0f} s: games {total.games}, added {total.added}, "
          f"duplicates {total.duplicates}, linked {total.linked}, skipped {total.skipped}")


def main() -> None:
    """CLI entry point for importing games into the library."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--collection", required=True, help="path of the root collection, for example \"Games/Capablanca\"")
    parser.add_argument("--visibility", choices=library_visibilities(), default="public")
    parser.add_argument("--owner", help="collection owner (required for --visibility owner)")
    parser.add_argument("--source", default="owner", help="source code, for example owner, structures")
    parser.add_argument("--dry-run", action="store_true", help="only parse the files and count the games")
    args = parser.parse_args()
    if not args.folder.is_dir():
        raise SystemExit(f"not a folder: {args.folder}")
    if args.visibility == "owner" and not args.owner:
        raise SystemExit("--visibility owner needs --owner")
    if args.dry_run:
        dry_run(args.folder)
    else:
        asyncio.run(run(args.folder, args.collection, args.visibility, args.owner, args.source))


def library_visibilities() -> tuple[str, ...]:
    """Returns the tuple of allowed visibility levels of library collections."""
    from src.models.library import VISIBILITIES

    return VISIBILITIES


if __name__ == "__main__":
    main()
