"""
The format of registration and of a response with a player's data, the name rules.

The name: from USERNAME_MIN_LENGTH to USERNAME_MAX_LENGTH characters, only Latin or Cyrillic letters, digits, "_" and
"-"; mixing alphabets is not allowed (otherwise "Morphy" with a Cyrillic first letter would look like a foreign name). Names
are compared
case-insensitively - username_key. Reserved names (routes, bots, champions) are checked by src/api/auth.py.
"""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.errors import validation_error
from src.services.kid_mode import GUARDIAN_CODE_MAX_LENGTH, GUARDIAN_CODE_MIN_LENGTH
from src.services.onboarding import Experience, StrengthBand

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 30
# Ukrainian Cyrillic letters by code point (escapes keep the source free of Cyrillic): A-Shch, soft sign, Yu, Ya, Ye,
# I, Yi, Ghe-with-upturn and their lowercase forms. Russian-only letters (yo, hard sign, yery, e) are not allowed.
_UK_LETTERS = "\u0410-\u0429\u042c\u042e\u042f\u0404\u0406\u0407\u0490\u0430-\u0449\u044c\u044e\u044f\u0454\u0456\u0457\u0491"
_USERNAME_RE = re.compile(rf"[A-Za-z0-9{_UK_LETTERS}_-]+")
_LATIN_RE = re.compile(r"[A-Za-z]")
_CYRILLIC_RE = re.compile(rf"[{_UK_LETTERS}]")


def username_key(username: str) -> str:
    """A key for comparing names case-insensitively (casefold); stored in users.username_key and unique in the database."""
    return username.strip().casefold()


def validate_username(value: str) -> str:
    """
    The name rules at registration. A whitelist of characters cuts off spaces, invisible and
    control characters, and the ban on mixing alphabets - forgeries like "Morphy" with a Cyrillic first letter.
    The name must contain at least one letter. A violation is a validation error with a code from src/core/errors.py
    (username_invalid_chars, username_mixed_scripts, username_no_letters). The same rules apply to the names of workshop
    opponents (src/api/personalities.py).
    """
    if not _USERNAME_RE.fullmatch(value):
        raise validation_error("username_invalid_chars")
    if _LATIN_RE.search(value) and _CYRILLIC_RE.search(value):
        raise validation_error("username_mixed_scripts")
    if not any(ch.isalpha() for ch in value):
        raise validation_error("username_no_letters")
    return value


# The password length (registration, change and reset - src/api/auth.py, src/api/account.py): at least 8 characters; the upper
# bound is so as not to hash megabyte-long "passwords" (bcrypt only takes 72 bytes into account anyway). The client checks
# the lower one in advance - frontend/src/config/passwordRules.ts.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


class UserCreate(BaseModel):
    """Registration data (POST /auth/register): the name, the password and optional answers and an invite code."""
    username: str = Field(
        ..., min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH, description="Unique username",
    )
    password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH, description="Strong password")
    # The first login (task 17.8): optional answers for the starting rating (src/services/onboarding.py).
    experience: Experience | None = None
    strength: StrengthBand | None = None
    # An invite code (task 24.4): required when registration is closed (REGISTRATION_INVITE_ONLY).
    invite_code: str | None = Field(None, max_length=64)
    # Consent to the terms (task 23.1): required with REQUIRE_TERMS_CONSENT, otherwise 400 terms_not_accepted.
    accept_terms: bool = False
    # A player under 16 (task 23.1, the owner's decision: the site is for 16+): only in kid mode, with a parent's or
    # guardian's consent and a guardian code that alone turns kid mode off (src/services/kid_mode.py).
    under_16: bool = False
    guardian_consent: bool = False
    guardian_code: str | None = Field(None, min_length=GUARDIAN_CODE_MIN_LENGTH, max_length=GUARDIAN_CODE_MAX_LENGTH)

    @field_validator("username")
    @classmethod
    def _check_username(cls, value: str) -> str:
        return validate_username(value)


class UserResponse(BaseModel):
    """
    The registration response - the data of the just created player. The password hash and the numeric trust factor
    (users.trust_factor) are not in it; the is_cheater flag is visible to the player about themselves.
    """
    id: int
    username: str
    bullet_rating: int
    blitz_rating: int
    rapid_rating: int
    classical_rating: int
    is_cheater: bool
    created_at: datetime

    # from_attributes: the response is assembled directly from the User model object.
    model_config = ConfigDict(from_attributes=True)
