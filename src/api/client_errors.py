# --- FILE: src/api/client_errors.py ---
"""
Client error reports (observability, 21.11.2026): POST /client-errors accepts from the page information about a failure -
a render error, an unhandled exception, a dropped connection - and writes it to the server log as a
`client_error` line (logger regence.client) together with the request id and the player. This way the bug "the page suddenly
reloaded"
is visible in the same log as server events: by the `request_id` from the "breadcrumbs" the whole chain is found.

Open without login (a failure may happen before login), therefore: the sizes of all fields are limited, the limit per address
(RATE_LIMIT_CLIENT_ERRORS per window) - over the limit reports are silently dropped (the same 204 response: there is no need to
tell the client about
the limit, and it must not retry sending). Nothing is written to the database. The client does not send request bodies, tokens
or personal data;
in any case the server writes only the short fields that were sent. The client part -
frontend/src/services/clientErrors.ts.
"""

import logging
from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from src.api.rate_limit import client_ip, try_consume
from src.core.config import settings
from src.core.logging_setup import REQUEST_ID_PATTERN, bind_log_context

router = APIRouter(tags=["observability"])
client_logger = logging.getLogger("regence.client")

# Report field limits: the excess is cut off at parsing instead of being silently accepted.
MAX_MESSAGE = 500
MAX_STACK = 4000
MAX_URL = 300
MAX_BREADCRUMBS = 30


class Breadcrumb(BaseModel):
    """One event before a failure: an API request (with its id), a WebSocket message, a page change."""
    t: int = Field(..., description="Unix time in milliseconds")
    kind: Literal["request", "socket", "route", "reload"]
    name: str = Field(..., max_length=120)
    status: int | None = None
    request_id: str | None = Field(None, max_length=64)


class ClientErrorIn(BaseModel):
    """A page failure report."""
    kind: Literal["render", "error", "unhandledrejection", "socket", "reload"]
    message: str = Field(..., max_length=MAX_MESSAGE)
    stack: str | None = Field(None, max_length=MAX_STACK)
    url: str = Field(..., max_length=MAX_URL)
    release: str | None = Field(None, max_length=40)
    game_id: int | None = None
    breadcrumbs: list[Breadcrumb] = Field(default_factory=list, max_length=MAX_BREADCRUMBS)


@router.post("/client-errors", status_code=status.HTTP_204_NO_CONTENT)
async def report_client_error(report: ClientErrorIn, request: Request) -> Response:
    """Writes the client report to the log; over the per-address limit - silently drops it (204 in both cases)."""
    if not await try_consume("client_error", f"ip:{client_ip(request)}",
                             settings.RATE_LIMIT_CLIENT_ERRORS, settings.RATE_LIMIT_CLIENT_ERRORS_WINDOW_S):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    bind_log_context(game_id=report.game_id)
    crumbs = [c.model_dump(exclude_none=True) for c in report.breadcrumbs]
    # Request ids from the breadcrumbs - as a separate list: handy for searching server lines.
    related = [c["request_id"] for c in crumbs if REQUEST_ID_PATTERN.match(c.get("request_id", ""))]
    client_logger.error("client_error", extra={
        "client_kind": report.kind, "client_message": report.message, "client_stack": report.stack,
        "client_url": report.url, "release": report.release, "breadcrumbs": crumbs, "related_request_ids": related,
    })
    return Response(status_code=status.HTTP_204_NO_CONTENT)
