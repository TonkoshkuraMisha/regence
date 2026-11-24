# --- FILE: src/services/legal.py ---
"""
Consent to the terms at registration (task 23.1): which version of the documents ("Terms of use", "Community Rules" and
"Privacy", client pages /terms, /rules and /privacy) is in force now and how the player's consent is recorded.

TERMS_VERSION is the edition date of the documents. It changes with every edit of their meaning; players with an older mark
(users.terms_version) are visible in the database so that consent can be requested again if needed. Consent is stored in
users.terms_version and users.terms_accepted_at; archive players from PGN and bots do not have it (NULL). The check is
enabled by
the REQUIRE_TERMS_CONSENT setting (src/core/config.py): tests and closed environments may disable it.
"""

from datetime import UTC, datetime

from src.core.errors import ApiError
from src.models.user import User

# The edition of the documents the new player agrees to (a date in the format YYYY-MM-DD).
TERMS_VERSION = "2026-11-24"


def require_consent(accepted: bool, required: bool) -> None:
    """Registration refusal without consent (400 terms_not_accepted) if the check is enabled by the setting."""
    if required and not accepted:
        raise ApiError(400, "terms_not_accepted")


def record_consent(user: User, accepted: bool, now: datetime | None = None) -> None:
    """Records the consent mark in the new player; without consent (check disabled) the fields stay empty."""
    if not accepted:
        return
    user.terms_version = TERMS_VERSION
    user.terms_accepted_at = now or datetime.now(UTC)
