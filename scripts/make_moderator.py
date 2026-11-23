# --- FILE: scripts/make_moderator.py ---
"""
Moderator role (task 17.4): grant or revoke.

    python scripts/make_moderator.py <player name> [--revoke]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main(username: str, revoke: bool) -> None:
    """Grants or revokes the moderator role for the given user."""
    from sqlalchemy import func, select

    from src.db.session import AsyncSessionLocal
    from src.models.user import User

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(func.lower(User.username) == username.lower()))).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"Player {username} not found")
        user.is_moderator = not revoke
        await db.commit()
        print(f"{user.username}: moderator = {user.is_moderator}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("username")
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.username, args.revoke))
