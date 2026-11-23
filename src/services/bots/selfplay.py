# --- FILE: src/services/bots/selfplay.py ---
"""
Personality tuning by self-play (task 32.3). The workshop archetypes (the ladder and tournaments are built from them) regularly
play each other — the celery beat task bot_selfplay in the simulation queue: each against a neighbour in strength. Results
accumulate
per archetype; after TUNE_GAMES games the in-game strength is computed (average opponent rating +- PERF_SPAN by score share).
If it differs from the declared one (target_elo) by DRIFT or more, the strength sliders are shifted by a step: if stronger than
declared — more spread (randomness) and a wider move window (blunder_guard_cp), if weaker — the opposite.

Style bounds: the spread — no further than RANDOMNESS_SPAN from the original, the window — no further than GUARD_SHARE from the
original; the other
sliders (aggression, centre, habits, openings) are not touched — the bot stays itself. Each shift is written to the open
log (bot_tuning_log, the transparency page). The tuned personality is received by the catalog (the client plays it in the
workshop and
on the ladder), tournaments and simulation — through tuned_config; the process cache is refreshed no more than once per
REFRESH_SECONDS.

The opponent's reference rating is its declared strength: all archetypes hold near their own, neighbours in strength measure
each other.

Data: tables bot_tunings (the game accumulator and the current randomness / blunder_guard_cp, BotTuning) and bot_tuning_log
(the shift log, BotTuningLog). Started by the bot_selfplay task via run (src/worker/tasks.py); the tuned personality is read by
src/api/bots.py (catalog, transparency page), src/api/tournaments.py and tournament_simulation.py.
"""

import asyncio
import logging
import random
import time
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bot_memory import BotTuning, BotTuningLog
from src.services.bots.archetypes import ARCHETYPES, ARCHETYPES_BY_KEY, Archetype
from src.services.bots.personality import BotPersonalityConfig

logger = logging.getLogger(__name__)

# How many games an archetype accumulates before the strength check.
TUNE_GAMES = 20
# The gap between the in-game and declared strength (rating points) from which the sliders shift.
DRIFT = 75
# Span of the score-share strength estimate: a 100 % share gives the average opponent rating + PERF_SPAN, 0 % — minus
# PERF_SPAN.
PERF_SPAN = 400
# Shift step per check: spread (randomness slider units) and move window (cp).
RANDOMNESS_STEP = 5
GUARD_STEP = 20
# Bounds the tuning does not leave: spread +- RANDOMNESS_SPAN from the original, window +- GUARD_SHARE from the original.
RANDOMNESS_SPAN = 15
GUARD_SHARE = 0.25
# How many games one run of the task plays.
GAMES_PER_RUN = 12
# How often (s) the process re-reads the tuned values from the database.
REFRESH_SECONDS = 300

# Process cache: archetype key → (randomness, blunder_guard_cp); filled by refresh, updated by record_game.
_tuned: dict[str, tuple[int, int]] = {}
_loaded_at = -float(REFRESH_SECONDS)


def bounds(base: BotPersonalityConfig) -> tuple[tuple[int, int], tuple[int, int]]:
    """Tuning bounds of an archetype: (min, max) for randomness and (min, max) for blunder_guard_cp."""
    randomness = (max(0, base.randomness - RANDOMNESS_SPAN), min(100, base.randomness + RANDOMNESS_SPAN))
    span = max(GUARD_STEP, round(base.blunder_guard_cp * GUARD_SHARE))
    guard = (max(0, base.blunder_guard_cp - span), min(400, base.blunder_guard_cp + span))
    return randomness, guard


def tuned_config(archetype: Archetype) -> BotPersonalityConfig:
    """The archetype's personality with tuned randomness and blunder_guard_cp (from the cache); without tuning — the
    original."""
    values = _tuned.get(archetype.key)
    if values is None:
        return archetype.config
    return archetype.config.model_copy(update={"randomness": values[0], "blunder_guard_cp": values[1]})


def forget() -> None:
    """Reset the process cache (tests)."""
    global _loaded_at
    _tuned.clear()
    _loaded_at = -float(REFRESH_SECONDS)


async def refresh(db: AsyncSession, *, force: bool = False) -> None:
    """Re-read the tuned values from bot_tunings into the cache; without force — no more than once per REFRESH_SECONDS."""
    global _loaded_at
    if not force and time.monotonic() - _loaded_at < REFRESH_SECONDS:
        return
    rows = (await db.execute(select(BotTuning))).scalars().all()
    _tuned.clear()
    _tuned.update({r.key: (r.randomness, r.blunder_guard_cp) for r in rows if r.key in ARCHETYPES_BY_KEY})
    _loaded_at = time.monotonic()


def performance(points: float, games: int, opponents_rating: float) -> float:
    """In-game strength: the average opponent plus or minus PERF_SPAN by score share (linear estimate, without extremes)."""
    return opponents_rating / games + 2 * PERF_SPAN * (points / games - 0.5)


def step(base: BotPersonalityConfig, randomness: int, guard: int, measured: float) -> tuple[int, int]:
    """New (randomness, guard): a step within bounds if the in-game strength differs from target_elo by DRIFT or more."""
    gap = measured - base.target_elo
    if abs(gap) < DRIFT:
        return randomness, guard
    sign = 1 if gap > 0 else -1          # stronger than declared — weaken
    (r_lo, r_hi), (g_lo, g_hi) = bounds(base)
    return (min(r_hi, max(r_lo, randomness + sign * RANDOMNESS_STEP)),
            min(g_hi, max(g_lo, guard + sign * GUARD_STEP)))


async def record_game(db: AsyncSession, key: str, opponent_rating: int, points: float) -> BotTuningLog | None:
    """A self-play game result for an archetype; if the accumulator is full — a strength check and maybe a shift. The commit
    is here."""
    base = ARCHETYPES_BY_KEY[key].config
    row = await db.get(BotTuning, key)
    if row is None:
        row = BotTuning(key=key, randomness=base.randomness, blunder_guard_cp=base.blunder_guard_cp, games=0,
                        points=0.0, opponents_rating=0.0)
        db.add(row)
    row.games = (row.games or 0) + 1
    row.points = (row.points or 0.0) + points
    row.opponents_rating = (row.opponents_rating or 0.0) + opponent_rating
    entry = None
    if row.games >= TUNE_GAMES:
        measured = performance(row.points, row.games, row.opponents_rating)
        randomness, guard = step(base, row.randomness, row.blunder_guard_cp, measured)
        if (randomness, guard) != (row.randomness, row.blunder_guard_cp):
            entry = BotTuningLog(key=key, games=row.games, measured=round(measured), target=base.target_elo,
                                 randomness_before=row.randomness, randomness_after=randomness,
                                 guard_before=row.blunder_guard_cp, guard_after=guard)
            db.add(entry)
            logger.info("Self-play tuning %s: measured %.0f vs %s, randomness %s->%s, guard %s->%s", key, measured,
                        base.target_elo, row.randomness, randomness, row.blunder_guard_cp, guard)
        row.randomness, row.blunder_guard_cp = randomness, guard
        row.games, row.points, row.opponents_rating = 0, 0.0, 0.0
    await db.commit()
    _tuned[key] = (row.randomness, row.blunder_guard_cp)
    return entry


def pairings(rng: random.Random, games: int = GAMES_PER_RUN) -> list[tuple[Archetype, Archetype]]:
    """Neighbours in strength; the colour is random. Each archetype meets one a little stronger or weaker."""
    ladder = sorted(ARCHETYPES, key=lambda a: a.config.target_elo)
    pairs = [(ladder[i], ladder[i + 1]) for i in range(len(ladder) - 1)]
    chosen = [rng.choice(pairs) for _ in range(games)] if pairs else []
    return [(a, b) if rng.random() < 0.5 else (b, a) for a, b in chosen]


async def run(db: AsyncSession, games: int = GAMES_PER_RUN, play: Callable | None = None,
              rng: random.Random | None = None) -> int:
    """Play self-play games and record the results; returns the number of games played."""
    # Import inside the function: tournament_simulation itself imports selfplay.
    from src.services import tournament_simulation as sim
    from src.services.bots.personality import PersonalityBot

    play = play or sim.play_game
    rng = rng or random.Random()
    await refresh(db, force=True)
    played = 0
    for white, black in pairings(rng, games):
        bots = []
        for archetype in (white, black):
            bot = PersonalityBot(tuned_config(archetype))
            bot.search_depth = min(bot.search_depth, sim.SIM_MAX_DEPTH)
            bot.time_limit = min(bot.time_limit, sim.SIM_TIME_LIMIT_S)
            bots.append(bot)
        _moves, result, _termination = await asyncio.to_thread(play, bots[0], bots[1])
        white_points = {"1-0": 1.0, "0-1": 0.0}.get(result, 0.5)
        await record_game(db, white.key, black.config.target_elo, white_points)
        await record_game(db, black.key, white.config.target_elo, 1.0 - white_points)
        played += 1
    return played


async def journal(db: AsyncSession, limit: int = 50) -> list[BotTuningLog]:
    """The last limit entries of the open shift log (newest first)."""
    return list((await db.execute(select(BotTuningLog).order_by(BotTuningLog.id.desc()).limit(limit))).scalars().all())
