"""
Passwords and login tokens.

* A password is stored only as a bcrypt hash (users.hashed_password). Bots and archived players have instead of a hash
  a marker that matches no password - one cannot log in as them.
* The access token is a JWT signed with SECRET_KEY: sub - the player id (a name can be changed, an id cannot), ver - the token
version
  (users.token_version). A password change and "log out everywhere" increase the version, and all tokens issued earlier stop
  being accepted (the check is src/api/deps.user_from_token). The lifetime is ACCESS_TOKEN_EXPIRE_MINUTES.

Long login (a refresh token in a cookie) - src/services/auth_sessions.py.
"""

from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext

from src.core.config import settings

# Password hashing: the bcrypt algorithm (the passlib library).
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Checks the password against the hash from users.hashed_password.

    A value that passlib does not recognise as a hash (the marker of bots and archived players) matches no
    password: the function returns False and does not raise, - otherwise an attempt to log in as a bot would give a 500 error.
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    """A bcrypt hash for a new password - only it is stored in the database."""
    return pwd_context.hash(password)


class InvalidTokenError(Exception):
    """The token is not signed by us, has expired or has an old format."""


def create_user_token(user, expires_delta: timedelta | None = None) -> str:
    """
    A user JWT: sub - the id (a name could be changed, an id cannot), ver - the token version,
    by which all previously issued tokens are revoked.
    """
    return create_access_token({"sub": str(user.id), "ver": int(user.token_version or 0)}, expires_delta)


def decode_user_token(token: str) -> tuple[int, int]:
    """(user_id, token_version) from the token; InvalidTokenError for foreign, expired and old tokens."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(str(exc)) from exc
    subject, version = payload.get("sub"), payload.get("ver")
    # Old-format tokens (sub = user name, without ver) are not accepted: log in again.
    if not isinstance(subject, str) or not subject.isdigit() or not isinstance(version, int):
        raise InvalidTokenError("unsupported token format")
    return int(subject), version


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    Signs a JWT with the data fields and an expiry exp: expires_delta, and without it -
    ACCESS_TOKEN_EXPIRE_MINUTES. Player tokens are issued by create_user_token; tests call this function directly.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt
