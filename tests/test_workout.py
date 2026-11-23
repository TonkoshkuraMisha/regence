"""Daily workout (task 22.2): steps based on today's actual training, trainer choice, streak of consecutive days."""

from datetime import UTC, datetime, timedelta

import pytest

from src.models.game import Game, GameStatus
from src.models.puzzle import PersonalPuzzle, Puzzle, PuzzleAttempt, PuzzleTheme
from src.models.repertoire import Repertoire, RepertoireCard
from src.models.trainer import TrainerResult
from src.services import workout

NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)


@pytest.fixture
async def puzzle(db_session):
    item = Puzzle(source="lichess", source_id="w1", fen="8/8/8/8/8/8/8/K6k w - - 0 1", moves="a1a2", rating=1500)
    db_session.add(item)
    await db_session.flush()
    db_session.add(PuzzleTheme(puzzle_id=item.id, theme="skewer"))
    await db_session.commit()
    return item


def attempts(db_session, user_id: int, puzzle_id: int, when: datetime, count: int, solved: bool = True):
    for _ in range(count):
        db_session.add(PuzzleAttempt(user_id=user_id, puzzle_id=puzzle_id, solved=solved, rating_before=1500,
                                     rating_after=1500, created_at=when))


async def test_fresh_player_gets_defaults(db_session, test_user_1):
    plan = await workout.plan(db_session, test_user_1, NOW)
    puzzles, trainer, repertoire, mistake = plan["steps"]
    assert puzzles == {"kind": "puzzles", "themes": list(workout.DEFAULT_THEMES), "target": 5, "done": 0}
    assert trainer == {"kind": "trainer", "trainer": "coord_find", "done": False}
    assert repertoire["done"] and repertoire["due"] == 0 and mistake["done"]
    assert (plan["complete"], plan["streak"], plan["date"]) == (False, 0, "2026-11-16")


async def test_steps_streak_and_weak_themes(db_session, test_user_1, test_user_2, puzzle):
    uid = test_user_1.id
    for days_ago in (0, 1, 2, 4):  # 3 days ago is a gap: streak 3 (today, yesterday, the day before)
        when = NOW - timedelta(days=days_ago, hours=1)
        attempts(db_session, uid, puzzle.id, when, 5, solved=days_ago != 0)
        db_session.add(TrainerResult(user_id=uid, trainer="coord_find", level=1, score=5, time_ms=1, created_at=when))
    attempts(db_session, test_user_2.id, puzzle.id, NOW, 5)  # other players' attempts are not counted
    rep = Repertoire(user_id=uid, name="", color="white")
    db_session.add(rep)
    game = Game(white_player_id=uid, black_player_id=test_user_2.id, status=GameStatus.COMPLETED, result="0-1")
    db_session.add(game)
    await db_session.flush()
    db_session.add(RepertoireCard(repertoire_id=rep.id, position="p", ease=2.5, interval_days=1, repetitions=1, lapses=0,
                                  due_at=NOW - timedelta(hours=2), first_reviewed_at=NOW - timedelta(days=1)))
    db_session.add(PersonalPuzzle(user_id=uid, game_id=game.id, ply=5, fen="x", solution="a1a2", played="a1b1",
                                  cp_loss=300, themes="fork", due_at=NOW - timedelta(hours=1)))
    await db_session.commit()

    plan = await workout.plan(db_session, test_user_1, NOW)
    puzzles, trainer, repertoire, mistake = plan["steps"]
    assert puzzles["done"] == 5 and puzzles["themes"] == ["skewer"]  # 15 of 20 - a weak theme
    assert trainer == {"kind": "trainer", "trainer": "coord_name", "done": True}  # coord_find was done more often already
    assert (repertoire["due"], repertoire["repertoire_id"], repertoire["done"]) == (1, rep.id, False)
    assert (mistake["due"], mistake["done"]) == (1, False)
    assert plan["complete"] and plan["streak"] == 3


async def test_api_requires_login(client, token_user_1):
    assert client.get("/api/v1/workout").status_code == 401
    body = client.get("/api/v1/workout", headers={"Authorization": f"Bearer {token_user_1}"}).json()
    assert [s["kind"] for s in body["steps"]] == ["puzzles", "trainer", "repertoire", "mistake"]


async def test_reminders_for_running_streaks_once_a_day(db_session, test_user_1, test_user_2, puzzle, monkeypatch):
    """Reminder (Celery beat): streak is going, no workout today - one notification a day; none for those who did it."""
    from sqlalchemy import select

    from src.models.social import Notification
    from src.services import notifications

    delivered = []

    async def fake_deliver(user_id, notification):
        delivered.append((user_id, notification["kind"], notification["payload"]))

    monkeypatch.setattr(notifications, "deliver", fake_deliver)
    yesterday = NOW - timedelta(days=1, hours=1)
    for uid in (test_user_1.id, test_user_2.id):
        attempts(db_session, uid, puzzle.id, yesterday, 5)
        db_session.add(TrainerResult(user_id=uid, trainer="coord_find", level=1, score=5, time_ms=1, created_at=yesterday))
    attempts(db_session, test_user_2.id, puzzle.id, NOW - timedelta(hours=1), 5)  # the second one already worked out today
    db_session.add(TrainerResult(user_id=test_user_2.id, trainer="tail", level=1, score=5, time_ms=1,
                                 created_at=NOW - timedelta(hours=1)))
    await db_session.commit()

    assert await workout.send_reminders(db_session, NOW) == 1
    assert delivered == [(test_user_1.id, "workout_reminder", {"streak": 1})]
    assert await workout.send_reminders(db_session, NOW + timedelta(hours=2)) == 0  # already reminded today
    kinds = (await db_session.execute(select(Notification.kind).where(Notification.user_id == test_user_1.id))).scalars().all()
    assert kinds == ["workout_reminder"]


def test_beat_schedule_has_the_reminder():
    import src.worker.tasks  # noqa: F401 — registers the tasks
    from src.worker.celery_app import celery_app

    assert celery_app.conf.beat_schedule["workout-reminders"]["task"] == "workout_reminders"
    assert "workout_reminders" in celery_app.tasks
