# --- FILE: tests/integration/test_tournament_races.py ---
"""
Arena and Swiss races on a real PostgreSQL (on SQLite SELECT ... FOR UPDATE is silently ignored, so these
checks live here). Each competing "handler" has its own session and connection, like separate server requests:
- one arena game finishes twice at the same time — points are awarded once;
- the last Swiss round ends on all boards at once — the next round opens exactly once;
- several players open the Swiss page at once — again exactly one new round;
- a tournament with bots (tournaments.record_result): one game recorded twice at once — the second is rejected;
  the last games of a round (a player game and a bot game from the worker) recorded at once — the next round is open.
Starting the round's games is patched out (no Redis or sockets): the advancement rule is tested, not game start.
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from src.core.errors import DomainError
from src.models.arena import Arena, ArenaGame, ArenaPlayer
from src.models.game import Game, GameStatus
from src.models.tournament import Tournament, TournamentGame
from src.models.user import User
from src.services import arena as arena_service
from src.services import tournaments

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set (real PostgreSQL required)"),
]


async def _setup(pg, players: int, fmt: str, rounds: int = 0) -> tuple[int, list[int]]:
    """An arena (started an hour ago) and its participants; returns (arena id, player ids)."""
    now = datetime.now(UTC)
    async with pg() as db:
        users = [User(username=f"race_{i}", hashed_password="pw") for i in range(players)]
        arena = Arena(base_time_ms=180_000, increment_ms=2_000, starts_at=now - timedelta(hours=1),
                      ends_at=now + timedelta(hours=2), format=fmt, rounds=rounds)
        db.add_all([*users, arena])
        await db.flush()
        db.add_all([ArenaPlayer(arena_id=arena.id, user_id=u.id, rating=1500 + i) for i, u in enumerate(users)])
        await db.commit()
        return arena.id, [u.id for u in users]


async def _add_game(pg, arena_id: int, white: int, black: int, round_no: int = 0) -> int:
    """An arena game without a result; returns the game id in games."""
    async with pg() as db:
        game = Game(white_player_id=white, black_player_id=black, status=GameStatus.IN_PROGRESS, is_rated=True)
        db.add(game)
        await db.flush()
        db.add(ArenaGame(arena_id=arena_id, game_id=game.id, white_id=white, black_id=black, round=round_no))
        await db.commit()
        return game.id


@pytest.fixture
def fake_round_start(monkeypatch):
    """A game of the new round — just a record without a result (instead of starting a PvP game via Redis and sockets)."""

    async def start(db, arena, white, black):
        game = Game(white_player_id=white, black_player_id=black, status=GameStatus.IN_PROGRESS, is_rated=True)
        db.add(game)
        await db.flush()
        db.add(ArenaGame(arena_id=arena.id, game_id=game.id, white_id=white, black_id=black, round=arena.current_round))
        await db.flush()

    monkeypatch.setattr(arena_service, "_start_swiss_game", start)


async def test_double_finish_of_one_arena_game_scores_once(pg):
    arena_id, (white, black) = await _setup(pg, 2, "arena")
    game_id = await _add_game(pg, arena_id, white, black)

    async def finish() -> bool:
        async with pg() as db:
            counted = await arena_service.on_game_finished(db, game_id, "1-0")
            await db.commit()
            return counted

    results = await asyncio.gather(*(finish() for _ in range(4)))

    assert sorted(results) == [False, False, False, True]
    async with pg() as db:
        winner = (await db.execute(select(ArenaPlayer).where(ArenaPlayer.user_id == white))).scalar_one()
        loser = (await db.execute(select(ArenaPlayer).where(ArenaPlayer.user_id == black))).scalar_one()
    assert (winner.score, winner.games, winner.wins, winner.streak) == (2, 1, 1, 1)
    assert (loser.score, loser.games) == (0, 1)


async def test_round_finishing_on_every_board_opens_the_next_round_once(pg, fake_round_start):
    arena_id, users = await _setup(pg, 8, "swiss", rounds=3)
    async with pg() as db:
        arena = await db.get(Arena, arena_id)
        arena.current_round = 1
        await db.commit()
    pairs = [(users[i], users[i + 4]) for i in range(4)]
    game_ids = [await _add_game(pg, arena_id, w, b, round_no=1) for w, b in pairs]

    async def finish_and_advance(game_id: int) -> None:
        # Like game_state.finish_game: game result and points — commit, then round advancement.
        async with pg() as db:
            await arena_service.on_game_finished(db, game_id, "1-0")
            await db.commit()
            await arena_service.advance_after_game(db, game_id)

    await asyncio.gather(*(finish_and_advance(gid) for gid in game_ids))

    async with pg() as db:
        arena = await db.get(Arena, arena_id)
        second_round = await db.scalar(select(func.count()).select_from(ArenaGame).where(
            ArenaGame.arena_id == arena_id, ArenaGame.round == 2))
    assert arena.current_round == 2
    assert second_round == 4


async def _round_robin(pg) -> tuple[int, list[int]]:
    """A round-robin tournament of a player with three bots; returns (tournament id, ids of the first round games)."""
    async with pg() as db:
        owner = User(username="race_owner", hashed_password="pw")
        db.add(owner)
        await db.commit()
        specs = [tournaments.ParticipantSpec("bot", key) for key in ("morphy", "philidor", "staunton")]
        tournament = await tournaments.create_tournament(db, owner, "round_robin", 4, specs, 300_000, 0)
        first = [g.id for g in await tournaments.games_of(db, tournament.id) if g.round == 1]
        return tournament.id, first


async def _record(pg, tournament_id: int, tgame_id: int) -> str:
    """Records a tournament game result in its own session; returns "ok" or a rejection code."""
    async with pg() as db:
        tournament = await db.get(Tournament, tournament_id)
        tgame = await db.get(TournamentGame, tgame_id)
        try:
            await tournaments.record_result(db, tournament, tgame, "1-0")
        except DomainError as exc:
            return exc.code
        return "ok"


async def test_tournament_game_recorded_twice_at_once_counts_once(pg):
    tournament_id, (first, _) = await _round_robin(pg)
    outcomes = await asyncio.gather(*(_record(pg, tournament_id, first) for _ in range(3)))
    assert sorted(outcomes) == ["ok", "tournament_game_closed", "tournament_game_closed"]


async def test_last_games_of_a_tournament_round_finishing_together_open_the_next_round(pg):
    # Without locking each transaction sees the other round game as unplayed — and the round never opens.
    tournament_id, round_one = await _round_robin(pg)
    assert await asyncio.gather(*(_record(pg, tournament_id, gid) for gid in round_one)) == ["ok", "ok"]
    async with pg() as db:
        assert (await db.get(Tournament, tournament_id)).current_round == 2


async def test_simultaneous_page_views_open_one_round(pg, fake_round_start):
    arena_id, _ = await _setup(pg, 6, "swiss", rounds=5)

    async def view() -> None:
        # Like GET /arenas/{id}: the page advances the Swiss.
        async with pg() as db:
            arena = await db.get(Arena, arena_id)
            await arena_service.advance_swiss(db, arena)
            await db.commit()

    await asyncio.gather(*(view() for _ in range(6)))

    async with pg() as db:
        arena = await db.get(Arena, arena_id)
        games = await db.scalar(select(func.count()).select_from(ArenaGame).where(ArenaGame.arena_id == arena_id))
    assert arena.current_round == 1
    assert games == 3
