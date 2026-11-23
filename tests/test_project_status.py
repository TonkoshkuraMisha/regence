# --- FILE: tests/test_project_status.py ---
"""Project status summary (project_status.py): ToDo.md tasks and the work order are parsed correctly."""

from pathlib import Path

from project_status import build_status, next_tasks, parse_plan

PLAN = """
**Новий порядок (13.11.2026, стратегія запуску — Частина III):** спочатку блокери.

1. **10.5** — чесна сила ботів.
1a. **A.1–A.3** — знайдене самоперевіркою.
2. **Спринт 23** — готовність до запуску, разом із **17.5**.

## СПРИНТ 10. Майстерня
### - [x] Таск 10.4. Драбина (`feat/bot-ladder`)
### - [ ] Таск 10.5. Сила ботів (`fix/bot-strength`)
## Знайдено при самоперевірці
### - [ ] Таск A.1. Лавина задач (`fix/a`)
### - [x] Таск A.2. Переграш (`fix/b`)
### - [ ] Таск A.3. Вихід (`feat/c`)
## СПРИНТ 17. Клуб
### - [ ] Таск 17.5. Обліковий запис (`feat/account`)
## СПРИНТ 23. Запуск
### - [ ] Таск 23.1. Юридичне (`chore/legal`)
### - [ ] Таск 23.2. Інфраструктура (`chore/prod-infra`)
"""


def test_plan_is_parsed_by_sections():
    plan = parse_plan(PLAN)
    assert [t.id for t in plan.tasks] == ["10.4", "10.5", "A.1", "A.2", "A.3", "17.5", "23.1", "23.2"]
    assert plan.tasks[0].done and plan.tasks[0].title == "Драбина"
    assert set(plan.sections) == {"СПРИНТ 10. Майстерня", "Знайдено при самоперевірці", "СПРИНТ 17. Клуб", "СПРИНТ 23. Запуск"}


def test_priority_expands_ranges_and_sprints_and_skips_done():
    plan = parse_plan(PLAN)
    assert plan.priority == ["10.5", "A.1", "A.2", "A.3", "17.5", "23.1", "23.2"]
    assert [t.id for t in next_tasks(plan)] == ["10.5", "A.1", "A.3", "17.5", "23.1", "23.2"]


def test_real_status_builds():
    status = build_status(Path(__file__).resolve().parent.parent)
    assert "# Project status" in status and "Migration head" in status and "Next in work order" in status
