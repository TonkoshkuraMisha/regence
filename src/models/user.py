"""
A player (the users table). The same table holds bots and archived players from PGN - they have is_bot and no username_key.

What is stored: the name and the case-insensitive name key, the password hash and the token version (src/core/security.py),
an optional confirmed e-mail, four ratings by time-control categories and the game counters for them
(src/services/rating.py), the ladder rating and the puzzle solver rating, anti-cheat flags (trust_factor, is_cheater -
src/services/anticheat.py), the moderator role, interface settings (language, theme, avatar), the country for conferences
(src/services/conferences.py). When an account is deleted the row is not erased but anonymised
(src/services/account.py).
"""

from datetime import datetime
from typing import Literal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base, one_of

# Who can write direct messages to the player (src/services/direct_messages.py, POLICIES).
DM_POLICIES = ("all", "following", "nobody")

RatingCategory = Literal["bullet", "blitz", "rapid", "classical"]
RATING_CATEGORIES: tuple[RatingCategory, ...] = ("bullet", "blitz", "rapid", "classical")


class User(Base):
    """
    A users table record: a live player, a bot or an archived player from PGN. What is in which fields - in the module
    description above.
    """
    __tablename__ = "users"
    __table_args__ = (one_of("users", "dm_policy", DM_POLICIES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    # The normalised name (casefold) of accounts that log in by password: case-insensitive
    # uniqueness ("Misha" and "misha" are one account) and login in any case. For archived players
    # from PGN and bots it is NULL: their names from game headers can differ only by case,
    # and a unique index does not restrict NULL.
    username_key: Mapped[str | None] = mapped_column(String(50), unique=True, index=True, nullable=True)
    # A bcrypt hash (src/core/security.py). For bots and archived players - a marker that is not a hash
    # ("!historical_bot_no_login!" - src/api/bots.py, "!historical_archive_no_login!" - src/db/seed.py): one cannot log in
    # as them; by the second marker "Watch" and player search tell archived players apart.
    hashed_password: Mapped[str] = mapped_column(String)
    # The token version: part of the JWT and checked on every verification. An increase (password change,
    # "log out on all devices") invalidates all tokens issued earlier.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # The account was deleted at the player's request (task 17.5): the name is replaced by deleted_<id>, the password is
    # unusable, personal data
    # is erased; games stay with the opponents without their name.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The player asked to delete the account (task 23.1): the account is closed at once (no login, hidden from others) and is
    # anonymised after the grace period (ACCOUNT_DELETION_GRACE_DAYS); logging in with the password during that period can
    # restore it (src/services/account.py). The index serves the daily purge.
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Kid mode (task 23.1, src/services/kid_mode.py): no free-text chat, messages or feed. Turned on at registration for
    # players under 16 (with a guardian's consent) or by the player in the settings. kid_guardian_hash is the bcrypt hash of
    # the guardian code: when set, only that code turns kid mode off.
    kid_mode: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    kid_guardian_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    # The invitation the player registered with (task 26.2, src/services/beta.py): partner links of clubs and bloggers show
    # how many of the people who came through them started to play. NULL - registered without a code or before 25.11.2026.
    # use_alter: invites.created_by points back at users, so this key is created after both tables (no table order cycle).
    invite_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("invites.id", ondelete="SET NULL", use_alter=True, name="users_invite_id_fkey"),
        nullable=True, index=True)
    # The confirmed e-mail (task 17.5) - optional; needed for password reset. Only a confirmed one is stored:
    # an address that has not been confirmed yet lives in a one-time link (EmailToken), so someone else's address cannot be
    # taken this way.
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True, nullable=True)
    # Consent to the terms at registration (task 23.1, src/services/legal.py): the edition of the documents and the moment of
    # consent.
    # NULL for archived players from PGN, bots and accounts created before consent existed.
    terms_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # The ELO rating separately for each time-control category (as on chess.com and
    # lichess.org) - there is no single "general" rating any more, bullet/blitz/rapid/classical are not
    # comparable with each other. The category is determined by the game's base_time_ms/increment_ms,
    # see src.services.rating.classify_time_control.
    bullet_rating: Mapped[int] = mapped_column(Integer, default=1200, server_default="1200", nullable=False)
    blitz_rating: Mapped[int] = mapped_column(Integer, default=1200, server_default="1200", nullable=False)
    rapid_rating: Mapped[int] = mapped_column(Integer, default=1200, server_default="1200", nullable=False)
    classical_rating: Mapped[int] = mapped_column(Integer, default=1200, server_default="1200", nullable=False)

    # The number of rated games played in each category - determines the ELO K-factor
    # (for beginners the rating moves faster). Stored as a counter rather than via COUNT(*) over
    # games on every game finish.
    bullet_games_played: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    blitz_games_played: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    rapid_games_played: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    classical_games_played: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    # The club ladder (task 10.4): a separate rating in games with bots without engine hints and
    # takebacks. The beaten rungs are the table ladder_beaten (src/models/ladder.py), the current one is computed by
    # src/services/ladder.py.
    ladder_rating: Mapped[int] = mapped_column(Integer, default=1000, server_default="1000", nullable=False)
    ladder_games: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # The puzzle solver rating (task 13.1) is a separate category, it does not affect game ratings.
    puzzle_rating: Mapped[int] = mapped_column(Integer, default=1500, server_default="1500", nullable=False)
    puzzle_games: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # Personal records of the timed mode (task 13.3): puzzles solved in 3 and in 5 minutes.
    puzzle_best_3: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    puzzle_best_5: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    # A historical bot (a playable AI) or an archived historical player (games from PGN,
    # can be viewed but not played) - not a real registered player, outside the leaderboard.
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    # Anti-cheat (src/services/anticheat.py): the trust factor starts at 100 and decreases with penalties for a "machine"
    # move rhythm; below anticheat.CHEATER_TRUST_THRESHOLD (30) the is_cheater flag is set and a request
    # to a moderator is created. Only a moderator can remove or confirm the flag (src/services/moderation.py).
    is_cheater: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    trust_factor: Mapped[int] = mapped_column(Integer, default=100)
    # Moderation (task 17.4): the moderator role (scripts/make_moderator.py) and chat disabled until a moment.
    is_moderator: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    chat_banned_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Languages (task 17.7): the interface language is stored in the profile (moves between devices) and the "translation
    # helper" mode - the "Suggest a text fix" button.
    language: Mapped[str | None] = mapped_column(String(2), nullable=True)
    translation_helper: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    # Appearance (task 18.3): the chosen theme set (a code from frontend/src/config/themePresets.ts) - moves between
    # devices; a guest keeps it in the browser.
    theme_preset: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # An avatar (task 18.4) from the own set: the "Lewis" piece and a background colour, for example "wN-3"; none - by name.
    avatar: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Who can write direct messages (task 30.1): all | following (only those I follow) | nobody.
    dm_policy: Mapped[str] = mapped_column(String(16), default="all", server_default="all", nullable=False)
    # Conference (task 33.6, src/services/conferences.py): the country the player themselves set in the profile (an ISO code
    # 3166-1 alpha-2), and the season "YYYY-MM" in which they last changed the conference (one change per season).
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    country_season: Mapped[str | None] = mapped_column(String(7), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def rating_for(self, category: RatingCategory) -> int:
        """The player's rating in a time-control category (the column <category>_rating)."""
        return getattr(self, f"{category}_rating")

    def games_played_for(self, category: RatingCategory) -> int:
        """The number of rated games in a category (the column <category>_games_played) - the K-factor depends on it."""
        return getattr(self, f"{category}_games_played")


# Profile, registration, player search and reports look up the name case-insensitively (lower(username)): without an index on
# this
# expression every such query read the whole table (database audit 29.1).
Index("ix_users_username_lower", func.lower(User.username))
