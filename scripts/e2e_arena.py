# --- FILE: scripts/e2e_arena.py ---
"""
An arena for the end-to-end browser test (frontend/e2e/social-arena.e2e.ts): a one-off 3+2 blitz arena that is already running
(it started a minute ago and ends in ARENA_MINUTES minutes). The conference schedule does not touch such an arena: it has no
schedule_key. Prints the arena number - CI puts it into the E2E_ARENA_ID variable.

    python scripts/e2e_arena.py

Only for a throwaway CI stand: do not run on a working server (an extra arena would appear in the list).
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Arena duration: with a margin for the whole E2E run.
ARENA_MINUTES = 60
# Arena control (3+2 blitz, as for the scheduled arenas).
BASE_MS, INCREMENT_MS = 180_000, 2_000


async def main() -> None:
    """Creates a running arena and prints its number."""
    from src.db.session import AsyncSessionLocal
    from src.models.arena import Arena

    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        arena = Arena(base_time_ms=BASE_MS, increment_ms=INCREMENT_MS, starts_at=now - timedelta(minutes=1),
                      ends_at=now + timedelta(minutes=ARENA_MINUTES), format="arena")
        db.add(arena)
        await db.commit()
        print(arena.id)


if __name__ == "__main__":
    asyncio.run(main())
