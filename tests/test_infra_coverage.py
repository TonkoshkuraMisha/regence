"""
Infrastructure modules: Celery signals and schedule (src/worker/celery_app.py), task dispatch
(src/services/task_dispatch.py), mail sending (src/services/mailer.py), the rate limiter
(src/api/rate_limit.py) and the application lifecycle (src/main.py). Broker, SMTP and Redis are stubbed;
time is fixed by stubbing the clock.
"""

import asyncio
import logging
import smtplib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src import main as main_module
from src.api import rate_limit
from src.core.config import settings
from src.core.security import create_user_token
from src.services import mailer, task_dispatch
from src.worker import celery_app as celery_module

# ---------------------------------------------------------------- celery_app


def test_task_signals_open_and_close_log_context(caplog):
    with caplog.at_level(logging.INFO, logger="regence.task"):
        celery_module._bind_task_context(task_id="t1", task=SimpleNamespace(name="analyze_game"), args=(7,))
        assert "t1" in celery_module._task_log_tokens
        celery_module._release_task_context(task_id="t1", state="SUCCESS")
    assert "t1" not in celery_module._task_log_tokens
    assert "task_started" in caplog.text and "task_finished" in caplog.text


def test_task_context_without_numeric_arg_and_unknown_task():
    celery_module._bind_task_context(task_id="t2", task=None, args=("x",))
    celery_module._release_task_context(task_id="t2", state="SUCCESS")
    celery_module._release_task_context(task_id="never-started", state="SUCCESS")  # no token: does not fail
    assert "t2" not in celery_module._task_log_tokens


def test_task_failure_is_logged_with_stack(caplog):
    error = RuntimeError("boom")
    with caplog.at_level(logging.ERROR, logger="regence.task"):
        celery_module._log_task_failure(task_id="t3", exception=error, einfo=SimpleNamespace(tb=None))
        celery_module._log_task_failure(task_id="t4", exception=None)
    assert caplog.text.count("task_failed") == 2


def test_logging_and_metrics_signals(monkeypatch):
    configured: list[str] = []
    monkeypatch.setattr(celery_module, "configure_logging", configured.append)
    celery_module._configure_worker_logging()
    assert configured == ["worker"]

    ports: list[int] = []
    monkeypatch.setattr(celery_module, "start_worker_metrics_server", ports.append)
    celery_module._serve_worker_metrics()
    assert ports == [settings.WORKER_METRICS_PORT]

    forgotten: list[int] = []
    monkeypatch.setattr(celery_module, "forget_worker_process", forgotten.append)
    celery_module._forget_worker_process(pid=123)
    celery_module._forget_worker_process(pid=None)  # without a pid nothing is forgotten
    assert forgotten == [123]


def test_every_beat_task_is_routed_or_default():
    conf = celery_module.celery_app.conf
    for entry in conf.beat_schedule.values():
        assert entry["task"] in conf.task_routes or conf.task_default_queue == celery_module.ANALYSIS_QUEUE


# ------------------------------------------------------------- task_dispatch


@pytest.fixture
def cooldown_reset():
    task_dispatch.reset_broker_cooldown()
    yield
    task_dispatch.reset_broker_cooldown()


def test_publish_helpers_call_apply_async_without_retry(monkeypatch):
    monkeypatch.undo()  # the conftest autouse fixture replaced _publish_* itself; the real ones are needed
    sent: list[tuple] = []
    for attr, name in (
        ("analyze_game_task", "analyze_game"), ("simulate_tournament_game_task", "simulate_tournament_game"),
        ("analyze_imported_game_task", "analyze_imported_game"),
    ):
        fake = SimpleNamespace(apply_async=lambda args=None, retry=None, _n=name: sent.append((_n, args, retry)))
        monkeypatch.setattr(task_dispatch, attr, fake)
    task_dispatch._publish_analysis(1)
    task_dispatch._publish_simulation(2)
    task_dispatch._publish_imported_analysis(3)
    assert sent == [("analyze_game", (1,), False), ("simulate_tournament_game", (2,), False),
                    ("analyze_imported_game", (3,), False)]


async def test_analysis_cooldown_skips_publish(monkeypatch, cooldown_reset):
    def broken(_id):
        raise ConnectionError("broker down")

    monkeypatch.setattr(task_dispatch, "_publish_analysis", broken)
    assert await task_dispatch.schedule_game_analysis(1) is False  # the failure triggered the pause
    monkeypatch.setattr(task_dispatch, "_publish_analysis", lambda _id: None)
    assert await task_dispatch.schedule_game_analysis(1) is False  # pause: nothing is published
    task_dispatch.reset_broker_cooldown()
    assert await task_dispatch.schedule_game_analysis(1) is True


@pytest.mark.parametrize(
    ("schedule", "publisher"),
    [
        (task_dispatch.schedule_tournament_simulations, "_publish_simulation"),
        (task_dispatch.schedule_imported_analyses, "_publish_imported_analysis"),
    ],
)
async def test_batch_schedulers_publish_and_cool_down(monkeypatch, cooldown_reset, schedule, publisher):
    published: list[int] = []
    monkeypatch.setattr(task_dispatch, publisher, published.append)
    assert await schedule([1, 2, 3]) == 3
    assert published == [1, 2, 3]

    def broken(_id):
        raise ConnectionError("down")

    monkeypatch.setattr(task_dispatch, publisher, broken)
    assert await schedule([4, 5]) == 0  # the first error triggers the pause
    assert await schedule([6]) == 0  # pause: nothing is published


@pytest.mark.parametrize(
    "background",
    [task_dispatch.schedule_tournament_simulations_in_background, task_dispatch.schedule_imported_analyses_in_background],
)
async def test_background_schedulers(monkeypatch, cooldown_reset, background):
    monkeypatch.setattr(task_dispatch, "_publish_simulation", lambda _id: None)
    monkeypatch.setattr(task_dispatch, "_publish_imported_analysis", lambda _id: None)
    assert background([]) is None
    task = background([1])
    assert task in task_dispatch._background_tasks
    assert await task == 1
    await asyncio.sleep(0)
    assert task not in task_dispatch._background_tasks


# -------------------------------------------------------------------- mailer


def test_render_falls_back_to_english_and_fills_params():
    subject, body = mailer.render("verify", "de", username="Ann", link="http://x", hours=24)
    assert subject == mailer.TEMPLATES["verify"]["en"][0]
    assert "Ann" in body and "http://x" in body and "24" in body
    assert mailer.render("reset", "uk", username="A", link="L", hours=1)[0] == mailer.TEMPLATES["reset"]["uk"][0]


async def test_send_without_smtp_host_only_logs(monkeypatch, caplog):
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    called: list[object] = []
    monkeypatch.setattr(mailer, "_send_smtp", called.append)
    with caplog.at_level(logging.INFO):
        await mailer.send("a@b.c", "Subject", "Body")
    assert called == [] and "not sent" in caplog.text


async def test_send_builds_message_and_uses_smtp(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "MAIL_FROM", "noreply@test")
    sent: list = []
    monkeypatch.setattr(mailer, "_send_smtp", sent.append)
    await mailer.send("a@b.c", "Subj", "Body")
    assert sent[0]["To"] == "a@b.c" and sent[0]["From"] == "noreply@test" and sent[0]["Subject"] == "Subj"


@pytest.mark.parametrize("error", [OSError("net"), smtplib.SMTPException("smtp")])
async def test_send_swallows_transport_errors(monkeypatch, caplog, error):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")

    def fail(_message):
        raise error

    monkeypatch.setattr(mailer, "_send_smtp", fail)
    with caplog.at_level(logging.ERROR):
        await mailer.send("a@b.c", "S", "B")
    assert "failed" in caplog.text


class _FakeSMTP:
    instances: list[_FakeSMTP] = []

    def __init__(self, host, port, timeout):
        self.log: list[tuple] = [("connect", host, port, timeout)]
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.log.append(("starttls",))

    def login(self, user, password):
        self.log.append(("login", user, password))

    def send_message(self, message):
        self.log.append(("send", message["To"]))


@pytest.mark.parametrize(("starttls", "user"), [(True, "u"), (False, "")])
def test_send_smtp_session_steps(monkeypatch, starttls, user):
    from email.message import EmailMessage

    _FakeSMTP.instances.clear()
    monkeypatch.setattr(mailer.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "SMTP_STARTTLS", starttls)
    monkeypatch.setattr(settings, "SMTP_USER", user)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")
    message = EmailMessage()
    message["To"] = "a@b.c"
    mailer._send_smtp(message)
    steps = [entry[0] for entry in _FakeSMTP.instances[0].log]
    assert steps == ["connect", *(["starttls"] if starttls else []), *(["login"] if user else []), "send"]


# ---------------------------------------------------------------- rate_limit


def _request(headers: dict[str, str] | None = None, client: tuple[str, int] | None = ("1.2.3.4", 5)) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw, "client": client, "method": "GET", "path": "/"})


def test_identity_by_token_or_ip():
    token = create_user_token(SimpleNamespace(id=42, token_version=0))
    assert rate_limit.client_identity(_request({"Authorization": f"Bearer {token}"})) == "user:42"
    assert rate_limit.client_identity(_request({"Authorization": "Bearer broken"})) == "ip:1.2.3.4"
    assert rate_limit.client_identity(_request()) == "ip:1.2.3.4"
    assert rate_limit.client_ip(_request(client=None)) == "unknown"


class _BrokenRedis:
    async def incr(self, *a, **k):
        raise ConnectionError("down")

    async def get(self, *a, **k):
        raise ConnectionError("down")

    async def expire(self, *a, **k):
        raise ConnectionError("down")


async def test_try_consume_counts_and_unlimited(freeze_rate_limit_window):
    assert await rate_limit.try_consume("s", "ip:1", 0, 60) is True  # limit<=0 means unlimited
    assert [await rate_limit.try_consume("s", "ip:1", 2, 60) for _ in range(3)] == [True, True, False]


async def test_rate_limiter_fails_open_when_redis_down(monkeypatch, freeze_rate_limit_window):
    monkeypatch.setattr(rate_limit.redis_module, "redis_client", _BrokenRedis())
    assert await rate_limit.try_consume("s", "ip:1", 1, 60) is True
    await rate_limit.ensure_below_limit("s", "ip:1", 1, 60, "code")
    await rate_limit.record_attempt("s", "ip:1", 60)
    quota = rate_limit.DailyQuota("x", "RATE_LIMIT_WINDOW_S")
    monkeypatch.setattr(settings, "FREE_TIER_LIMITS", True)
    await quota.check(_request())


async def test_enforce_rate_limit_raises_429_with_retry_after(freeze_rate_limit_window):
    await rate_limit.enforce_rate_limit("e", "ip:1", 1, 60, "rate_limited")
    with pytest.raises(HTTPException) as caught:
        await rate_limit.enforce_rate_limit("e", "ip:1", 1, 60, "rate_limited")
    assert caught.value.status_code == 429 and "Retry-After" in caught.value.headers


async def test_ensure_below_limit_and_record_attempt(freeze_rate_limit_window):
    await rate_limit.ensure_below_limit("f", "ip:1", 0, 60, "rate_limited")  # limit disabled
    await rate_limit.ensure_below_limit("f", "ip:1", 2, 60, "rate_limited")
    await rate_limit.record_attempt("f", "ip:1", 60)
    await rate_limit.record_attempt("f", "ip:1", 60)
    with pytest.raises(HTTPException) as caught:
        await rate_limit.ensure_below_limit("f", "ip:1", 2, 60, "rate_limited")
    assert caught.value.status_code == 429


async def test_daily_quota_off_then_on(monkeypatch, freeze_rate_limit_window):
    quota = rate_limit.DailyQuota("analysis", "RATE_LIMIT_WINDOW_S")
    request = _request()
    monkeypatch.setattr(settings, "FREE_TIER_LIMITS", False)
    assert quota.limit() == 0
    await quota.record(request)
    await quota.check(request)  # disabled: counts and forbids nothing

    monkeypatch.setattr(settings, "FREE_TIER_LIMITS", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_WINDOW_S", 2)
    assert quota.limit() == 2
    await quota.check(request)
    await quota.record(request)
    await quota.record(request)
    with pytest.raises(HTTPException) as caught:
        await quota.check(request)
    assert caught.value.status_code == 429


async def test_rate_limit_dependency_uses_guest_limit_for_ip(monkeypatch, freeze_rate_limit_window):
    monkeypatch.setattr(settings, "RATE_LIMIT_WINDOW_S", 60)
    monkeypatch.setattr(settings, "FREE_TIER_LIMITS", False)
    dependency = rate_limit.rate_limit("dep", "RATE_LIMIT_POSITION_ANALYSIS", "RATE_LIMIT_POSITION_ANALYSIS_GUEST")
    guest_limit = int(settings.RATE_LIMIT_POSITION_ANALYSIS_GUEST)
    for _ in range(guest_limit):
        await dependency(_request())
    with pytest.raises(HTTPException):
        await dependency(_request())


# ---------------------------------------------------------------------- main


async def test_lifespan_starts_loop_and_closes_resources(monkeypatch):
    started = asyncio.Event()

    async def fake_loop(_manager):
        started.set()
        await asyncio.sleep(3600)

    closed: list[str] = []

    class FakeRedis:
        async def aclose(self):
            closed.append("redis")

    monkeypatch.setattr(main_module.state_manager, "check_timeouts_loop", fake_loop)
    monkeypatch.setattr(main_module, "close_all_engine_pools", lambda: closed.append("engines"))
    monkeypatch.setattr(main_module.redis_module, "redis_client", FakeRedis())
    async with main_module.lifespan(main_module.app):
        await asyncio.wait_for(started.wait(), 1)
    assert closed == ["engines", "redis"]


async def test_game_analysis_background_task_is_tracked(cooldown_reset):
    task = task_dispatch.schedule_game_analysis_in_background(1)
    assert task in task_dispatch._background_tasks
    assert await task is True  # publishing is stubbed by the conftest fixture
    await asyncio.sleep(0)
    assert task not in task_dispatch._background_tasks
