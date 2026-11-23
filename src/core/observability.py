"""
Observability: error collection in Sentry and Prometheus metrics.

Sentry is enabled only when SENTRY_DSN is set (without it - fully off). Personal
data (cookies, authorization headers, IP) is not sent. The FastAPI, Celery, SQLAlchemy integrations
and logging are connected automatically: everything logged via logger.exception/error (failures
of WS actions, the timeout loop, game analysis) becomes a Sentry event.

Metrics are served at GET /metrics of the API itself - nginx does not proxy this path outside, it is read by
Prometheus from inside the compose network (api:8000/metrics). The API runs in several uvicorn processes
(WEB_CONCURRENCY), so in production the multiprocess mode of prometheus_client is on: each
process writes values to files in PROMETHEUS_MULTIPROC_DIR, and /metrics sums them over all
processes. The variable must be set before importing prometheus_client: it is set by the api service in
docker-compose.prod.yml (the directory /tmp/prometheus on tmpfs, cleared at container start). In development
there is no variable - metrics are taken from the memory of the single process.

Celery workers (background review, tournament simulations) serve their own metrics - start_worker_metrics_server on the port
WORKER_METRICS_PORT; this way regence_engine_seconds_total counts background engine work too.

Where the values come from: WebSocket counters are increased by src/api/websockets.py, HTTP - by http_metrics_middleware below,
finished games and clock loop failures - src/services/game_state.py, engine time - src/services/engine_pool.py,
the number of players per day - Redis (key active_players:<UTC date>, the mark is set by src/api/deps.get_current_user).
"""

import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from starlette.requests import Request
from starlette.responses import Response

from src.core.config import settings

logger = logging.getLogger(__name__)

# --- Metrics ------------------------------------------------------------------------------------
# Labels come only from finite sets (an action name from the registry, a route template, an outcome), never
# user or game ids: otherwise the number of time series grows without bound.

WS_CONNECTIONS = Gauge(
    "regence_ws_connections", "Open WebSocket connections", multiprocess_mode="livesum",
)
WS_ACTIONS = Counter(
    "regence_ws_actions_total", "Processed WebSocket actions", ["action", "outcome"],
)
WS_ACTION_SECONDS = Histogram(
    "regence_ws_action_seconds", "WebSocket action processing time (make_move = move latency)", ["action"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
HTTP_REQUESTS = Counter(
    "regence_http_requests_total", "HTTP requests", ["method", "route", "status"],
)
HTTP_REQUEST_SECONDS = Histogram(
    "regence_http_request_seconds", "HTTP request processing time", ["method", "route"],
)
DB_POOL_CHECKED_OUT = Gauge(
    "regence_db_pool_checked_out", "Database connections currently checked out of the pool",
    multiprocess_mode="livesum",
)
# Only games between people (game_state.finish_game); games with bots (/bots/save-game) are not included.
GAMES_FINISHED = Counter(
    "regence_games_finished_total", "Games finished and recorded in the database", ["termination"],
)
TIMEOUT_CHECK_FAILURES = Counter(
    "regence_timeout_check_failures_total", "Failed timeout checks of individual games",
)
# The engine budget (task 23.3): "CPU per active player per day" =
#   increase(regence_engine_seconds_total[1d]) / regence_active_players_today (at the end of a UTC day).
# Engine time is counted by the pool itself (src/services/engine_pool.py), players per day - by a HyperLogLog in Redis.
ACTIVE_PLAYERS_TODAY = Gauge(
    "regence_active_players_today", "Distinct logged-in players seen today (UTC)", multiprocess_mode="mostrecent",
)
# Celery queues (task 23.2, alerts): the length is LLEN of the queue list in the Redis broker; computed on every /metrics
# request.
# A growing analysis queue means the worker cannot keep up with game review; simulation - with bot games in tournaments.
CELERY_QUEUE_LENGTH = Gauge(
    "regence_celery_queue_length", "Messages waiting in a Celery queue (not yet taken by a worker)", ["queue"],
    multiprocess_mode="mostrecent",
)
# The daily player counter is kept in Redis for three days - with a margin, so that yesterday's value can still be read.
ACTIVE_PLAYERS_TTL_S = 3 * 86400

# Outcomes of a WS action.
OUTCOME_OK = "ok"
OUTCOME_IGNORED = "ignored"
OUTCOME_REJECTED = "rejected"  # MatchmakingError: a regular refusal with an explanation to the client
OUTCOME_ERROR = "error"
OUTCOME_RATE_LIMITED = "rate_limited"


_LABEL_RE = re.compile(r"^[a-z_]{1,40}$")


def bounded_label(value: object) -> str:
    """A label value from a finite set: anything that does not look like a short identifier is "other"."""
    text = str(value or "").lower()
    return text if _LABEL_RE.match(text) else "other"


def _active_players_key(now: datetime | None = None) -> str:
    return f"active_players:{(now or datetime.now(UTC)).strftime('%Y-%m-%d')}"


async def note_active_player(user_id: int) -> None:
    """Marks the player as active today (HyperLogLog: ~12 KB per day for any number of players)."""
    from src.db import redis as redis_module

    key = _active_players_key()
    try:
        if await redis_module.redis_client.pfadd(key, user_id):
            await redis_module.redis_client.expire(key, ACTIVE_PLAYERS_TTL_S)
    except Exception as exc:  # a metric must not bring down a request
        logger.debug("Active player mark failed: %s", exc)


async def refresh_active_players() -> None:
    """Before serving /metrics: the number of players today from Redis."""
    from src.db import redis as redis_module

    try:
        ACTIVE_PLAYERS_TODAY.set(await redis_module.redis_client.pfcount(_active_players_key()))
    except Exception as exc:
        logger.debug("Active players count failed: %s", exc)


async def refresh_queue_lengths() -> None:
    """Before serving /metrics: how many messages wait in each Celery queue (the broker is the same Redis, db 0)."""
    from src.db import redis as redis_module

    # Imported here, not at the top: celery_app itself imports this module.
    from src.worker.celery_app import ANALYSIS_QUEUE, SIMULATION_QUEUE

    for queue in (ANALYSIS_QUEUE, SIMULATION_QUEUE):
        try:
            CELERY_QUEUE_LENGTH.labels(queue=queue).set(await redis_module.redis_client.llen(queue))
        except Exception as exc:  # a metric must not bring down /metrics
            logger.debug("Queue length failed for %s: %s", queue, exc)


def metrics_response() -> Response:
    """
    The body of the /metrics response in Prometheus format. If PROMETHEUS_MULTIPROC_DIR is set, the values are summed from the
    files
    of all uvicorn processes; otherwise the registry of the current process is taken.
    """
    return Response(generate_latest(_collect_registry()), media_type=CONTENT_TYPE_LATEST)


def _collect_registry() -> CollectorRegistry:
    """The registry for serving metrics: the sum of the files of all processes (multiprocess) or the registry of the current
    process."""
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    return REGISTRY


def start_worker_metrics_server(port: int) -> bool:
    """
    Serves the /metrics of a Celery worker on port (a thread in the worker's main process; called by the worker_init signal in
    src/worker/celery_app.py). Tasks are executed by child processes, so the worker and worker-simulation services,
    like api, have PROMETHEUS_MULTIPROC_DIR set - each container has its own tmpfs: a directory shared with api is not
    possible, process
    numbers in different containers coincide, and metric files would overwrite each other. Prometheus polls
    worker:9101 and worker-simulation:9101 together with api:8000 (DEPLOY.md, section 6) and sums them itself. port 0 - off.
    """
    if port <= 0:
        return False
    from prometheus_client import start_http_server

    start_http_server(port, registry=_collect_registry())
    logger.info("Worker metrics on port %s", port)
    return True


def forget_worker_process(pid: int) -> None:
    """
    A worker child process has ended: its "live" indicator files (Gauge livesum/liveall) are deleted so that
    the sum does not include the dead process. Counters (engine time) stay - their sum must not decrease.
    """
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        multiprocess.mark_process_dead(pid)


def route_template(scope) -> str:
    """
    The route template (/api/v1/profile/{username}), not the actual path - a finite set of labels.

    Since FastAPI 0.14x the route of an included router keeps the path without the include_router prefix
    (/profile/{username}), so the prefix is taken from the actual path: as many last
    segments as there are in the template - that is the substituted template.
    """
    route = scope.get("route")
    template = getattr(route, "path_format", None) or getattr(route, "path", None)
    if not template:
        return "unmatched"
    if ":path}" in template:  # a parameter may contain "/", the segments cannot be matched
        return template
    path_segments = scope.get("path", "").strip("/").split("/")
    template_segments = template.strip("/").split("/")
    prefix_len = len(path_segments) - len(template_segments)
    if prefix_len <= 0:
        return template
    return "/" + "/".join(path_segments[:prefix_len]) + template


async def http_metrics_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """
    Counts HTTP requests and their duration by route template and response code; the metrics request itself (/metrics) is not
    counted.
    """
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route_label = route_template(request.scope)
        if route_label != "/metrics":
            HTTP_REQUESTS.labels(request.method, route_label, str(status)).inc()
            HTTP_REQUEST_SECONDS.labels(request.method, route_label).observe(time.perf_counter() - start)


def instrument_engine(engine) -> None:
    """The counter of busy pool connections by the checkout/checkin events of the SQLAlchemy engine."""
    from sqlalchemy import event

    sync_engine = getattr(engine, "sync_engine", engine)
    event.listen(sync_engine, "checkout", lambda *_: DB_POOL_CHECKED_OUT.inc())
    event.listen(sync_engine, "checkin", lambda *_: DB_POOL_CHECKED_OUT.dec())


# --- Sentry -------------------------------------------------------------------------------------

def init_sentry(component: str) -> bool:
    """
    Connects Sentry if SENTRY_DSN is set; returns whether it is connected. component is "api" (called in src/main.py) or
    "worker" (src/worker/celery_app.py), it goes into the event tag. The release is regence@VERSION, personal data is not
    sent (send_default_pii=False).
    """
    if not settings.SENTRY_DSN:
        return False

    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        release=f"regence@{settings.VERSION}",
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("component", component)
    logger.info("Sentry enabled for %s (%s)", component, settings.ENVIRONMENT)
    return True
