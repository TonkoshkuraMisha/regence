# --- FILE: scripts/import_puzzles.py ---
"""
Loading the puzzle database (task 13.1) from data/puzzles/lichess_subset.csv.gz (with the lichess_themes_extra supplement and
our own endgame technique endgame_generated) and the defence drills (task 13.6) from data/puzzles/defense_drills.csv.gz
into the server database. Run after
migrations at deployment (idempotent: puzzles already loaded are skipped).

    python -m scripts.import_puzzles [--limit N]
"""

import argparse
import asyncio
import itertools
import time

from src.db.session import AsyncSessionLocal
from src.services.defense_drills import import_drills, read_drills
from src.services.puzzle_import import ENDGAME, EXTRA, GENERATED_SOURCE, import_rows, read_subset, retag_outdated


async def main() -> None:
    """Loads the puzzle selection and defence drills into the DB at deployment."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="load at most N puzzles (for a check)")
    args = parser.parse_args()
    rows = read_subset()
    if EXTRA.exists():  # a supplement for themes without database tags (scripts/dev/build_theme_extra.py, task 27.8)
        rows = itertools.chain(rows, read_subset(EXTRA))
    if args.limit:
        rows = itertools.islice(rows, args.limit)
    started = time.monotonic()
    async with AsyncSessionLocal() as db:
        added, skipped = await import_rows(db, rows)
        if ENDGAME.exists() and not args.limit:  # our own endgame technique (scripts/dev/build_endgame_puzzles.py)
            own_added, own_skipped = await import_rows(db, read_subset(ENDGAME), GENERATED_SOURCE)
            added, skipped = added + own_added, skipped + own_skipped
        retagged = await retag_outdated(db)
        drills = await import_drills(db, read_drills())
    print(f"Puzzles: added {added}, skipped {skipped}, retagged {retagged} in {time.monotonic() - started:.1f}s")
    print("Defense drills: " + ", ".join(f"{name} {count}" for name, count in drills.items()))


if __name__ == "__main__":
    asyncio.run(main())
