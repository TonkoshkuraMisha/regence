"""
Login checks - route dependencies.

* get_current_user - for HTTP: the player by the token from the "Authorization: Bearer" header. The token is accepted only
  while its version matches users.token_version (user_from_token): a password change and "log out everywhere" revoke all
  earlier tokens. On the way the player is marked as active for the day - for metrics (src/core/observability.py,
  src/services/product_metrics.py).
* get_current_user_ws - for WebSocket: login by a one-time ticket. The ticket is issued by POST /auth/ws-ticket and put into
  Redis (key ws_ticket:<ticket>, TTL WS_TICKET_TTL_S); here it is taken by the GETDEL command and therefore works
  exactly once. A token in the WebSocket address is not used: addresses end up in server and proxy logs.
"""

from fastapi import Depends, Query, WebSocketException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.errors import ApiError
from src.core.logging_setup import bind_log_context
from src.core.observability import note_active_player
from src.core.security import InvalidTokenError, decode_user_token
from src.db import redis as redis_module
from src.db.session import get_db, get_session_factory
from src.models.user import User
from src.services import product_metrics

# The scheme for extracting the token from the Authorization: Bearer header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

WS_TICKET_PREFIX = "ws_ticket:"


async def user_from_token(db: AsyncSession, token: str) -> User | None:
    """
    The user by JWT or None. The token is valid only while its version matches
    users.token_version: a password change and "log out on all devices" increase it.
    """
    try:
        user_id, version = decode_user_token(token)
    except InvalidTokenError:
        return None
    user = await db.get(User, user_id)
    if user is None or user.token_version != version:
        return None
    return user


async def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db),
        session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> User:
    """
    The dependency of "logged-in only" HTTP endpoints: the player by the token from the Authorization: Bearer header, otherwise
    401 not_authenticated. It also marks the player as active for the day: a counter in Redis for the metric
    regence_active_players_today and an event in product_events (at most once a day).
    """
    user = await user_from_token(db, token)
    if user is None:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "not_authenticated", headers={"WWW-Authenticate": "Bearer"})
    bind_log_context(user_id=user.id)  # every log line of this request carries the player (src/core/logging_setup.py)
    await note_active_player(user.id)  # for the "CPU per active player" metric (task 23.3)
    await product_metrics.mark_active(session_factory, user.id)  # D1/D7/D30 retention (task 23.5)
    return user


async def get_current_user_ws(
        ticket: str = Query(..., max_length=128, description="One-time ticket from POST /auth/ws-ticket"),
        session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> User:
    """
    The WebSocket dependency: login by a one-time ticket from the address parameter ?ticket=. A wrong, expired or already
    used ticket - closing with code 1008; Redis unavailable - 1011.

    A JWT in the WebSocket address would end up in the uvicorn and proxy access logs and would stay valid there until the end
    of its
    lifetime. Instead the client gets over HTTP (token in the header) a one-time ticket for WS_TICKET_TTL_S seconds;
    GETDEL guarantees that the ticket works exactly once. In Redis under the key ws_ticket:<ticket> lies
    "player id:token version".

    The user is read in a short session that is closed immediately: a dependency with get_db
    would hold a pool connection for as long as the WebSocket is open. The returned object
    is detached from the session, its fields are already loaded.
    """
    rejected = WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired ticket")
    try:
        raw = await redis_module.redis_client.getdel(f"{WS_TICKET_PREFIX}{ticket}")
    except Exception as exc:
        raise WebSocketException(code=status.WS_1011_INTERNAL_ERROR, reason="Ticket store unavailable") from exc
    if not raw:
        raise rejected

    user_id_str, _, version_str = str(raw).partition(":")
    async with session_factory() as db:
        user = await db.get(User, int(user_id_str))

    # The tokens were revoked between the ticket being issued and the connection - the ticket is invalid too.
    if user is None or str(user.token_version) != version_str:
        raise rejected
    return user
