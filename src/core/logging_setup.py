# --- FILE: src/core/logging_setup.py ---
"""
Server logs (the observability task of 21.11.2026): one format for the API, WebSocket and Celery workers, so that any
complaint like "my game disappeared" can be analysed by the chain of events and reproduced.

What the module does:
- The record context (request_id, user_id, game_id, tournament_id, task...) lies in a contextvar and is mixed into EVERY
  log line automatically - whoever writes it (bind_log_context). For HTTP the context is set by
  request_log_middleware, for WebSocket - matchmaking_endpoint, for Celery tasks - the signals in worker/celery_app.py.
- Format: json (one JSON line per record - for collecting into Loki/ELK/files) or text (for reading in the console). Chosen by
  LOG_FORMAT; auto - json in production, text in development. The rotating file (LOG_FILE) is always written in json.
- request_log_middleware - the "end-to-end request id": takes the client's X-Request-ID (if it is safe) or creates
  its own, returns it in the response and writes one http_request line per request (method, route template, status, time).
  The client (frontend/src/services/http.ts) sends its own id in every request and together with a page error sends
  the latest requests - by them the whole chain is found in the log.

What does NOT go into the log: request and response bodies, passwords, tokens, Authorization and Cookie headers, e-mail - only
numeric ids and codes. Address parameters are not written: the route template (/games/{game_id}) is logged, not the path
itself.
"""

import contextvars
import json
import logging
import logging.handlers
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import sentry_sdk
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.core.config import settings
from src.core.errors import error_payload

# A request id from the client is accepted only in a safe form: it goes into the log and into the response header.
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
REQUEST_ID_HEADER = "X-Request-ID"
# Requests longer than this (seconds) are written at WARNING level: they are used to look for "hangs" without metrics.
SLOW_REQUEST_S = 2.0
# Service paths are written at DEBUG level: health and metrics polling would otherwise flood the log.
QUIET_PATHS = frozenset({"/health", "/metrics"})
# Attributes of an ordinary logging record - everything else is considered "extra fields" (extra=...).
_STANDARD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}

# Context fields that are duplicated as Sentry event tags.
_SENTRY_TAGS = frozenset({"request_id", "user_id", "game_id", "task", "ws_id"})

_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("log_context", default=None)


def bind_log_context(**fields: Any) -> None:
    """Adds fields to the context of the current request, WebSocket message or task; None values are skipped."""
    current = _context.get()
    if current is None:
        current = {}
        _context.set(current)
    current.update({key: value for key, value in fields.items() if value is not None})
    # The same fields as Sentry event tags: by request_id the event is found in the server log too (set_tag without Sentry is a
    # no-op).
    for key in _SENTRY_TAGS & fields.keys():
        if fields[key] is not None:
            sentry_sdk.set_tag(key, str(fields[key]))


def unbind_log_context(*keys: str) -> None:
    """Removes fields from the context (for example game_id after an action: the connection outlives the action)."""
    current = _context.get()
    if current:
        for key in keys:
            current.pop(key, None)


def start_log_context(**fields: Any) -> contextvars.Token:
    """Starts a new context (for a request or a task); the returned token is passed to end_log_context."""
    token = _context.set({})
    bind_log_context(**fields)
    return token


def end_log_context(token: contextvars.Token) -> None:
    """Restores the context that was before start_log_context."""
    _context.reset(token)


def current_log_context() -> dict[str, Any]:
    """A copy of the current context (for tests and for passing to someone else's task)."""
    return dict(_context.get() or {})


def new_request_id() -> str:
    """Our own request id, if the client did not send one or sent an unsafe one."""
    return uuid.uuid4().hex[:16]


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {key: value for key, value in record.__dict__.items() if key not in _STANDARD_ATTRS and not key.startswith("_")}


class JsonFormatter(logging.Formatter):
    """One record - one JSON line: UTC time, level, source, message, context, fields and the error with a stack."""

    def __init__(self, component: str) -> None:
        super().__init__()
        self.component = component

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "component": self.component,
            "msg": record.getMessage(),
            **(_context.get() or {}),
            **_extra_fields(record),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """A readable line for the developer's console; the context is in square brackets after the message."""

    def format(self, record: logging.LogRecord) -> str:
        context = {**(_context.get() or {}), **_extra_fields(record)}
        tail = " ".join(f"{key}={value}" for key, value in context.items())
        stamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        base = f"{stamp} {record.levelname:<7} {record.name}: {record.getMessage()}"
        text = f"{base} [{tail}]" if tail else base
        if record.exc_info:
            text += "\n" + self.formatException(record.exc_info)
        return text


def resolve_format() -> str:
    """json or text: LOG_FORMAT, and with auto - json in production and text in development."""
    configured = settings.LOG_FORMAT.lower()
    if configured in ("json", "text"):
        return configured
    return "json" if settings.is_production else "text"


def setup_logging(component: str) -> None:
    """
    Configures the process root log: the console (the format by resolve_format) and, if LOG_FILE is set, a rotating file
    in json. component is "api" or "worker": written into every json line. A repeated call replaces the handlers
    (--reload and tests do not breed duplicates). The uvicorn access lines are off: they are replaced by http_request below.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_regence", False):
            root.removeHandler(handler)
    root.setLevel(settings.LOG_LEVEL.upper())

    console = logging.StreamHandler()
    console.setFormatter(JsonFormatter(component) if resolve_format() == "json" else TextFormatter())
    console._regence = True  # type: ignore[attr-defined]
    root.addHandler(console)

    if settings.LOG_FILE:
        file_handler = logging.handlers.RotatingFileHandler(
            settings.LOG_FILE, maxBytes=settings.LOG_FILE_MAX_MB * 1024 * 1024,
            backupCount=settings.LOG_FILE_BACKUPS, encoding="utf-8",
        )
        file_handler.setFormatter(JsonFormatter(component))
        file_handler._regence = True  # type: ignore[attr-defined]
        root.addHandler(file_handler)

    logging.getLogger("uvicorn.access").disabled = True


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or request.url.path


request_logger = logging.getLogger("regence.http")


async def request_log_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """
    Sets up the request context (request_id), writes the http_request line and returns the id in the X-Request-ID header.
    An unhandled exception is written with the full stack (http_unhandled_error); the client gets 500 with the code
    internal_error and the same id in the header. A client id is accepted only by REQUEST_ID_PATTERN.
    """
    supplied = request.headers.get(REQUEST_ID_HEADER, "")
    request_id = supplied if REQUEST_ID_PATTERN.match(supplied) else new_request_id()
    token = start_log_context(request_id=request_id)
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    except Exception:
        request_logger.exception(
            "http_unhandled_error", extra={"method": request.method, "route": _route_template(request)})
        # A 500 response in the common error format and with the request id: the player can name it in a complaint, and the
        # client can attach it
        # to the report (in an ordinary server response the 500 would have no body and no header).
        return JSONResponse(
            status_code=500, content={"detail": error_payload("internal_error")}, headers={REQUEST_ID_HEADER: request_id},
        )
    finally:
        duration = time.perf_counter() - start
        route = _route_template(request)
        if route in QUIET_PATHS:
            level = logging.DEBUG
        else:
            level = logging.WARNING if duration > SLOW_REQUEST_S or status >= 500 else logging.INFO
        request_logger.log(level, "http_request", extra={
            "method": request.method, "route": route, "status": status, "duration_ms": round(duration * 1000, 1),
        })
        end_log_context(token)
