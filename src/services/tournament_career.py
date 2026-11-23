# --- FILE: src/services/tournament_career.py ---
"""
Tournament career (task 15.4): a ladder of ready-made tournaments of growing strength and random opponents from a range.

The ladder is MAIN_STAGES main tournaments: the opponents' strength grows from START_TARGET to END_TARGET, the size is 4, 6
or 8 (by thirds of the ladder), format and time control alternate. The next main tournament opens when the previous one
is finished in the upper half of the table. After every INVITATIONAL_EVERY-th main one comes an invitational tournament (in
total MAIN_STAGES // INVITATIONAL_EVERY): it is hidden (the player sees only "???"), opens with a top-three place in its "gate"
main tournament and is stronger than it by INVITATIONAL_BONUS.

A stage's opponents are not stored: they are roster participants (historical bots and workshop archetypes) closest in
strength to the stage's target - the set is deterministic as long as the calibration does not change (bots/calibration.py).

Progress is the player's best places in finished career tournaments (the tables tournaments.career_stage and
tournament_players). Called by src/api/tournaments.py; the tournament itself is created by tournaments.create_tournament.
"""

import random
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainError
from src.models.tournament import Tournament, TournamentPlayer
from src.models.user import User
from src.services import tournaments as tournaments_service
from src.services.bots.archetypes import ARCHETYPE_PREFIX, ARCHETYPES
from src.services.bots.calibration import strength_of
from src.services.rating import classify_time_control

# Number of main tournaments on the ladder.
MAIN_STAGES = 24
# Target strength of opponents of the first and last main tournament (by calibration); linearly in between.
START_TARGET, END_TARGET = 800, 2200
# After every this-many-th main tournament comes an invitational; it is stronger than its "gate" by INVITATIONAL_BONUS.
INVITATIONAL_EVERY = 4
INVITATIONAL_BONUS = 150
# Time controls of the stages (base time, increment - ms); the stages take them in a cycle.
TIME_CONTROLS = ((300_000, 0), (600_000, 0), (180_000, 2_000), (900_000, 10_000))
# Random tournament mode: opponents around the player's level, stronger or weaker.
RandomMode = Literal["my_level", "stronger", "weaker"]
# Shift of the centre of random opponent selection relative to the player's rating by mode.
RANDOM_SHIFT: dict[str, int] = {"my_level": 0, "stronger": 200, "weaker": -200}


@dataclass(frozen=True)
class Stage:
    """
    A career stage: format, number of participants, time control and the target strength of opponents. gate - the main
    tournament, a top-three place in which opens this invitational.
    """
    key: str
    number: int
    format: tournaments_service.Format
    size: int
    base_time_ms: int
    increment_ms: int
    target: int
    # An invitational: hidden until a top-three place is taken in the gate tournament.
    gate: str | None = None


def _main_stage(i: int) -> Stage:
    """Main stage with index i (from zero): the size is by thirds of the ladder; knockout - every third, of sizes 4 and 8."""
    size = 4 if i < 8 else 6 if i < 16 else 8
    # Knockout - only sizes 4 and 8 (six does not suit a bracket): every third tournament of the ladder.
    fmt: tournaments_service.Format = "knockout" if size != 6 and i % 3 == 2 else "round_robin"
    base, inc = TIME_CONTROLS[i % len(TIME_CONTROLS)]
    target = START_TARGET + round((END_TARGET - START_TARGET) * i / (MAIN_STAGES - 1))
    return Stage(f"main-{i + 1}", i + 1, fmt, size, base, inc, target)


def _build() -> tuple[Stage, ...]:
    """Assembles the whole ladder: the main stages and an invitational after every INVITATIONAL_EVERY-th one."""
    stages: list[Stage] = []
    invitational = 0
    for i in range(MAIN_STAGES):
        stage = _main_stage(i)
        stages.append(stage)
        if (i + 1) % INVITATIONAL_EVERY == 0:
            invitational += 1
            base, inc = TIME_CONTROLS[(i + 1) % len(TIME_CONTROLS)]
            stages.append(Stage(f"invitational-{invitational}", invitational, "round_robin", 4, base, inc,
                                stage.target + INVITATIONAL_BONUS, gate=stage.key))
    return tuple(stages)


# All career stages in order; by key - STAGES_BY_KEY.
STAGES: tuple[Stage, ...] = _build()
STAGES_BY_KEY = {stage.key: stage for stage in STAGES}


def roster() -> list[tuple[tournaments_service.ParticipantSpec, int]]:
    """Possible opponents and their strength (by calibration): historical bots and archetypes."""
    entries: list[tuple[tournaments_service.ParticipantSpec, int]] = []
    for bot_id, declared in tournaments_service._bot_ratings().items():
        entries.append((tournaments_service.ParticipantSpec("bot", bot_id), strength_of(bot_id, declared).rating))
    for archetype in ARCHETYPES:
        entries.append((tournaments_service.ParticipantSpec("archetype", archetype.key.removeprefix(ARCHETYPE_PREFIX)),
                        strength_of(archetype.key, archetype.config.target_elo).rating))
    return sorted(entries, key=lambda item: (item[1], str(item[0].id)))


def nearest(target: int, count: int) -> list[tournaments_service.ParticipantSpec]:
    """count opponents closest in strength to target (on a tie - by id)."""
    ranked = sorted(roster(), key=lambda item: (abs(item[1] - target), str(item[0].id)))
    return [spec for spec, _ in ranked[:count]]


def stage_opponents(stage: Stage) -> list[tournaments_service.ParticipantSpec]:
    """Opponents of a stage: size - 1 closest in strength to the stage's target (the player is one more participant)."""
    return nearest(stage.target, stage.size - 1)


def random_opponents(rating: int, mode: RandomMode, count: int, rng: random.Random | None = None,
                     ) -> list[tournaments_service.ParticipantSpec]:
    """Random opponents around rating (+ the mode shift): chosen from the 2*count closest in strength."""
    pool = nearest(rating + RANDOM_SHIFT[mode], min(len(roster()), count * 2))
    if len(pool) < count:
        raise DomainError("tournament_participants_count", expected=count)
    return (rng or random.Random()).sample(pool, count)


async def best_places(db: AsyncSession, user: User) -> dict[str, int]:
    """The player's best place in each finished (and not resigned) career tournament."""
    rows = (await db.execute(
        select(Tournament.career_stage, TournamentPlayer.place)
        .join(TournamentPlayer, (TournamentPlayer.tournament_id == Tournament.id) & (TournamentPlayer.user_id == user.id))
        .where(Tournament.owner_id == user.id, Tournament.career_stage.is_not(None), Tournament.status == "finished",
               Tournament.withdrawn_at.is_(None), TournamentPlayer.place.is_not(None))
    )).all()
    best: dict[str, int] = {}
    for key, place in rows:
        best[key] = min(best.get(key, place), place)
    return best


def unlocked(stage: Stage, best: dict[str, int]) -> bool:
    """
    Whether a stage is open given the best places best: an invitational - a top-three place in the "gate" tournament; a
    main one - the previous one is finished in the upper half of the table; the first is always open.
    """
    if stage.gate is not None:
        return best.get(stage.gate, 99) <= 3
    if stage.number == 1:
        return True
    previous = STAGES_BY_KEY[f"main-{stage.number - 1}"]
    return best.get(previous.key, 99) <= previous.size // 2


async def overview(db: AsyncSession, user: User) -> list[dict]:
    """
    The player's career: stages with the best place taken and the "open" flag. A hidden invitational reveals neither
    opponents nor conditions.
    """
    best = await best_places(db, user)
    result = []
    for stage in STAGES:
        is_open = unlocked(stage, best)
        hidden = stage.gate is not None and not is_open
        category = classify_time_control(stage.base_time_ms, stage.increment_ms)
        result.append({
            "key": stage.key, "number": stage.number, "invitational": stage.gate is not None, "hidden": hidden,
            "unlocked": is_open, "best_place": best.get(stage.key),
            # A hidden invitational reveals neither opponents nor conditions.
            **({} if hidden else {
                "format": stage.format, "size": stage.size, "base_time_ms": stage.base_time_ms,
                "increment_ms": stage.increment_ms, "category": category, "target": stage.target,
                "opponents": [{"kind": s.kind, "id": s.id} for s in stage_opponents(stage)],
            }),
        })
    return result


async def start_stage(db: AsyncSession, user: User, key: str) -> Tournament:
    """Creates a career stage tournament; a closed stage - refusal."""
    stage = STAGES_BY_KEY.get(key)
    if stage is None:
        raise DomainError("career_stage_unknown", stage=key)
    if not unlocked(stage, await best_places(db, user)):
        raise DomainError("career_stage_locked", stage=key)
    return await tournaments_service.create_tournament(
        db, user, stage.format, stage.size, stage_opponents(stage), stage.base_time_ms, stage.increment_ms,
        career_stage=stage.key, progress_branch=branch_of(stage),
    )


def branch_of(stage: Stage) -> tuple[str, ...]:
    """
    Progress branch of a stage: the main ladder - all main stages (while one is running, the next cannot be started);
    an invitational - on its own (in parallel with the ladder, but not twice at once).
    """
    if stage.gate is not None:
        return (stage.key,)
    return tuple(s.key for s in STAGES if s.gate is None)
