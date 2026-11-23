# --- FILE: src/services/course_progress.py ---
"""
Auto-credit of Big Course steps and programmes (task 6 of the owner's plan of 18.11, tasks 27.6 and 22.3): a summary of what
the player has already done, by the norms below. Course steps are client data (frontend/src/content/supercourse.ts), so the
server returns what is done by exercise kind and the client matches it to the steps (services/courseProgress.ts).

Where it comes from and by what norm:
* lessons, the primer, the mate course, the endgame trainer, mini-games -- the lesson_progress table: a record with
  completed_at
  (the lesson finished, an endgame exercise or mini-game won); record ids are returned as they are, the keys
  are built by the client the same way as when writing;
* puzzle themes -- theme_progress: a theme counts when at least THEME_PASS_STAGE stages are passed (moving to a
  stage takes puzzles.STAGE_PASS clean solves out of a STAGE_WINDOW in a row) or the theme is fully mastered;
* trainers -- trainer_results: counted if at least TRAINER_MIN_ATTEMPTS attempts were made (trainers have no
  score thresholds: each has its own levels);
* exams -- exam_results: the latest grade per section; the rule "level exam passed" (grade not below the level's
  goal) lives on the client next to the level goals (supercourse.levelExamPassed).
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.lesson import LessonProgress
from src.models.puzzle import ThemeProgress
from src.models.trainer import TrainerResult
from src.services import exam

# A theme counts after moving from the first stage to the second (8 clean out of 10 at the "introduction" stage).
THEME_PASS_STAGE = 2
# A trainer counts after the first finished attempt.
TRAINER_MIN_ATTEMPTS = 1


def theme_passed(stage: int, mastered: bool) -> bool:
    """Theme norm: stage THEME_PASS_STAGE reached or the theme is mastered."""
    return mastered or stage >= THEME_PASS_STAGE


async def summary(db: AsyncSession, user_id: int) -> dict:
    """
    {lessons: [ids of completed lesson_progress records], themes: [counted themes], trainers: [counted
    trainers], exams: {section: latest grade}} -- everything sorted so that the response is stable.
    """
    lessons = (await db.execute(select(LessonProgress.lesson_id).where(
        LessonProgress.user_id == user_id, LessonProgress.completed_at.is_not(None)))).scalars().all()
    themes = (await db.execute(select(ThemeProgress.theme, ThemeProgress.stage, ThemeProgress.mastered).where(
        ThemeProgress.user_id == user_id))).all()
    trainers = (await db.execute(
        select(TrainerResult.trainer).where(TrainerResult.user_id == user_id)
        .group_by(TrainerResult.trainer).having(func.count() >= TRAINER_MIN_ATTEMPTS))).scalars().all()
    exams = (await exam.latest(db, user_id))["sections"]
    return {
        "lessons": sorted(lessons),
        "themes": sorted(code for code, stage, mastered in themes if theme_passed(stage, mastered)),
        "trainers": sorted(trainers),
        "exams": {section: result["estimate"] for section, result in sorted(exams.items())},
    }
