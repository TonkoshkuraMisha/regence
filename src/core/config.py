# --- FILE: src/core/config.py ---
"""
Application settings: one settings object per process.

Values are read from environment variables and the .env file in the project root (pydantic-settings; a sample with explanations
-
.env.example, production - DEPLOY.md). Each setting below has a default value and a comment saying what it
changes: PostgreSQL and Redis addresses, token lifetime, engine pool size, request limits per endpoint, e-mail,
the beta programme, arenas and conferences. The anti-cheat thresholds are set not here but by constants in
src/services/anticheat.py
(it reads only AC_PREMOVE_MAX_ELAPSED_MS from here).

Startup check: in production (ENVIRONMENT=production) a weak SECRET_KEY, or one taken from the example, stops
the start - this key signs the tokens of all players.
"""

import json
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIN_SECRET_KEY_LENGTH = 32
_WEAK_SECRET_KEYS = {"secret", "changeme", "change_me", "your-secret-key", "test", "dev"}


class Settings(BaseSettings):
    """
    All application settings. A field without a default (POSTGRES_*, SECRET_KEY) is required: without it in the
    environment or .env the process does not start. Environment variable names match the field names (case-sensitively).
    """
    PROJECT_NAME: str = "Regence API"
    # The application version: served by /health and /beta/config, and it is also the release tag in Sentry.
    VERSION: str = "1.2.2"
    API_V1_STR: str = "/api/v1"

    # Conferences whose schedule creates arenas (task 33.4), comma-separated. While there are few players the list can be
    # shortened (for example "central") so as not to split them across the arenas of five time zones.
    ARENA_CONFERENCES: str = "central,western,northern,southern,eastern"
    # The header in which the proxy in front of the server names the visitor's country (task 33.6), for example "CF-IPCountry"
    # at Cloudflare. The country from it is only offered to the player at selection; empty - no address-based hint.
    COUNTRY_HEADER: str = ""

    # "production" enables strict startup checks (SECRET_KEY) and hides /docs.
    ENVIRONMENT: str = "development"

    # CORS: in .env - comma-separated or as a JSON list. In production behind nginx the frontend and the API
    # are on one domain, and CORS is not needed at all.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

    # PostgreSQL: the database address is assembled from these five values (async_database_url below).
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_SERVER: str
    POSTGRES_PORT: int
    POSTGRES_DB: str

    # The database connection pool - per API process (src/db/session.py): permanent connections, how many can be
    # opened beyond them under load, and how many seconds a request waits for a free connection before getting an error.
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT_S: float = 30.0

    # Redis. Short timeouts: rate_limit.py and other calls are designed for fail-open when
    # Redis is unavailable, but without them a hung connection (for example, a container in a restart loop)
    # blocks a request for tens of seconds instead of a quick TCP refusal.
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_CONNECT_TIMEOUT_S: float = 1.0
    REDIS_SOCKET_TIMEOUT_S: float = 1.0
    # Command retries without a pause; the worst wait on failure is (1 + REDIS_RETRIES) timeouts.
    REDIS_RETRIES: int = 1

    # Login tokens (JWT, src/core/security.py): the signing key and algorithm.
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    # The access token is short, the client keeps it in memory; the long login is a refresh token in an httpOnly cookie (17.5).
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    # The Secure flag of the login cookie; by default - only in production (ENVIRONMENT=production).
    COOKIE_SECURE: bool | None = None

    # Anti-cheat. The six settings below are left over from the first version of anti-cheat and are not read anywhere in the
    # code now: the rhythm
    # and trust thresholds are constants in src/services/anticheat.py, and the path to Stockfish is searched by
    # src/services/bots/base.resolve_stockfish_path (the bin/ folder, PATH, standard Linux paths). Changing them is useless.
    AC_BLUR_RATE_HIGH: float = 0.8
    AC_BLUR_RATE_MED: float = 0.5
    AC_MIN_MOVE_TIME_MS: int = 3000
    AC_MAX_MOVE_TIME_MS: int = 8000
    AC_STOCKFISH_PATH: str = "bin/stockfish-windows-x86-64-avx2.exe"
    AC_MAX_CENTIPAWN_LOSS: int = 15
    # The only active anti-cheat setting: the server trusts a premove reported by the client only if it itself
    # saw the move no later than this many milliseconds (anticheat.trusted_premove). Otherwise a dishonest player would mark
    # all moves as premoves and take them out of the rhythm estimate.
    AC_PREMOVE_MAX_ELAPSED_MS: int = 600

    # The lobby (src/services/matchmaker.py): the rating window +-N for a challenge when the client did not send its own
    # bounds;
    # 0 - no limit.
    MATCHMAKING_DEFAULT_RATING_RANGE: int = 0

    # Queueing Celery tasks from the API process (src/services/task_dispatch.py, src/worker/celery_app.py): short
    # timeouts, no publish retries and a pause after a broker failure - an unavailable broker must not delay a game
    # and pile up threads. CELERY_PUBLISH_TIMEOUT_S is how long we wait for the publish itself.
    CELERY_PUBLISH_TIMEOUT_S: float = 3.0
    # Endgame tablebases (task 14.4): in development - the open lichess API; in production - our own tablebase server with the
    # same
    # API (owner's decision: we keep the tables in-house, DEPLOY).
    TABLEBASE_URL: str = "https://tablebase.lichess.ovh/standard"
    # Continuation of the Celery settings: the broker connection timeout and the pause during which, after a broker failure,
    # we do not even try to queue new tasks.
    CELERY_BROKER_CONNECT_TIMEOUT_S: float = 1.0
    CELERY_BROKER_COOLDOWN_S: float = 30.0

    # Observability (src/core/observability.py): Sentry is off while SENTRY_DSN is empty.
    # The share of requests with performance tracing: 0 - errors only.
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0
    # Logs (src/core/logging_setup.py): the format json / text / auto (json in production), the level, an optional file
    # with rotation (empty - console only), its size in MB and the number of copies.
    LOG_FORMAT: str = "auto"
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = ""
    LOG_FILE_MAX_MB: int = 20
    LOG_FILE_BACKUPS: int = 10
    # Client error reports (src/api/client_errors.py): how many to accept from one address per window; anything over is
    # dropped.
    RATE_LIMIT_CLIENT_ERRORS: int = 30
    RATE_LIMIT_CLIENT_ERRORS_WINDOW_S: int = 300
    # Celery worker metrics (src/core/observability.start_worker_metrics_server): the port on which the worker's main process
    # serves /metrics of its processes (engine time in background review and simulations); 0 - do not serve.
    # In production it is set by docker-compose.prod.yml (9101), in development it is off.
    WORKER_METRICS_PORT: int = 0

    # The Stockfish process pool (src/services/engine_pool.py): no more than this many engines in each API process and
    # worker; a request over the limit waits for a free engine this many seconds and then gets the engine_busy refusal.
    ENGINE_POOL_SIZE: int = 2
    ENGINE_ACQUIRE_TIMEOUT_S: float = 10.0

    # Request limits (src/api/rate_limit.py): this many requests per RATE_LIMIT_WINDOW_S seconds window - per player, and
    # without
    # login - per address. The setting name is passed to rate_limit(...) as a string, so a search for "settings.NAME" does not
    # find these
    # settings. RATE_LIMIT_BOT_MOVE - bot moves (/bots/move, /bots/custom-move, /bots/draw-offer,
    # /chess960/*); RATE_LIMIT_POSITION_ANALYSIS - position evaluation, endgame tablebases, "find mate", the opening
    # explorer; RATE_LIMIT_GAME_ANALYSIS - full game review.
    RATE_LIMIT_WINDOW_S: int = 60
    RATE_LIMIT_BOT_MOVE: int = 90
    RATE_LIMIT_POSITION_ANALYSIS: int = 30
    # Without login position analysis is available, but less often: a guest cannot be tied to a game in progress
    RATE_LIMIT_POSITION_ANALYSIS_GUEST: int = 10
    RATE_LIMIT_GAME_ANALYSIS: int = 6
    # Mentor advice for a position (POST /analysis/advice) has its own limit: this is engine work too. The same limit (but with
    # separate counters) bounds the tiered hint (/analysis/hint) and "disagree" (/analysis/dispute).
    RATE_LIMIT_ADVICE: int = 20
    RATE_LIMIT_ADVICE_GUEST: int = 6
    # Move check in a game with the mentor (POST /analysis/check-move): each player move is one request
    RATE_LIMIT_MOVE_CHECK: int = 60
    RATE_LIMIT_MOVE_CHECK_GUEST: int = 20
    # Puzzles (/puzzles/*): move, hint, serving - with a margin for the timed mode. The same number (each section has
    # its own counter) bounds the engine-free sections: exam, feed, messages, library, repertoire, "Watch",
    # trainers, mini-games, teams, joint review, moderation, "Guess the move", players and notifications.
    RATE_LIMIT_PUZZLES: int = 240
    # Daily quotas of the free tier for costly engine work (task 23.3). Off until tiers (25.1) turn
    # on FREE_TIER_LIMITS; basic play (bot moves, puzzles) has no quotas.
    FREE_TIER_LIMITS: bool = False
    FREE_GAME_ANALYSES_PER_DAY: int = 3
    FREE_COACH_REQUESTS_PER_DAY: int = 300

    # The open read-only API (task 24.3, /api/v1/public) and calibration logs: requests per window.
    RATE_LIMIT_PUBLIC_API: int = 60

    # Import of games from lichess and chess.com (task 24.1): open API addresses, per-player limits. MAX_GAMES - games per
    # import, MAX_STORED - how many imported games are stored per player, RATE_LIMIT_GAME_IMPORT - imports
    # per window RATE_LIMIT_GAME_IMPORT_WINDOW_S.
    GAME_IMPORT_LICHESS_URL: str = "https://lichess.org"
    GAME_IMPORT_CHESSCOM_URL: str = "https://api.chess.com"
    GAME_IMPORT_MAX_GAMES: int = 20
    GAME_IMPORT_MAX_STORED: int = 300
    RATE_LIMIT_GAME_IMPORT: int = 10
    RATE_LIMIT_GAME_IMPORT_WINDOW_S: int = 3600

    # Login and registration (src/api/auth.py): all login attempts from one address, failed logins to one account
    # (the same counter is password confirmation when changing the password, e-mail and deleting the account), registrations
    # from an address.
    RATE_LIMIT_LOGIN_PER_IP: int = 20
    RATE_LIMIT_LOGIN_WINDOW_S: int = 60
    RATE_LIMIT_LOGIN_FAILURES_PER_ACCOUNT: int = 10
    RATE_LIMIT_LOGIN_FAILURES_WINDOW_S: int = 900
    RATE_LIMIT_REGISTER_PER_IP: int = 5
    RATE_LIMIT_REGISTER_WINDOW_S: int = 3600
    # The beta programme (task 24.4). REGISTRATION_INVITE_ONLY - registration only by invite code (codes are issued by a
    # moderator); by default registration is open. COMMUNITY_URL - the link to the community channel: empty - not shown.
    REGISTRATION_INVITE_ONLY: bool = False
    # Consent to the "Community Rules" and "Privacy" at registration (task 23.1, src/services/legal.py):
    # without the mark the registration is rejected with the code terms_not_accepted.
    REQUIRE_TERMS_CONSENT: bool = True
    COMMUNITY_URL: str = ""
    # "Report a problem": reports per window from an address (or per player); invite code checks - from an address.
    RATE_LIMIT_FEEDBACK: int = 5
    RATE_LIMIT_FEEDBACK_WINDOW_S: int = 3600
    RATE_LIMIT_INVITE_CHECK: int = 20
    # E-mails with links (e-mail confirmation, password reset): no more than N requests per address and per IP per window.
    RATE_LIMIT_EMAIL_PER_ADDRESS: int = 3
    RATE_LIMIT_EMAIL_PER_IP: int = 10
    RATE_LIMIT_EMAIL_WINDOW_S: int = 3600

    # E-mail (task 17.5). An empty SMTP_HOST - e-mails are not sent but written to the log (development). Any provider
    # (Brevo, Amazon SES, Postmark...) or one's own server - only these variables, the code does not change.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True
    MAIL_FROM: str = "regence <noreply@localhost>"
    # The site address for links in e-mails.
    PUBLIC_BASE_URL: str = "http://localhost:5173"
    EMAIL_VERIFY_TTL_S: int = 24 * 3600
    PASSWORD_RESET_TTL_S: int = 3600

    # One-time WebSocket tickets (the login token does not end up in the WebSocket address - src/api/deps.py): the ticket
    # lifetime
    # in seconds and how many tickets a player can get per minute (the 60 s window is set in src/api/auth.py).
    WS_TICKET_TTL_S: int = 30
    RATE_LIMIT_WS_TICKETS: int = 30

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value):
        """CORS_ORIGINS from the environment: a comma-separated string or a JSON list; a ready list is taken as is."""
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                return json.loads(text)
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _check_production_secrets(self):
        """
        In production a weak SECRET_KEY = the ability to forge the token of any user.
        It is better not to start at all than to run with the example key or a short key.
        """
        if self.is_production:
            key = self.SECRET_KEY
            if len(key) < MIN_SECRET_KEY_LENGTH or key.lower() in _WEAK_SECRET_KEYS or "change-me" in key.lower():
                raise ValueError(
                    f"SECRET_KEY must be a random string of at least {MIN_SECRET_KEY_LENGTH} characters "
                    "in production (e.g. `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`)"
                )
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() == "production"

    @property
    def async_database_url(self) -> str:
        """The PostgreSQL address for the asyncpg driver, assembled from the POSTGRES_* settings."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
