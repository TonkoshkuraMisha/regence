"""
The Celery application: queues and the schedule of background tasks. The broker and the result store are Redis (databases 0 and
1).

There are two queues so that long bot games do not delay the review of players' games: analysis (the default - game review,
the position index, reminders) and simulation (bot-vs-bot games, self-play). In production they are listened to by different
workers
(docker-compose.prod.yml), in development by one. The schedule (beat_schedule) is run by a separate celery beat process -
there must be only one for the whole installation. The tasks themselves are in src/worker/tasks.py; the list with the schedule
is DEPLOY.md, 8c.

Publishing tasks from the API must not delay a game, so the broker connection timeouts are short and there are no publish
retries (see src/services/task_dispatch.py).

The worker's Prometheus metrics (engine time in reviews and simulations) are served by the main process on WORKER_METRICS_PORT
-
the signals below, the rules - src/core/observability.start_worker_metrics_server.
"""

import logging

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging, task_failure, task_postrun, task_prerun, worker_init, worker_process_shutdown

from src.core.config import settings
from src.core.logging_setup import end_log_context, start_log_context
from src.core.logging_setup import setup_logging as configure_logging
from src.core.observability import forget_worker_process, init_sentry, start_worker_metrics_server

init_sentry("worker")


# Tokens of log contexts by task ids: prerun opens a context, postrun closes it (src/core/logging_setup.py).
_task_log_tokens: dict[str, object] = {}
_task_logger = logging.getLogger("regence.task")


@setup_logging.connect
def _configure_worker_logging(**_) -> None:
    """A single worker log format (json/text, file) instead of Celery's own configuration."""
    configure_logging("worker")


@task_prerun.connect
def _bind_task_context(task_id=None, task=None, args=None, **_) -> None:
    """Every log line inside a task carries its name and id; the first numeric argument is the game id (game_id)."""
    game_id = args[0] if args and isinstance(args[0], int) else None
    _task_log_tokens[task_id] = start_log_context(task=getattr(task, "name", None), task_id=task_id, game_id=game_id)
    _task_logger.info("task_started")


@task_postrun.connect
def _release_task_context(task_id=None, state=None, **_) -> None:
    """Closes the task context; the outcome (state) is written as a task_finished line."""
    _task_logger.info("task_finished", extra={"state": state})
    token = _task_log_tokens.pop(task_id, None)
    if token is not None:
        end_log_context(token)  # type: ignore[arg-type]


@task_failure.connect
def _log_task_failure(task_id=None, exception=None, einfo=None, **_) -> None:
    """A task failure - with a stack: without it the worker would write only a Celery line without context."""
    _task_logger.error("task_failed", exc_info=(type(exception), exception, getattr(einfo, "tb", None)) if exception else None)


@worker_init.connect
def _serve_worker_metrics(**_) -> None:
    """The worker main process (before the children are started): /metrics on WORKER_METRICS_PORT, if it is set."""
    start_worker_metrics_server(settings.WORKER_METRICS_PORT)


@worker_process_shutdown.connect
def _forget_worker_process(pid: int | None = None, **_) -> None:
    """A child process ends - its "live" indicators are no longer summed."""
    if pid:
        forget_worker_process(pid)

ANALYSIS_QUEUE = "analysis"
SIMULATION_QUEUE = "simulation"

celery_app = Celery(
    "regence_worker",
    broker=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0",
    backend=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/1",
    include=["src.worker.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Publishing from the API process must not hang long on an unavailable broker
    # (by default kombu waits for the connection for ~4 s and retries).
    broker_connection_timeout=settings.CELERY_BROKER_CONNECT_TIMEOUT_S,
    broker_transport_options={
        "socket_connect_timeout": settings.CELERY_BROKER_CONNECT_TIMEOUT_S,
        "socket_timeout": settings.CELERY_PUBLISH_TIMEOUT_S,
    },
    task_publish_retry=False,
    # The worker at start still waits for the broker (that is a separate setting).
    broker_connection_retry_on_startup=True,
    # Two queues (task A.4): the review of a just-played player game does not wait until the bot games are finished
    # in a tournament (in an 8-participant round-robin - 28 games, 21 of them bots play among themselves).
    # In production they are listened to by different workers (docker-compose.prod.yml), in development by one
    # (start_dev.ps1, -Q analysis,simulation).
    task_default_queue=ANALYSIS_QUEUE,
    task_routes={
        "analyze_game": {"queue": ANALYSIS_QUEUE},
        "analyze_imported_game": {"queue": ANALYSIS_QUEUE},
        "simulate_tournament_game": {"queue": SIMULATION_QUEUE},
        "workout_reminders": {"queue": ANALYSIS_QUEUE},
        "arena_reminders": {"queue": ANALYSIS_QUEUE},
        "archive_move_telemetry": {"queue": ANALYSIS_QUEUE},
        "purge_deleted_accounts": {"queue": ANALYSIS_QUEUE},
        "arena_awards": {"queue": ANALYSIS_QUEUE},
        "bot_selfplay": {"queue": SIMULATION_QUEUE},
    },
    # Scheduled tasks (the celery beat process, the beat service in docker-compose.prod.yml; the list - DEPLOY.md, section 8c).
    # The warm-up reminder 22.2 - once a day, at 16:00 UTC: evening in Europe.
    beat_schedule={
        "workout-reminders": {"task": "workout_reminders", "schedule": crontab(hour=16, minute=0)},
        # Archetype self-play (task 32.3): every 6 hours, at minute 17 - not together with other scheduled tasks.
        "bot-selfplay": {"task": "bot_selfplay", "schedule": crontab(hour="*/6", minute=17)},
        # Arena start reminders (task 33.4): every minute - the notification goes out five minutes before the start
        # (arena.REMIND_BEFORE).
        "arena-reminders": {"task": "arena_reminders", "schedule": crontab()},
        # Move telemetry retention (task 9 of the 18.11 plan): once a day at night UTC, at minute 41 - not together with
        # others.
        "archive-move-telemetry": {"task": "archive_move_telemetry", "schedule": crontab(hour=3, minute=41)},
        # Arena awards (task 33.5): every 5 minutes - winners get their places soon after the results are final.
        "arena-awards": {"task": "arena_awards", "schedule": crontab(minute="*/5")},
        # Review of old unfair-play flags (task 26.4): on Monday mornings UTC.
        "review-cheater-flags": {"task": "review_cheater_flags", "schedule": crontab(day_of_week=1, hour=6, minute=7)},
        # Accounts past the deletion grace period are anonymised (task 23.1): once a day, at 04:23 UTC.
        "purge-deleted-accounts": {"task": "purge_deleted_accounts", "schedule": crontab(hour=4, minute=23)},
        # The new legends week is open (task 26.1): Monday morning UTC, at minute 11 - not together with other scheduled tasks.
        "legends-week-start": {"task": "legends_week_start", "schedule": crontab(day_of_week=1, hour=8, minute=11)},
    },
    # Do not prefetch long simulation games: otherwise one worker takes a queue and holds it.
    worker_prefetch_multiplier=1,
)
