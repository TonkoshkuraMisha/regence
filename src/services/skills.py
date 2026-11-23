"""
Skills map (task 22.1): a player's strengths and weaknesses from data already collected - without new tables.

* Tactics: puzzle solve rate by sections A-L of the theme catalogue (attempts x puzzle themes) and the weakest themes.
* Mistakes in own games (13.5): which themes were missed most often.
* Vision, memory and counting trainers (19): attempts and best result.
* Openings (20): repertoire cards - learned / in progress / new.
* Endgame (14.4) and mating patterns (14.6): completed exercises.

For the player only: training data is personal.

Where the data comes from: puzzle_attempts and puzzle_themes (tactics; all attempts are counted, including runs and the
mate course), personal_puzzles (mistakes in games), trainer_results (trainers), repertoires and repertoire_cards (openings),
lesson_progress (endgame and mates: completed records with the identifier "endgame-..." and "mates-..."), exam_results
(diagnostics, src/services/exam.py). Route - src/api/skills.py; weak themes are also used by the warm-up
(src/services/workout.py). The module itself writes nothing.
"""

from collections import Counter

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.lesson import LessonProgress
from src.models.puzzle import PersonalPuzzle, PuzzleAttempt, PuzzleTheme
from src.models.repertoire import Repertoire, RepertoireCard
from src.models.trainer import TrainerResult
from src.models.user import User
from src.services import exam
from src.services.personal_puzzles import split_themes
from src.services.themes import SECTIONS, THEMES

MIN_ATTEMPTS = 5  # fewer - there is no estimate for the section or theme ("not enough data")
WEAK_THEMES = 5  # how many weak themes and how many frequent themes of own mistakes are shown
# "Total" for the endgame progress bar. The number is written by hand and is not checked against the data: in
# frontend/src/content/endgames.json as of 17.11.2026 there are 34 exercises (see also ``lessons_done``).
ENDGAME_EXERCISES = 25
MATE_CONSTRUCTIONS = 20  # "total" constructions of the mate course; the same number as len(mate_course.COURSE)
SECTION_OF = {theme.code: theme.section for theme in THEMES}  # theme code -> catalogue section (A-L)


def _percent(solved: int, total: int) -> int | None:
    """Share solved in percent; None - fewer attempts than MIN_ATTEMPTS, the estimate would be random."""
    return round(100 * solved / total) if total >= MIN_ATTEMPTS else None


async def tactics(db: AsyncSession, user_id: int) -> tuple[list[dict], list[dict]]:
    """
    Solve rate by section and the weakest themes (at least MIN_ATTEMPTS attempts). An attempt at a puzzle with several
    themes counts for each of them. Weak ones - the WEAK_THEMES themes with the lowest solved share; with an equal share
    the theme with more attempts comes first.
    """
    rows = (await db.execute(
        select(PuzzleTheme.theme, func.count(), func.sum(case((PuzzleAttempt.solved, 1), else_=0)))
        .join(PuzzleAttempt, PuzzleAttempt.puzzle_id == PuzzleTheme.puzzle_id)
        .where(PuzzleAttempt.user_id == user_id)
        .group_by(PuzzleTheme.theme)
    )).all()
    by_section: dict[str, list[int]] = {section: [0, 0] for section in SECTIONS}
    themes = []
    for theme, total, solved in rows:
        section = SECTION_OF.get(theme)
        if section is None:
            continue
        by_section[section][0] += int(solved or 0)
        by_section[section][1] += int(total)
        score = _percent(int(solved or 0), int(total))
        if score is not None:
            themes.append({"theme": theme, "section": section, "attempts": int(total), "score": score})
    sections = [{"section": section, "attempts": total, "score": _percent(solved, total)}
                for section, (solved, total) in by_section.items()]
    weakest = sorted(themes, key=lambda t: (t["score"], -t["attempts"]))[:WEAK_THEMES]
    return sections, weakest


async def mistakes(db: AsyncSession, user_id: int) -> dict:
    """
    Mistakes in own games: how many personal puzzles in total, how many corrected and which themes occur more often than
    others. A puzzle may have several themes - each counts; codes outside the theme registry are skipped.
    """
    rows = (await db.execute(
        select(PersonalPuzzle.themes, PersonalPuzzle.done).where(PersonalPuzzle.user_id == user_id)
    )).all()
    counter: Counter[str] = Counter()
    for themes, _ in rows:
        counter.update(code for code in split_themes(themes) if code in SECTION_OF)
    return {"total": len(rows), "fixed": sum(1 for _, done in rows if done),
            "themes": [{"theme": theme, "count": count} for theme, count in counter.most_common(WEAK_THEMES)]}


async def trainers(db: AsyncSession, user_id: int) -> list[dict]:
    """Vision, memory and counting trainers (trainer_results): number of attempts, best score and the highest level of each."""
    rows = (await db.execute(
        select(TrainerResult.trainer, func.count(), func.max(TrainerResult.score), func.max(TrainerResult.level))
        .where(TrainerResult.user_id == user_id).group_by(TrainerResult.trainer).order_by(TrainerResult.trainer)
    )).all()
    return [{"trainer": trainer, "attempts": attempts, "best": best, "max_level": level}
            for trainer, attempts, best, level in rows]


async def openings(db: AsyncSession, user_id: int) -> dict:
    """
    Repertoire repetition cards (20.2): learned - interval from 6 days. The rule is the same as
    repertoire_drill.status; the number 6 is repeated here (repertoire_drill.LEARNED_DAYS).
    """
    rows = (await db.execute(
        select(RepertoireCard.first_reviewed_at.is_(None), RepertoireCard.interval_days >= 6, func.count())
        .join(Repertoire, Repertoire.id == RepertoireCard.repertoire_id)
        .where(Repertoire.user_id == user_id)
        .group_by(RepertoireCard.first_reviewed_at.is_(None), RepertoireCard.interval_days >= 6)
    )).all()
    counts = {"new": 0, "learning": 0, "learned": 0}
    for is_new, learned, count in rows:
        counts["new" if is_new else "learned" if learned else "learning"] += int(count)
    repertoires = await db.scalar(select(func.count()).select_from(Repertoire).where(Repertoire.user_id == user_id))
    return {"repertoires": repertoires or 0, **counts}


async def lessons_done(db: AsyncSession, user_id: int, prefix: str) -> int:
    """
    How many of the player's lesson_progress records with an identifier starting with prefix are completed. The final check
    of the mate course ("mates-exam") is not counted. All identifiers with such a start are counted: "endgame-" covers both
    exercises of the endgame trainer and school lessons with an identifier "endgame-...".
    """
    return await db.scalar(select(func.count()).select_from(LessonProgress).where(
        LessonProgress.user_id == user_id, LessonProgress.lesson_id.like(f"{prefix}%"),
        LessonProgress.completed_at.is_not(None), LessonProgress.lesson_id != "mates-exam",
    )) or 0


async def skill_map(db: AsyncSession, user: User) -> dict:
    """
    The player's skills map: tactics by catalogue section, weak themes, own mistakes, trainers, openings, endgame and
    mating patterns.
    """
    sections, weakest = await tactics(db, user.id)
    return {
        "username": user.username,
        "puzzle_rating": user.puzzle_rating,
        "sections": sections,
        "weakest_themes": weakest,
        "mistakes": await mistakes(db, user.id),
        "trainers": await trainers(db, user.id),
        "openings": await openings(db, user.id),
        "endgames": {"done": await lessons_done(db, user.id, "endgame-"), "total": ENDGAME_EXERCISES},
        "mates": {"done": await lessons_done(db, user.id, "mates-"), "total": MATE_CONSTRUCTIONS},
        # Diagnostic exam (22.0) - starting data while there are few puzzle attempts.
        "exam": await exam.latest(db, user.id),
    }
