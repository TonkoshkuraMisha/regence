# --- FILE: src/api/account.py ---
"""
Account (/account; tasks 17.5, 23.1, 24.3): export of one's own data and games, account deletion with a grace period
(src/services/account.py; restoring is POST /auth/restore), kid mode (src/services/kid_mode.py), e-mail binding and
password reset via a link from an e-mail (src/services/email_links.py, sending - src/services/mailer.py).

Binding, deletion and kid mode require the password (turning kid mode off - the guardian code when one is set); failed
attempts are counted by the same counter as failed logins. E-mails
are limited by the recipient address and by the address of the request sender (RATE_LIMIT_EMAIL_*). Address confirmation and
password
reset work without logging in - by a one-time token from the e-mail (table email_tokens).
"""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.api.rate_limit import client_ip, enforce_rate_limit, ensure_below_limit, record_attempt
from src.core.config import settings
from src.core.errors import ApiError
from src.core.security import verify_password
from src.db.session import get_db
from src.models.user import User
from src.schemas.user import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, username_key
from src.services import account as service
from src.services import email_links, kid_mode

router = APIRouter(prefix="/account", tags=["Account"])


class DeleteAccountRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)


# A simple check of the address shape; the real check is the e-mail with a link.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
Language = Literal["en", "uk"]


class EmailRequest(BaseModel):
    email: str = Field(..., max_length=254, pattern=EMAIL_PATTERN)
    password: str = Field(..., min_length=1, max_length=128)
    language: Language = "en"


class TokenRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)


class ResetRequest(BaseModel):
    email: str = Field(..., max_length=254, pattern=EMAIL_PATTERN)
    language: Language = "en"


class ResetConfirm(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)
    new_password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class KidModeRequest(BaseModel):
    """
    Turning kid mode on or off (src/services/kid_mode.py). On: the account password, and optionally a guardian code that
    will be needed to turn it off. Off: the guardian code if one is set, otherwise the account password.
    """
    enabled: bool
    password: str | None = Field(None, max_length=128)
    guardian_code: str | None = Field(None, min_length=kid_mode.GUARDIAN_CODE_MIN_LENGTH,
                                      max_length=kid_mode.GUARDIAN_CODE_MAX_LENGTH)


async def _check_secret(user: User, secret: str, hashed: str, wrong_code: str) -> None:
    """A password or guardian code check; failed attempts fall under the same per-account limit as failed logins."""
    account = f"account:{user.username_key or username_key(user.username)}"
    await ensure_below_limit(
        "login_failures", account,
        settings.RATE_LIMIT_LOGIN_FAILURES_PER_ACCOUNT, settings.RATE_LIMIT_LOGIN_FAILURES_WINDOW_S,
        "too_many_password_attempts",
    )
    if not verify_password(secret, hashed):
        await record_attempt("login_failures", account, settings.RATE_LIMIT_LOGIN_FAILURES_WINDOW_S)
        raise ApiError(status.HTTP_400_BAD_REQUEST, wrong_code)


async def _check_password(user: User, password: str) -> None:
    """Password confirmation; failed attempts fall under the same limit as login."""
    await _check_secret(user, password, user.hashed_password, "wrong_current_password")


async def _limit_mail(request: Request, email: str) -> None:
    """E-mails with links: at most N per address and per IP within the window - so that we cannot be used to flood someone
    else's mailbox."""
    window = settings.RATE_LIMIT_EMAIL_WINDOW_S
    await enforce_rate_limit("mail", f"ip:{client_ip(request)}", settings.RATE_LIMIT_EMAIL_PER_IP, window,
                             "too_many_emails")
    await enforce_rate_limit("mail", f"to:{email_links.normalize(email)}", settings.RATE_LIMIT_EMAIL_PER_ADDRESS,
                             window, "too_many_emails")


@router.get("/export")
async def export_my_data(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """All of the player's data as one JSON file (GDPR, right to portability); only one's own, login required."""
    data = await service.export_data(db, user)
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="regence-{user.id}.json"'})


@router.get("/games.pgn", response_class=PlainTextResponse)
async def export_my_games_pgn(offset: int = Query(0, ge=0), user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    """
    One's own finished games as a single PGN file (task 24.3) - to open in any chess program. Per request
    at most account.GAMES_PGN_LIMIT games, from oldest to newest; the total is in the X-Total-Count header, further pages -
    the offset parameter.
    """
    text, total = await service.games_pgn(db, user, offset)
    return PlainTextResponse(text, media_type="application/x-chess-pgn", headers={
        "Content-Disposition": f'attachment; filename="regence-games-{user.id}.pgn"', "X-Total-Count": str(total),
    })


@router.post("/delete")
async def delete_my_account(
        payload: DeleteAccountRequest,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """
    Deletion of one's own account with password confirmation (src/services/account.py). The account is closed and the
    player logged out at once; after ACCOUNT_DELETION_GRACE_DAYS the data is erased and the name anonymised, games stay with
    the opponents. Until then logging in with the password offers to restore it. Returns delete_after (ISO time). While a
    game is in progress - refusal 409 account_in_game.
    """
    await _check_password(user, payload.password)
    when = await service.request_deletion(db, user)
    return {"delete_after": when.isoformat()}


@router.post("/kid-mode")
async def set_kid_mode(payload: KidModeRequest, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """
    Kid mode on or off (src/services/kid_mode.py). On - with the account password and an optional guardian code; off - with
    the guardian code when one was set (400 guardian_code_wrong), otherwise with the password. Returns the new state.
    A set guardian code is never replaced by the password: to change it, turn the mode off with the old code first.
    """
    if payload.enabled:
        if user.kid_guardian_hash is None:
            await _check_password(user, payload.password or "")
            kid_mode.enable(user, payload.guardian_code)
    elif user.kid_guardian_hash is not None:
        await _check_secret(user, payload.guardian_code or "", user.kid_guardian_hash, "guardian_code_wrong")
        kid_mode.disable(user)
    else:
        await _check_password(user, payload.password or "")
        kid_mode.disable(user)
    await db.commit()
    return {"kid_mode": user.kid_mode, "kid_guardian_code": user.kid_guardian_hash is not None}


@router.post("/email", status_code=status.HTTP_202_ACCEPTED)
async def request_email(
        payload: EmailRequest, request: Request,
        user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Bind an e-mail: an e-mail with a confirmation link; the address reaches the profile only via the link."""
    await _check_password(user, payload.password)
    await _limit_mail(request, payload.email)
    await email_links.request_verification(db, user, payload.email, payload.language)


@router.post("/email/remove", status_code=status.HTTP_204_NO_CONTENT)
async def remove_email(
        payload: DeleteAccountRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Unbind the e-mail (with password): afterwards the password cannot be reset by e-mail."""
    await _check_password(user, payload.password)
    user.email = None
    await db.commit()


@router.post("/email/verify")
async def verify_email(payload: TokenRequest, db: AsyncSession = Depends(get_db)):
    """Link from the e-mail (no login - by the token in it): the address is confirmed and written to the profile
    (users.email)."""
    user = await email_links.confirm_verification(db, payload.token)
    return {"email": user.email}


@router.post("/password-reset", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(payload: ResetRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    An e-mail with a reset link (no login). The response is the same whether such an address exists or not, so that it cannot
    be used to
    find out whether an address is bound to someone's account.
    """
    await _limit_mail(request, payload.email)
    await email_links.request_reset(db, payload.email, payload.language)


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_password_reset(payload: ResetConfirm, db: AsyncSession = Depends(get_db)):
    """New password via the link from the e-mail: all sessions and other reset links are revoked."""
    await email_links.confirm_reset(db, payload.token, payload.new_password)
