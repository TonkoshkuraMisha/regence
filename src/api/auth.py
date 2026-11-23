"""
Registration and login (/auth).

* Registration: username rules - src/schemas/user.py; route names, bot names and champion names are reserved
  (RESERVED_USERNAMES, reserved_bot_usernames). With REGISTRATION_INVITE_ONLY a valid invite code is required
  (src/services/beta.py). Answers to two optional questions give the starting rating (src/services/onboarding.py).
* Login: the password is checked against the hash (src/core/security.py). Brute force is limited twice - all attempts from one
address and
  failed attempts per account (settings RATE_LIMIT_LOGIN_*). For a non-existent name a dummy
  password is checked, so that the response time does not reveal whether such an account exists.
* Session: a short access token in the response and a refresh token in an HttpOnly cookie (src/services/auth_sessions.py);
  /refresh issues a new access token, /logout ends the session on this device, /logout-all and a password change
  revoke all tokens and close the player's open WebSockets.
* /ws-ticket - a one-time ticket for connecting a WebSocket (see src/api/deps.py).
"""

import secrets

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import WS_TICKET_PREFIX, get_current_user
from src.api.rate_limit import client_ip, enforce_rate_limit, ensure_below_limit, record_attempt
from src.core.config import settings
from src.core.errors import ApiError, error_payload
from src.core.security import create_user_token, get_password_hash, verify_password
from src.db import redis as redis_module
from src.db.session import get_db
from src.models.user import RATING_CATEGORIES, User
from src.schemas.user import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, UserCreate, UserResponse, username_key
from src.services import auth_sessions, beta, legal, product_metrics
from src.services.onboarding import starting_rating

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Names that coincide with routes (/profile/me, /profile/leaderboard ...) or impersonate
# the site administration. Compared case-insensitively.
RESERVED_USERNAMES = frozenset({
    "me", "leaderboard", "games", "matchmaking", "profile", "auth", "api", "ws",
    "admin", "administrator", "moderator", "support", "system", "root",
    "regence", "michess", "bot", "guest", "anonymous", "null", "undefined",
})

# A hash for comparison when the user does not exist: the response takes as long as with
# a wrong password, and by timing one cannot tell whether the account exists.
_DUMMY_PASSWORD_HASH = get_password_hash("timing-equalizer-not-a-real-password")


def _is_reserved(username: str) -> bool:
    """
    The name cannot be taken: it coincides (case-insensitively) with a route or a service word, with a bot or archetype id
    or with a champion name from the archive. The same check is used for workshop opponent names
    (src/api/personalities.py).
    """
    from src.api.bots import reserved_bot_usernames
    from src.db.seed import get_champion_meta

    key = username_key(username)
    return (
        key in RESERVED_USERNAMES
        or key in reserved_bot_usernames()
        or get_champion_meta(username) is not None  # a champion profile would shadow the account
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_in: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Registration (without login): creates a row in users and returns the data of the new player; the token is issued by a
    separate
    request /auth/login. Order of checks: registration limit per address -> consent to the terms (terms_not_accepted,
    400; task 23.1) -> invite code (when registration is
    closed) -> reserved name -> name availability case-insensitively. Refusals - codes
    too_many_registrations (429), registration_invite_* (403), username_reserved and username_taken (400).
    """
    await enforce_rate_limit(
        "register", f"ip:{client_ip(request)}",
        settings.RATE_LIMIT_REGISTER_PER_IP, settings.RATE_LIMIT_REGISTER_WINDOW_S,
        "too_many_registrations",
    )

    legal.require_consent(user_in.accept_terms, settings.REQUIRE_TERMS_CONSENT)

    # Closed registration (task 24.4): without an invite code we go no further - and do not reveal whether names are taken.
    invite_code = beta.normalize_code(user_in.invite_code)
    if settings.REGISTRATION_INVITE_ONLY:
        if not invite_code:
            raise ApiError(status.HTTP_403_FORBIDDEN, "registration_invite_required")
        if not await beta.invite_usable(db, invite_code):
            raise ApiError(status.HTTP_403_FORBIDDEN, "registration_invite_invalid")

    if _is_reserved(user_in.username):
        raise ApiError(status.HTTP_400_BAD_REQUEST, "username_reserved")

    key = username_key(user_in.username)
    # username_key exists for accounts with a password; archived players from PGN and bots do not have it,
    # so with them we also compare by the name itself.
    result = await db.execute(select(User.id).where(or_(
        User.username_key == key,
        func.lower(User.username) == user_in.username.lower(),
    )))
    if result.first() is not None:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "username_taken")

    # Starting rating from the answers at registration (task 17.8) - in all game categories and in puzzles. Without answers -
    # the model defaults (game 1200, puzzles 1500).
    ratings: dict[str, int] = {}
    if user_in.experience is not None or user_in.strength is not None:
        start = starting_rating(user_in.experience, user_in.strength)
        ratings = {f"{c}_rating": start for c in (*RATING_CATEGORIES, "puzzle")}
    new_user = User(
        username=user_in.username,
        username_key=key,
        hashed_password=get_password_hash(user_in.password),
        **ratings,
    )
    legal.record_consent(new_user, user_in.accept_terms)
    db.add(new_user)
    # The code is consumed in the same transaction as account creation. With open registration the code is optional:
    # a valid one is counted (it shows who came by invitation), an invalid one does not interfere.
    if not await beta.consume_invite(db, invite_code) and settings.REGISTRATION_INVITE_ONLY:
        await db.rollback()  # the code was exhausted or revoked between the check and consumption
        raise ApiError(status.HTTP_403_FORBIDDEN, "registration_invite_invalid")
    try:
        await db.commit()
    except IntegrityError:
        # Parallel registration of the same name (in another case) - the unique index in the DB.
        await db.rollback()
        raise ApiError(status.HTTP_400_BAD_REQUEST, "username_taken") from None
    await db.refresh(new_user)
    await product_metrics.record_event(db, new_user.id, product_metrics.REGISTERED)
    await db.commit()

    return new_user


async def _find_login_user(db: AsyncSession, username: str) -> User | None:
    """A record for login: first the exact name, then case-insensitively (username_key)."""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if user is None:
        # Login in any case: "misha" will find the account "Misha".
        result = await db.execute(select(User).where(User.username_key == username_key(username)))
        user = result.scalars().first()
    return user


@router.post("/login")
async def login(
        request: Request,
        response: Response,
        form_data: OAuth2PasswordRequestForm = Depends(),
        db: AsyncSession = Depends(get_db)
):
    """
    Login by name and password (OAuth2 form: fields username and password). Returns a short access token and sets
    the long-login refresh cookie (src/services/auth_sessions.py). A wrong name or password - the same response
    401 login_failed.

    Password guessing is limited twice: all attempts from one IP (brute force across many accounts)
    and failed attempts per account (brute force of one password from many addresses).
    """
    await enforce_rate_limit(
        "login", f"ip:{client_ip(request)}",
        settings.RATE_LIMIT_LOGIN_PER_IP, settings.RATE_LIMIT_LOGIN_WINDOW_S,
        "too_many_login_attempts",
    )
    account = f"account:{username_key(form_data.username)}"
    await ensure_below_limit(
        "login_failures", account,
        settings.RATE_LIMIT_LOGIN_FAILURES_PER_ACCOUNT, settings.RATE_LIMIT_LOGIN_FAILURES_WINDOW_S,
        "account_login_locked",
    )

    user = await _find_login_user(db, form_data.username)
    password_ok = verify_password(form_data.password, user.hashed_password if user else _DUMMY_PASSWORD_HASH)

    if user is None or not password_ok:
        await record_attempt("login_failures", account, settings.RATE_LIMIT_LOGIN_FAILURES_WINDOW_S)
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "login_failed", headers={"WWW-Authenticate": "Bearer"})

    access_token = create_user_token(user)
    auth_sessions.set_refresh_cookie(response, await auth_sessions.issue(user.id, user.token_version or 0))

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.post("/refresh")
async def refresh_session(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """
    A new short access token from the refresh cookie (task 17.5): the client calls it on page load and shortly before
    the token expires. 401 - there is no session or it was revoked (logout, "log out everywhere", password change, account
    deletion).
    """
    token = auth_sessions.read_refresh_cookie(request.cookies)
    found = await auth_sessions.lookup(token)
    user = await db.get(User, found[0]) if found else None
    if (token is None or found is None or user is None or user.deleted_at is not None
            or (user.token_version or 0) != found[1]):
        # The response is built here, not by an exception: otherwise clearing the revoked cookie would be lost.
        rejected = JSONResponse({"detail": error_payload("not_authenticated")}, status_code=401,
                                headers={"WWW-Authenticate": "Bearer"})
        auth_sessions.clear_refresh_cookie(rejected)
        return rejected
    # The cookie lifetime is extended together with the Redis entry: an active player does not log out on their own.
    auth_sessions.set_refresh_cookie(response, token)
    return {"access_token": create_user_token(user), "token_type": "bearer"}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> Response:
    """Logout on this device: the refresh session is deleted, the cookie is cleared. The client forgets the access token
    itself."""
    await auth_sessions.revoke(auth_sessions.read_refresh_cookie(request.cookies))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    auth_sessions.clear_refresh_cookie(response)
    return response


@router.post("/ws-ticket")
async def issue_ws_ticket(current_user: User = Depends(get_current_user)):
    """
    A one-time ticket for connecting a WebSocket (?ticket=...), valid for WS_TICKET_TTL_S seconds.
    A JWT in the WebSocket address would end up in server and proxy logs. Only for logged-in users; at most
    RATE_LIMIT_WS_TICKETS tickets per minute per player. The ticket is stored in Redis (ws_ticket:<ticket>) and is taken
    on connection (src/api/deps.get_current_user_ws).
    """
    await enforce_rate_limit(
        "ws_ticket", f"user:{current_user.id}", settings.RATE_LIMIT_WS_TICKETS, 60,
        "too_many_reconnects",
    )
    ticket = secrets.token_urlsafe(32)
    await redis_module.redis_client.set(
        f"{WS_TICKET_PREFIX}{ticket}",
        f"{current_user.id}:{current_user.token_version}",
        ex=settings.WS_TICKET_TTL_S,
    )
    return {"ticket": ticket, "expires_in": settings.WS_TICKET_TTL_S}


async def _revoke_all_tokens(db: AsyncSession, user: User) -> None:
    """Revokes all tokens issued to the user and closes their open WebSockets."""
    from src.services.connection_manager import manager

    user.token_version = (user.token_version or 0) + 1
    await db.commit()
    await manager.revoke_sessions(user.id)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_everywhere(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Logout on all devices: all issued tokens (including the current one) stop being valid."""
    await _revoke_all_tokens(db, current_user)


class PasswordChange(BaseModel):
    """Password change: the current password for confirmation and the new one (at least 8 characters)."""
    current_password: str = Field(..., max_length=128)
    new_password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


@router.post("/change-password")
async def change_password(
        payload: PasswordChange,
        response: Response,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """
    Password change. All previously issued tokens are revoked (in case the password is changed because of
    a leak), and the current client gets a new token so that it stays logged in.
    A wrong current password - 400 wrong_current_password; such attempts are counted by the same counter as
    failed logins to the account.
    """
    account = f"account:{current_user.username_key or username_key(current_user.username)}"
    await ensure_below_limit(
        "login_failures", account,
        settings.RATE_LIMIT_LOGIN_FAILURES_PER_ACCOUNT, settings.RATE_LIMIT_LOGIN_FAILURES_WINDOW_S,
        "too_many_password_attempts",
    )
    if not verify_password(payload.current_password, current_user.hashed_password):
        await record_attempt("login_failures", account, settings.RATE_LIMIT_LOGIN_FAILURES_WINDOW_S)
        raise ApiError(status.HTTP_400_BAD_REQUEST, "wrong_current_password")

    current_user.hashed_password = get_password_hash(payload.new_password)
    await _revoke_all_tokens(db, current_user)
    # The previous refresh sessions were revoked together with the token version; this client gets a new one.
    auth_sessions.set_refresh_cookie(response, await auth_sessions.issue(current_user.id, current_user.token_version))
    return {"access_token": create_user_token(current_user), "token_type": "bearer"}
