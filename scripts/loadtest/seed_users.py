"""
Players for the load test (scripts/loadtest/ws_load.py).

Run inside the API container - it needs its DB and SECRET_KEY:

    docker compose -f docker-compose.prod.yml exec -T api \
        python -m scripts.loadtest.seed_users --count 400 > tokens.json

Creates (or reuses) players loadtest_0001..N and prints to stdout a JSON list
{id, username, token}. One cannot log in as them with a password - only with the issued token - and registration
through the API will not do: it is limited to a few accounts per hour from one IP.

    python -m scripts.loadtest.seed_users --cleanup

removes these players together with their games and moves.
"""

import argparse
import asyncio
import json
import sys

from sqlalchemy import delete, or_, select

from src.core.security import create_user_token
from src.db.session import AsyncSessionLocal
from src.models.game import Game
from src.models.move import Move
from src.models.user import User

PREFIX = "loadtest_"
NO_LOGIN_MARKER = "!loadtest_no_login!"


async def seed(count: int) -> list[dict]:
    """Creates test players in the DB and issues JWT tokens for them for the load."""
    names = [f"{PREFIX}{i:04d}" for i in range(1, count + 1)]
    async with AsyncSessionLocal() as db:
        existing = {
            user.username: user
            for user in (await db.execute(select(User).where(User.username.in_(names)))).scalars()
        }
        for name in names:
            if name not in existing:
                user = User(username=name, username_key=name, hashed_password=NO_LOGIN_MARKER)
                db.add(user)
                existing[name] = user
        await db.commit()
        users = [existing[name] for name in names]
        return [{"id": u.id, "username": u.username, "token": create_user_token(u)} for u in users]


async def cleanup() -> tuple[int, int]:
    """Deletes the load-test players together with their games and moves."""
    async with AsyncSessionLocal() as db:
        user_ids = list((await db.execute(
            select(User.id).where(User.hashed_password == NO_LOGIN_MARKER)
        )).scalars())
        if not user_ids:
            return 0, 0
        game_ids = list((await db.execute(select(Game.id).where(or_(
            Game.white_player_id.in_(user_ids), Game.black_player_id.in_(user_ids),
        )))).scalars())
        if game_ids:
            await db.execute(delete(Move).where(Move.game_id.in_(game_ids)))
            await db.execute(delete(Game).where(Game.id.in_(game_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
        return len(user_ids), len(game_ids)


def main() -> None:
    """CLI entry point for creating and deleting test players."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=200, help="number of players (even: games are played in pairs)")
    parser.add_argument("--cleanup", action="store_true", help="delete the load-test players and their games")
    args = parser.parse_args()

    if args.cleanup:
        users, games = asyncio.run(cleanup())
        print(f"removed {users} load-test players and {games} games", file=sys.stderr)
        return
    json.dump(asyncio.run(seed(args.count)), sys.stdout)


if __name__ == "__main__":
    main()
