# --- FILE: src/services/auth_sessions.py ---
"""
Login sessions (task 17.5): a short access token in client memory + a long refresh token in an httpOnly cookie.

Previously the JWT lived a day in localStorage — any script injected into the page (XSS) could steal it. Now:
* the access token (JWT, ACCESS_TOKEN_EXPIRE_MINUTES) is kept by the client only in memory and sent in Authorization, as
  before;
* the refresh token is a random string in a cookie HttpOnly + SameSite=Strict, path /api/v1/auth: page script cannot
  see it, and it is not sent to other sites or to the rest of the API requests. Redis holds only its hash: refresh:<sha256> →
  "<user_id>:<token_version>", lifetime REFRESH_TOKEN_EXPIRE_DAYS, extended on every refresh.
* Revocation: logout deletes the record; "log out everywhere", password change and account deletion increase token_version —
  all
  refresh tokens with the old version stop working. The version from the record is compared with users.token_version by the
  refresh
  route (src/api/auth.py); this module only stores and reads the record.

The token does not change on refresh (no rotation): a player may have several tabs, and rotation would break the session
in the one that refreshed second.
"""

import hashlib
import logging
import secrets
from collections.abc import Mapping

from fastapi import Response

from src.core.config import settings
from src.db import redis as redis_module

logger = logging.getLogger(__name__)

# Name of the cookie with the refresh token and the start of the Redis key under which the session record is stored.
REFRESH_COOKIE = "regence_refresh"
REFRESH_PREFIX = "refresh:"


def _key(token: str) -> str:
    """Redis key for a token: the key holds the sha256 of the token, so the token cannot be recovered from Redis contents."""
    return REFRESH_PREFIX + hashlib.sha256(token.encode()).hexdigest()


def _ttl_s() -> int:
    return settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400


def cookie_secure() -> bool:
    """Secure by default in production; browsers accept such cookies on http://localhost too."""
    return settings.is_production if settings.COOKIE_SECURE is None else settings.COOKIE_SECURE


def read_refresh_cookie(cookies: Mapping[str, str]) -> str | None:
    """Refresh token from the request cookie. The former name (michess_refresh) is not read: the site was never deployed."""
    return cookies.get(REFRESH_COOKIE)


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE, token, max_age=_ttl_s(), httponly=True, secure=cookie_secure(), samesite="strict",
        path=f"{settings.API_V1_STR}/auth",
    )


def clear_refresh_cookie(response: Response, name: str = REFRESH_COOKIE) -> None:
    """Erases the refresh cookie (by default — under the current name)."""
    response.delete_cookie(
        name, httponly=True, secure=cookie_secure(), samesite="strict", path=f"{settings.API_V1_STR}/auth",
    )


async def issue(user_id: int, token_version: int) -> str:
    """New login session: a random refresh token and a record about it in Redis for REFRESH_TOKEN_EXPIRE_DAYS days."""
    token = secrets.token_urlsafe(32)
    await redis_module.redis_client.set(_key(token), f"{user_id}:{token_version}", ex=_ttl_s())
    return token


async def lookup(token: str | None) -> tuple[int, int] | None:
    """
    (user_id, token_version) by refresh token and extension of its lifetime; None — no token or it is revoked. Unavailable
    Redis is also None: the player will have to log in again.
    """
    if not token:
        return None
    try:
        value = await redis_module.redis_client.get(_key(token))
        if value is None:
            return None
        await redis_module.redis_client.expire(_key(token), _ttl_s())
    except Exception as exc:
        logger.warning("Refresh session lookup failed: %s", exc)
        return None
    user_id, _, version = str(value).partition(":")
    if not user_id.isdigit() or not version.lstrip("-").isdigit():
        return None
    return int(user_id), int(version)


async def revoke(token: str | None) -> None:
    """Logout: deletes the session record of this token. A Redis failure is only logged — the record will expire by itself."""
    if not token:
        return
    try:
        await redis_module.redis_client.delete(_key(token))
    except Exception as exc:
        logger.warning("Refresh session revoke failed: %s", exc)
