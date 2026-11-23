# --- FILE: src/api/rate_limit.py ---
"""
Request rate limiting: endpoints that load Stockfish, login and registration, e-mails, game import,
the open API and engine-free sections (each section has its own counter), as well as WebSocket messages
(src/api/websockets.py calls try_consume).

A fixed window in Redis (INCR + EXPIRE): the key ratelimit:{scope}:{who}:{window number}, where "who" is user:<id>,
ip:<address>, account:<name> or to:<e-mail>. The quota is counted per user if the request
came with a valid Bearer token, otherwise per IP address (guest games with bots and viewing
analysis are available without login). The token is only decoded, without touching the DB (a revoked but not yet expired token
is still counted for its player - that is enough for the counter). The limits themselves are the RATE_LIMIT_* settings
(src/core/config.py). When Redis is unavailable requests are let through: an accounting failure must not stop the site.

DailyQuota - daily quotas of the free tier; while FREE_TIER_LIMITS is off, they limit nothing.
"""

import logging
import time

import jwt
from fastapi import HTTPException, Request, status

from src.core.config import settings
from src.core.errors import ApiError
from src.db import redis as redis_module

logger = logging.getLogger(__name__)


def _client_identity(request: Request) -> str:
    """"user:<id>" by the token signature and expiry (the token version is not checked, the DB is not read), otherwise
    "ip:<address>"."""
    auth_header = request.headers.get("authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            subject = payload.get("sub")
            if subject:
                return f"user:{subject}"
        except jwt.InvalidTokenError:
            pass
    return f"ip:{client_ip(request)}"


def client_identity(request: Request) -> str:
    """The player by token, and without login - the address: a shared limit key for endpoints open to guests."""
    return _client_identity(request)


def client_ip(request: Request) -> str:
    """
    The client address. In production uvicorn is started with --proxy-headers (Dockerfile) and takes it from X-Forwarded-For,
    which nginx sets; without a proxy - the connection address. "unknown" - the address could not be determined.
    """
    return request.client.host if request.client else "unknown"


def _window(window_s: int) -> tuple[int, int]:
    """(the number of the current window, seconds until its end)."""
    now = int(time.time())
    return now // window_s, max(1, window_s - now % window_s)


def _too_many(code: str, retry_after: int) -> HTTPException:
    """429 with an error code; how many seconds to retry - both in the header and in the parameters for the text."""
    return ApiError(
        status.HTTP_429_TOO_MANY_REQUESTS, code,
        headers={"Retry-After": str(retry_after)}, retry_after=retry_after,
    )


async def try_consume(scope: str, identity: str, limit: int, window_s: int) -> bool:
    """
    Counts an attempt; False if there are already more than limit of them in the current window.
    limit <= 0 - no limit. When Redis is unavailable it lets through (fail-open).
    """
    if limit <= 0:
        return True
    window_id, _ = _window(window_s)
    key = f"ratelimit:{scope}:{identity}:{window_id}"
    redis_client = redis_module.redis_client
    try:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, window_s + 1)
    except Exception as exc:
        # Redis is unavailable - we do not block users (fail-open), but we record the problem.
        logger.warning("Rate limiter unavailable for %s: %s", scope, exc)
        return True
    return count <= limit


async def enforce_rate_limit(scope: str, identity: str, limit: int, window_s: int, code: str) -> None:
    """Like try_consume, but for HTTP: raises 429 with Retry-After."""
    if not await try_consume(scope, identity, limit, window_s):
        raise _too_many(code, _window(window_s)[1])


async def ensure_below_limit(scope: str, identity: str, limit: int, window_s: int, code: str) -> None:
    """Checks the counter without increasing it (for example of failed logins): 429 if the limit is exhausted."""
    if limit <= 0:
        return
    window_id, retry_after = _window(window_s)
    try:
        count = int(await redis_module.redis_client.get(f"ratelimit:{scope}:{identity}:{window_id}") or 0)
    except Exception as exc:
        logger.warning("Rate limiter unavailable for %s: %s", scope, exc)
        return
    if count >= limit:
        raise _too_many(code, retry_after)


async def record_attempt(scope: str, identity: str, window_s: int) -> None:
    """Increases the counter without checking (paired with ensure_below_limit)."""
    window_id, _ = _window(window_s)
    key = f"ratelimit:{scope}:{identity}:{window_id}"
    try:
        if await redis_module.redis_client.incr(key) == 1:
            await redis_module.redis_client.expire(key, window_s + 1)
    except Exception as exc:
        logger.warning("Rate limiter unavailable for %s: %s", scope, exc)


DAY_S = 86400


class DailyQuota:
    """
    The daily quota of the free tier for costly engine work (task 23.3): full game analysis, the mentor.
    Active only when FREE_TIER_LIMITS is on (tiers - 25.1). Completed work is counted, not the
    attempt: check() is the dependency before the computation, record() - after a successful response. The window is a UTC day.
    """

    def __init__(self, scope: str, limit_setting: str):
        self.scope = f"daily_{scope}"
        self.limit_setting = limit_setting

    def limit(self) -> int:
        """The current daily limit; 0 - the quota is off (FREE_TIER_LIMITS is not enabled)."""
        return int(getattr(settings, self.limit_setting)) if settings.FREE_TIER_LIMITS else 0

    async def check(self, request: Request) -> None:
        """
        Refusal 429 daily_limit_reached if the daily quota is already exhausted. When Redis is unavailable the request is let
        through:
        an accounting failure must not stop the site.
        """
        limit = self.limit()
        if limit <= 0:
            return
        window_id, retry_after = _window(DAY_S)
        try:
            used = int(await redis_module.redis_client.get(
                f"ratelimit:{self.scope}:{_client_identity(request)}:{window_id}") or 0)
        except Exception as exc:
            logger.warning("Daily quota unavailable for %s: %s", self.scope, exc)
            return
        if used >= limit:
            raise ApiError(
                status.HTTP_429_TOO_MANY_REQUESTS, "daily_limit_reached",
                headers={"Retry-After": str(retry_after)}, limit=limit, hours=-(-retry_after // 3600),
            )

    async def record(self, request: Request) -> None:
        """Counts completed work against the daily quota (called after a successful response)."""
        if self.limit() > 0:
            await record_attempt(self.scope, _client_identity(request), DAY_S)


def rate_limit(scope: str, limit_setting: str, guest_limit_setting: str | None = None,
               code: str = "engine_rate_limited"):
    """
    A FastAPI dependency factory for engine endpoints. limit_setting is the name of the Settings field
    with the per-window limit, read on every request (convenient to override in tests and via .env).
    guest_limit_setting is a separate (stricter) limit for requests without a token. code is the 429 error code (by
    default - the engine one; endpoints without an engine have their own text).
    """

    async def _dependency(request: Request) -> None:
        identity = _client_identity(request)
        setting = guest_limit_setting if guest_limit_setting and identity.startswith("ip:") else limit_setting
        await enforce_rate_limit(
            scope,
            identity,
            int(getattr(settings, setting)),
            int(settings.RATE_LIMIT_WINDOW_S),
            code,
        )

    return _dependency
