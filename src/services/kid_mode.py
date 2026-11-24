# --- FILE: src/services/kid_mode.py ---
"""
Kid mode (task 23.1): what a player in kid mode may not do and how the mode is turned on and off. The rules follow two
public patterns: Lichess kid mode (no chat, messages or forums) and Chess.com Safe Mode / ChessKid (only preset phrases
in the game chat).

Who is in kid mode: users.kid_mode. Registration turns it on for a player under 16 (the owner's decision: the site is for
16+, younger players only in kid mode with a guardian's consent, src/api/auth.py); any player may turn it on in the settings
(src/api/account.py). users.kid_guardian_hash keeps the hash of the guardian code: when it is set, only that code turns
the mode off. Without it, the account password does.

What the mode changes (each check sits where the action is; the codes are in src/core/errors.py):
- the game chat (src/api/websockets.py): free text is refused in a game where either player is in kid mode
  (chat_kid_mode); preset phrases (codes, translated by the client) still work - the ChessKid pattern;
- direct messages (src/services/direct_messages.py): a player in kid mode does not write (dm_kid_mode) and cannot be
  written to (dm_closed, the same answer as a closed setting); the whole /messages section answers dm_kid_mode;
- the feed (src/services/feed.py, src/api/feed.py): no posts, comments or likes (feed_kid_mode); the player's own posts
  and comments are not shown to others while the mode is on;
- the shared study room chat (src/api/study.py): refused (chat_kid_mode);
- the public profile (src/api/profile.py): the country is not shown, and the profile carries kid_mode so the client
  hides the "Message" button.
Playing, puzzles, lessons, tournaments and arenas are unchanged: the openness rule (CLAUDE.md, invariant 7) holds.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.core.errors import DomainError
from src.core.security import get_password_hash
from src.models.user import User

# Length of the guardian code: short enough to remember, long enough not to be guessed in the few attempts the
# password limiter allows (RATE_LIMIT_LOGIN_FAILURES_PER_ACCOUNT).
GUARDIAN_CODE_MIN_LENGTH = 4
GUARDIAN_CODE_MAX_LENGTH = 32


def is_kid(user: User | None) -> bool:
    """Whether the player is in kid mode; a guest or a missing player is not."""
    return bool(user is not None and user.kid_mode)


def free_chat_refusal(players: Iterable[User | None]) -> str | None:
    """
    The refusal code for free text in a chat shared by these players: chat_kid_mode when any of them is in kid mode,
    otherwise None. A kid neither writes free text nor reads it from the opponent.
    """
    return "chat_kid_mode" if any(is_kid(p) for p in players) else None


def ensure_not_kid(user: User | None, code: str) -> None:
    """A DomainError with the given code when the player is in kid mode (a section closed to kids)."""
    if is_kid(user):
        raise DomainError(code)


def enable(user: User, guardian_code: str | None) -> None:
    """
    Turns kid mode on. With a guardian code, only that code turns it off later (the code is stored as a bcrypt hash, like a
    password). Turning it on again with a new code replaces the old one; without a code the old one is kept.
    """
    user.kid_mode = True
    if guardian_code:
        user.kid_guardian_hash = get_password_hash(guardian_code)


def disable(user: User) -> None:
    """Turns kid mode off and forgets the guardian code (the caller has already checked the code or the password)."""
    user.kid_mode = False
    user.kid_guardian_hash = None
