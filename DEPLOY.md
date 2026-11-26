<!-- --- FILE: DEPLOY.md --- -->

# Deploying regence (production)

The stack comes up with one command via `docker-compose.prod.yml`:

| Service   | What it does                                                      | Exposed      |
|-----------|-------------------------------------------------------------------|--------------|
| `web`     | nginx: frontend static files, proxy for `/api/` and WebSocket, CSP | port 80      |
| `api`     | FastAPI (uvicorn, `WEB_CONCURRENCY` processes)                     | —            |
| `worker`  | Celery, `analysis` queue: background analysis of finished games     | —            |
| `worker-simulation` | Celery, `simulation` queue: bot-vs-bot games in tournaments, bot self-play | — |
| `beat`    | Celery beat: scheduled tasks (section 8c); exactly one process per stack | —            |
| `migrate` | one-shot: applies Alembic migrations and loads puzzles before api and worker start | — |
| `db`      | PostgreSQL 16                                                      | —            |
| `redis`   | Redis 7.4 with AOF (game state, queues, limits, Celery broker)     | —            |
| `backup`  | scheduled `pg_dump` into `BACKUP_DIR`, deletion of old copies       | —            |

## 1. Configuration

    cp .env.example .env

You must change in `.env`:

- `SECRET_KEY` — a random string of at least 32 characters. With a weak key the API in production
  **does not start** (the tokens of all users are signed with it):

      python -c "import secrets; print(secrets.token_urlsafe(48))"

- `POSTGRES_PASSWORD` — your own DB password.

`ENVIRONMENT=production` and the DB and Redis addresses are set by `docker-compose.prod.yml` itself.

## 2. Launch

    docker compose -f docker-compose.prod.yml up -d --build
    docker compose -f docker-compose.prod.yml ps
    curl http://localhost/health      # {"status": "healthy", "checks": {...}}

Loading the archive of world champions' games (once, optional):

    docker compose -f docker-compose.prod.yml exec api python -m src.db.seed

## 3. Updating

    git pull
    docker compose -f docker-compose.prod.yml up -d --build

Migrations are applied automatically by the `migrate` service before `api` and `worker` are restarted.

> The release from sprint 7 changes the token format: all users will log in again once.

> **Rename michess → regence (2026-11-19).** In `.env.example` the database and its user are now `regence_db` /
> `regence_user`. If the server already runs with the previous `michess_db` / `michess_user`, you can leave everything as is: the names
> are set by the server's `.env`. To rename (before `up -d`, with `api` and `worker` stopped):
>
>     docker compose -f docker-compose.prod.yml stop api worker beat
>     docker compose -f docker-compose.prod.yml exec db psql -U michess_user -d postgres >       -c "ALTER DATABASE michess_db RENAME TO regence_db" >       -c "ALTER ROLE michess_user RENAME TO regence_user" >       -c "ALTER ROLE regence_user PASSWORD '<password from .env>'"
>
> (a renamed role loses its password — the last command sets it), then in `.env` set
> `POSTGRES_USER=regence_user`, `POSTGRES_DB=regence_db` and perform the update as above. The migration itself renames the source of own puzzles
> `michess` → `regence`; the login cookie moves over on the first session refresh (section 8b).

## 4. HTTPS

The domain is `regence.club`, DNS and proxy are Cloudflare (Free plan, zone active; records are changed only there, not in GoDaddy).
By default nginx in the `web` image listens only on HTTP (port `HTTP_PORT`): this way it can be put behind any
load balancer, and health checks and the CI build do not require certificates. Any external proxy must pass
`Upgrade`/`Connection` for WebSocket (`/api/v1/ws/`) and replace, not append to, `X-Forwarded-For`: the limits on login
attempts and on engine requests are counted by client IP.

**Scheme with Cloudflare (SSL/TLS mode — Full (strict); do not enable Flexible):**

1. **DNS.** In Cloudflare add an A record `@` → server IP (Proxied); `www` (a CNAME to `regence.club`) already exists.
   WebSockets work through the Cloudflare proxy without separate setup. SSL/TLS → Edge Certificates: enable
   *Always Use HTTPS* and *Automatic HTTPS Rewrites*.
2. **Origin certificate.** SSL/TLS → Origin Server → Create Certificate (up to 15 years, `regence.club` and `*.regence.club`).
   Save on the server `deploy/certs/origin.pem` and `deploy/certs/origin.key` (permissions 600; the `deploy/` folder does not
   go into git, do not publish the key).
3. **Client address.** `scripts/deploy/cloudflare_ips.sh nginx` writes `deploy/cloudflare_real_ip.inc`: nginx takes the client IP
   from `CF-Connecting-IP`, but only from Cloudflare addresses (from other sources `CF-Connecting-IP` is ignored, so it cannot
   be forged). It then goes to the API as `X-Forwarded-For` — for limits, logs and anti-cheat.
4. **Launch.** `docker compose -f docker-compose.prod.yml -f docker-compose.tls.yml up -d` — adds port 443
   (`HTTPS_PORT`) with `frontend/nginx-tls.conf`; HSTS is sent only over HTTPS (30 days; once everything is verified,
   raise it to a year in `map $hsts_value`, `frontend/nginx.conf`).
5. **Close the origin against bypass.** `sudo scripts/deploy/cloudflare_ips.sh ufw` allows 80/443 only for the Cloudflare
   ranges (allow SSH separately: `ufw allow OpenSSH`, then `ufw default deny incoming`). The ranges change
   rarely: rerun the scripts (`nginx`, `ufw`) once a month, after `nginx` — `docker compose ... restart web`.
6. **Cache.** Rules → Cache Rules: a rule "`/api/*` — Bypass cache" (and everything with authorization); cache only
   the frontend static files (`/assets/*` is already served with `immutable`). Cloudflare itself prepends its own lines to
   `robots.txt` (AI bots: search and agents allowed, training blocked); our own `frontend/public/robots.txt` blocks `/api/`.
7. **Do not enable** without agreement Bot Fight Mode (on Free it breaks API clients and webhooks), Under Attack and Development
   Mode. To protect login and registration, use Rate Limiting rules on `/api/v1/auth/*` instead of Bot Fight Mode; DNSSEC —
   enable it in Cloudflare and add the DS record in GoDaddy (DNS → DNSSEC). We do not put Cloudflare tokens in the repository:
   if API access is needed, use a separate token with only Zone → DNS Edit for `regence.club`, kept in the server's secrets.
8. **"Maintenance" page (502/503/504).** The ready file is `frontend/public/maintenance.html` (self-contained, English
   only, its own artwork). On the Free plan Cloudflare does not allow custom error pages ("Custom Errors" — from the
   Pro plan). After moving to Pro: Rules → Custom Error Rules → a rule on `http.response.code in {502 503 504}`
   (and `cf.response.1xxx_code`/521–524 for a downed server), the response is the HTML from this file, response code 503. Without Pro
   a player sees the standard Cloudflare page during an outage; we do not put a Worker on all traffic for this (an extra hop for
   game WebSockets).
9. **Waiting page before launch.** Currently `regence.club` and `www` are served by the Worker `regence-landing` (`ops/landing`, deployed with
   `cf deploy` in that folder; the page is English only). When the site is rolled out,
   detach the Worker from the domains (Workers & Pages → regence-landing → Domains) and only then add the A record `@`,
   otherwise it will keep intercepting traffic.

In the server's `.env`: `PUBLIC_BASE_URL=https://regence.club`; `COOKIE_SECURE` turns on by itself when `ENVIRONMENT=production`.

## 5. Backups

The `backup` service takes a DB snapshot immediately at start and then every `BACKUP_INTERVAL_HOURS` hours
(24 by default) into the host folder `BACKUP_DIR` (`./backups`): `regence_YYYYmmdd_HHMMSS.dump`,
`pg_dump -Fc` format. Snapshots older than `BACKUP_KEEP_DAYS` days (14) are deleted.

**Copy `BACKUP_DIR` off the server** (rsync, `rclone` to object storage): a copy
on the same disk will not survive the loss of the disk or the server.

**Restore verification runs by itself:** after a snapshot the `backup` service, once every `BACKUP_VERIFY_EVERY_DAYS` days (7;
0 — disabled), restores the latest snapshot into a temporary database. A snapshot or verification failure is written to the log as an
`ERROR` line and sent by POST request to `BACKUP_ALERT_WEBHOOK_URL`, if set (the receiver can be anything: Slack, a bridge to Telegram,
a monitoring service).

**An off-server copy** is the optional service `backup-offsite` (rclone), enabled by a profile:

    docker compose -f docker-compose.prod.yml --profile offsite up -d

The storage is described in `.env`: `BACKUP_OFFSITE_PATH=offsite:<bucket>` and the `RCLONE_CONFIG_OFFSITE_*` variables (an example
for an S3-compatible one is in `.env.example`; the list of storage types is in the rclone documentation). Every `BACKUP_OFFSITE_INTERVAL_HOURS`
hours (24) the new `regence_*.dump` files are copied; deletion of old snapshots in the storage is configured by the storage's
own policy. A storage account and keys are needed — that is on the owner.

    # a snapshot right now (for example, before an update with migrations)
    docker compose -f docker-compose.prod.yml run --rm --no-deps backup once

    # check: the latest snapshot is restored into a temporary database and readable
    docker compose -f docker-compose.prod.yml run --rm --no-deps backup verify

Check restoration regularly (at least once a week, for example with a cron job running `verify`):
a snapshot that cannot be restored will be discovered only on the day of the disaster.

### Restore

    docker compose -f docker-compose.prod.yml stop api worker
    docker compose -f docker-compose.prod.yml run --rm --no-deps backup restore regence_20261111_094729.dump
    docker compose -f docker-compose.prod.yml up -d

`restore` replaces the contents of the working database in one transaction (on error the database stays as
it was). If the snapshot was taken on an older schema version, the `migrate` service will catch it up on `up`.
The state of games in progress is stored in Redis (AOF) and is not covered by the DB snapshot.

## 6. Monitoring

**Logs and bug analysis.** Each log line is json (in production; `LOG_FORMAT=auto`) with the fields `ts`, `level`,
`component` (api/worker), `msg` and context: `request_id` (an end-to-end request number, also in the response header
`X-Request-ID`), `user_id`, `game_id`, `ws_id`, `task`. Requests are written as an `http_request` line (route template, status,
duration), player actions over WebSocket as `ws_action`, connection and closing as `ws_connected` / `ws_disconnected` (the close
code distinguishes a page reload from a network drop), worker tasks as `task_started` / `task_finished` /
`task_failed`. The page sends error reports (`client_error`: a render error, an unhandled exception,
a page reload with the trail of events before it) — `src/api/client_errors.py`. There are no passwords, tokens or request bodies in the log.
The container console is rotated by the Docker driver (5 files of 20 MB). Analysis by a key:

    docker compose -f docker-compose.prod.yml logs --no-log-prefix api worker \
      | python scripts/trace_logs.py game_id=20767          # or request_id=…, user_id=…, tournament_id=…
    python scripts/trace_logs.py user_id=1 --level WARNING logs/api.jsonl logs/worker.jsonl   # development

The chain for a complaint: find the `client_error`, take `related_request_ids` and analyze each number with the same script.
`LOG_FILE` (optional) writes a json file with rotation — in development `start_dev.ps1` sets it (`logs/`).

**Errors — Sentry.** Set `SENTRY_DSN` in `.env` (a Python project in Sentry or a compatible
GlitchTip) and restart `api` and `worker`. Sentry receives unhandled exceptions and everything that
is logged as an error: failures of WS actions, of the timeout loop, of background analysis. Cookies, authorization
headers and IPs are not sent. `SENTRY_TRACES_SAMPLE_RATE` (for example, `0.05`) enables
sampled performance tracing. For the page (project `regence-web`) the DSN is set at image build time:
`VITE_SENTRY_DSN` in `.env` next to compose (passed as a build argument of the `web` service; in development — `frontend/.env`).
**Page source maps** (readable traces instead of `index-4f3a.js:1:20431`): when the `web` image is built with a token, the maps
are uploaded to Sentry (`@sentry/vite-plugin`, `frontend/vite.config.ts`) and removed from the build — the site does not serve them. The token is
Sentry → Settings → Auth Tokens (scopes `project:releases`, `org:read`); save it to a file outside the repository and
specify `SENTRY_AUTH_TOKEN_FILE=/path/to/file` next to compose (passed as a BuildKit secret, it does not end up in the image layers).
Without the file no maps are created and the build is ordinary. Matching is by Debug ID inside the files — no release name is needed.
Screen recording (Session Replay) and personal data are not enabled; the address for Sentry reports is allowed in the CSP
(`frontend/security_headers.inc`). Events carry the tags `request_id`, `user_id`, `game_id` — use them to find the log line.

**Metrics — Prometheus.** The API serves `GET /metrics` (a sum over all uvicorn processes). The
path is not published externally — nginx proxies only `/api/` and `/health`; Prometheus must be on the
compose network (or publish the `api` port only on an internal interface):

    scrape_configs:
      - job_name: regence
        static_configs:
          - targets: ["api:8000", "worker:9101", "worker-simulation:9101"]

The Celery workers serve their own metrics (port `WORKER_METRICS_PORT`, set by `docker-compose.prod.yml`): these hold the
engine time in background analysis (`kind="analysis"`) and in bot games (`kind="simulation"`). The total engine budget is
`sum(increase(regence_engine_seconds_total[1d]))` over all three targets.

| Metric                                     | What it shows                                               |
|--------------------------------------------|-------------------------------------------------------------|
| `regence_ws_connections`                   | open WebSocket connections                                  |
| `regence_ws_actions_total{action,outcome}` | WS actions: `ok`, `ignored`, `rejected`, `error`, `rate_limited` |
| `regence_ws_action_seconds{action}`        | processing time; `action="make_move"` — move latency        |
| `regence_db_pool_checked_out`              | busy DB pool connections (the limit is `DB_POOL_SIZE + DB_MAX_OVERFLOW` per process) |
| `regence_http_requests_total`, `regence_http_request_seconds` | HTTP by route template and status    |
| `regence_games_finished_total{termination}`| finished games                                              |
| `regence_timeout_check_failures_total`     | failures of the flag and no-show checks (should be about zero) |
| `regence_engine_seconds_total{kind}`       | time the Stockfish engines are busy: `bot_move`, `analysis`, `coach`, `simulation`, `puzzles`, `other` |
| `regence_engine_acquire_wait_seconds{kind}`, `regence_engine_busy_total{kind}` | waiting for a free engine and "pool busy" refusals |
| `regence_active_players_today`             | players who logged in during the UTC day (HyperLogLog in Redis) |
| `regence_celery_queue_length{queue}`       | messages in the Celery queue (`analysis`, `simulation`) not yet taken by a worker |

It is worth configuring alerts: p95 of `regence_ws_action_seconds{action="make_move"}` above 0.5 s,
growth of `regence_ws_actions_total{outcome="error"}` and `regence_timeout_check_failures_total`,
`regence_db_pool_checked_out` at the pool limit, `/health` with code 503.

**Engine budget (task 23.3).** CPU per active player per day (at the end of the UTC day):
`increase(regence_engine_seconds_total[1d]) / regence_active_players_today`, by kind of work — with `by (kind)`.
The counters are written by the process where the engine ran: the API (bot moves, analysis, coach) serves them on `/metrics`, while
the Celery workers (background analysis, tournament simulation) do so only if they share `PROMETHEUS_MULTIPROC_DIR` with the API
or have their own exporter. Growth of `regence_engine_busy_total` is a signal to add engines (`ENGINE_POOL_SIZE`) or workers.

**Endgame tablebases (task 14.4).** Owner decision: in production we keep the tables ourselves. Set up our own tablebase
server with the lichess API (the lila-tablebase project: Syzygy 3–5 pieces ≈ 1 GB, plus DTM tables for the "moves to mate" counter)
and specify its address in `TABLEBASE_URL` (by default the public `https://tablebase.lichess.ovh/standard`, for
development only). Responses are cached in Redis for 30 days. If the tablebase server does not respond within 1.5 s, the position is evaluated by a Stockfish from the pool
(depth 18, without "moves to mate"; the response is not cached) and the trainer shows a note; 503 `tablebase_unavailable` —
only when there is no engine either.

**Free-tier quotas.** `FREE_TIER_LIMITS=true` enables daily quotas on full game analysis
(`FREE_GAME_ANALYSES_PER_DAY`, 3 by default) and on the coach — advice, a hint, a move check
(`FREE_COACH_REQUESTS_PER_DAY`, 300). Completed work is what counts; over the quota — 429 `daily_limit_reached`.
Off by default — the pricing model (25.1) will turn it on. Bot moves, puzzles and play have no quotas.

**Alerts.** The ready rules are in `ops/prometheus/alerts.yml` (verified with `promtool`): a target not responding, 5xx share > 2%,
95th percentile of a move > 0.5 s, the `analysis` queue > 50 (10 min) and `simulation` > 500 (30 min), the DB pool 80% busy
(60 connections with `DB_POOL_SIZE` 10 + `DB_MAX_OVERFLOW` 20 and two processes), engine pool refusals, host CPU > 85%
(needs `node_exporter`, job `node`), failures of the flag check. Include the file in `prometheus.yml`:
`rule_files: ["/etc/prometheus/alerts.yml"]` and add Alertmanager with a receiver (email, Telegram, etc.) — without it
Prometheus only shows the rules that fired. The thresholds are for a single server; adjust them to the load. Check:
`docker run --rm --entrypoint promtool -v "$PWD/ops/prometheus:/r" prom/prometheus check rules /r/alerts.yml`.

## 7. Load test

`scripts/loadtest/ws_load.py` plays out N simultaneous PvP games through nginx the same way
real players do (ticket, WebSocket, private challenge, random legal moves, resignation), and measures
move latency — from sending `make_move` to receiving one's own `move_made`.

    # loadtest_NNNN players and their tokens (registration through the API is limited by IP)
    docker compose -f docker-compose.prod.yml exec -T api         python -m scripts.loadtest.seed_users --count 400 > tokens.json
    python scripts/loadtest/ws_load.py --base-url http://localhost --tokens tokens.json --games 200
    # cleanup: the players and their games
    docker compose -f docker-compose.prod.yml exec -T api python -m scripts.loadtest.seed_users --cleanup

The client needs `websockets`, `httpx` and `chess` (they are in `uv.lock`). Exit code 1 on errors
or when p95 is above `--max-p95-ms`. Run it on a copy, not on the working server: the test creates games
that end up in the analysis queue.

Results of 2026-11-11 (one host: 2 uvicorn processes, PostgreSQL, Redis, a worker in Docker Desktop;
200 games × 40 plies, "thinking" 0.5–1.5 s — ~150 moves/s, 400 WebSockets):

| Configuration                      | p50   | p95    | p99    | errors |
|------------------------------------|-------|--------|--------|--------|
| analysis worker without a CPU limit | 17 ms | 233 ms | 668 ms | 0      |
| worker stopped                      | 16 ms | 72 ms  | 390 ms | 0      |
| worker with `WORKER_CPUS=1.0`       | 18 ms | 136 ms | 499 ms | 0      |

In steady state p95 is 30–55 ms; the tail comes from the synthetic spike — 200 games start
and finish almost simultaneously. The worker's Stockfish takes CPU away from the API, so the worker is limited by
`WORKER_CPUS`; as the load grows, move it to a separate machine.

## 8. What is important to know

- **Only `web` is exposed externally.** The API trusts `X-Forwarded-For` from any address of the internal
  compose network (`FORWARDED_ALLOW_IPS=*`) — this is safe as long as the `api` port is not published.
- **Several API processes** are supported: presence, spectators, event broadcast and the timeout
  loop (with leader election) work through Redis.
- **Monitoring:** `GET /health` returns 503 if the DB or Redis is unavailable.
- **API documentation** (`/docs`) is disabled in production.
- **Recreating the API does not require restarting nginx:** the `api` address is re-read from Docker DNS
  every 10 s (`resolver` + `resolve` in `frontend/nginx.conf`).
- **The Celery worker** is required for background game analysis; without it the analysis is still
  computed on demand from the game page button.
- **The simulation worker** (`worker-simulation`) is required for tournaments: bot-vs-bot games are played
  only by it. Without it a tournament will get stuck at the first round — bot games will wait in the `simulation` queue.
  The queues are separate so that a tournament of 8 (up to 28 games) does not delay the analysis of players' games
  (`SIMULATION_CONCURRENCY`, `SIMULATION_CPUS`).
- **Bot strength** is shown as measured if the image contains `src/services/bots/calibration.json`. It is
  updated by `scripts/calibrate_bots.py` (section 9) — after **any** change to the bots' move choice.

## 8b. Login: short token and refresh cookie

The access token lives for `ACCESS_TOKEN_EXPIRE_MINUTES` (15) and is stored only in page memory; a long-lived login is the refresh token
in the `regence_refresh` cookie (HttpOnly, SameSite=Strict, path `/api/v1/auth`, `REFRESH_TOKEN_EXPIRE_DAYS` = 30), and its hash is
in Redis (before 2026-11-19 the cookie had the name `michess_refresh` — it is no longer read under that name: the site was never deployed, so there are no live sessions). The Secure flag is set when `ENVIRONMENT=production` (overridable with `COOKIE_SECURE`): behind nginx HTTPS is required (section 4).
If the frontend and the API are on different addresses, the frontend address must be in `CORS_ORIGINS` — requests go with
`credentials: 'include'`. Resetting Redis logs everyone out of long sessions: they must log in again.

## 8a. Mail: e-mail confirmation and password reset

> **Currently DNS forbids any sending from `regence.club`:** TXT `@` = `v=spf1 -all`, `_dmarc` = `v=DMARC1; p=reject;`.
> This is protection against spoofing while there is no mail. When connecting a provider (SES / Resend / Postmark), **first update the records in
> Cloudflare**: SPF with the provider's `include:`, its DKIM (CNAME/TXT) and DMARC — at first `p=none` or `p=quarantine` with
> `rua=mailto:…` for reports, and only after delivery is verified back to `reject`. Otherwise the platform's emails will be rejected.
> Receiving (`support@regence.club` → Gmail) is Cloudflare Email Routing; it will add its own MX and SPF itself.

A player's e-mail is optional; it is linked via a link from an email and is needed to restore access if the password is
forgotten. Emails go out over ordinary SMTP — any transactional mail provider or your own server will do.

1. Choose a provider (at the start — Brevo: the free volume is enough for the beta, an EU company; later — Amazon SES
   or Postmark) and verify your domain with it: add the **SPF** and **DKIM** records it gives you to DNS, plus
   **DMARC** (`v=DMARC1; p=quarantine; rua=mailto:…`). Without them emails land in spam.
2. In `.env`: `SMTP_HOST`, `SMTP_PORT` (usually 587), `SMTP_USER`, `SMTP_PASSWORD` (the provider's SMTP key),
   `SMTP_STARTTLS=true`, `MAIL_FROM` (an address on the verified domain), `PUBLIC_BASE_URL` (the site address — the links in
   emails are built from it).
3. `docker compose -f docker-compose.prod.yml up -d` — the API will re-read the settings. Check: in the settings link
   your address and open the link from the email.

While `SMTP_HOST` is empty, emails are not sent but written to the API log (`docker compose logs api | grep mail`) —
this is convenient in development. The provider becomes a processor of personal data — list it in the privacy
policy (task 23.1).

## 8d. Beta program: invitations, problem reports, community channel

- **Consent at registration.** `REQUIRE_TERMS_CONSENT=true` (default): without the "I accept the rules and privacy policy" checkbox `POST /auth/register` responds 400 `terms_not_accepted`; the version and time of consent are `users.terms_version` / `terms_accepted_at` (`src/services/legal.py`, `TERMS_VERSION`). Change `TERMS_VERSION` with every edit of the documents.
- **Closed registration.** `REGISTRATION_INVITE_ONLY=true` in `.env` — an account is created only with an invitation code;
  by default registration is open (the code is then optional, but a valid one is counted). Codes are created and revoked by a
  moderator on the `/moderation` page: the usage limit and expiry are optional, and for each code you can see
  how many people came through it. The tester is sent the "Copy link" link (`/?invite=CODE`) — it immediately
  opens registration with the code filled in. The first moderator is created with `scripts/make_moderator.py` (section 9).
- **"Report a problem".** A button in the header (for a logged-in user on a phone — in the profile menu), works without login too. The text
  is accompanied by the page path (without URL parameters), the app version, the language and the window size. Reports are on
  `/moderation` with the statuses "new → in progress → done / rejected". The limit is `RATE_LIMIT_FEEDBACK` reports per
  `RATE_LIMIT_FEEDBACK_WINDOW_S` per address (or per player).
- **Weekly digest.** `docker compose exec api python scripts/feedback_digest.py` prints a 7-day summary as
  a block for `ToDo.md`: how many came in and how they were handled, by site section, the unhandled ones as `- [ ]` items.
- **Community channel.** `COMMUNITY_URL=https://t.me/regence_club` (the project's Telegram channel) — the link appears on the "About" page and in
  the "Report a problem" window; empty — there is no link. The label is chosen by the address (Telegram, Discord or just "community").

After editing `.env` — `docker compose -f docker-compose.prod.yml up -d` (the API will re-read the settings).

## 8c. Scheduled tasks

The `beat` service (`celery beat`) runs tasks from `src/worker/celery_app.py` (`beat_schedule`) on a schedule:

| Task | When | Queue | What it does |
|---|---|---|---|
| `workout_reminders` | once a day, 16:00 UTC | `analysis` | a warm-up reminder to players with an ongoing streak |
| `bot_selfplay` | every 6 hours, at minute 17 | `simulation` | the workshop archetypes play each other and tune their strength |
| `arena_reminders` | every minute | `analysis` | a notification of an arena start to those who pressed "remind me" (5 minutes ahead) |
| `archive_move_telemetry` | once a day, 03:41 UTC | `analysis` | the raw `moves` of games older than 90 days — into the summary `games.telemetry_summary`, then delete |
| `arena_awards` | every 5 minutes | `analysis` | prize places of finished arenas: record, notification, trophies and achievements |
| `review_cheater_flags` | Monday 06:07 UTC | `analysis` | old unfair-play flags (without a decision for over 60 days) go back into the moderator queue |
| `legends_week_start` | Monday 07:13 UTC | `analysis` | the new legends week is announced to its regulars (a finished run in one of the last 4 weeks), at most once a week |
| `purge_deleted_accounts` | once a day, 04:23 UTC | `analysis` | accounts whose deletion was requested more than `ACCOUNT_DELETION_GRACE_DAYS` (10) days ago are anonymised: personal and social data erased, games kept without the name |

There must be exactly one beat process per stack: two processes will send every task twice.

## 8e. Arenas and conferences

Arenas are created by the API itself when the list is requested, 6 hours ahead, per the schedule in `src/services/arena_schedule.py`:
each of the five conferences has its plan set in its local time. Settings in `.env`:

- `ARENA_CONFERENCES` — the conferences for which arenas are created (all five by default:
  `central,western,northern,southern,eastern`). While there are few players, the list should be shortened (for example, `central`):
  in the shared European evening the arenas of three conferences run at the same time and split the players among themselves. Future empty arenas
  of disabled conferences are removed by themselves on the next list request.
- `COUNTRY_HEADER` — the name of the header in which the proxy in front of the server names the visitor's country (for Cloudflare —
  `CF-IPCountry`). The country from it is only suggested to the player when choosing their country and is not stored anywhere. Empty —
  there is no address-based suggestion, the client suggests a country from the browser language. The application has no "address → country" database of its own.

Arena start reminders work only when `beat` is running.

## 9. Utility scripts

| Script | What it does | When to run |
|---|---|---|
| `scripts/calibrate_bots.py` | Bot matches against Stockfish references (fixed `UCI_Elo`) and among themselves, ratings of all bots at once with ±95%; writes `calibration.json` and a log into `scripts/calibration_runs/` | After changing the bots, their style or strength; ~1 h, needs Stockfish |
| `scripts/calibrate_bots.py --from-log LOG` | Recomputes ratings from the log of a previous run without playing games; `--reuse-log` mixes in the bots' games among themselves | Only the fitting formula or the references changed |
| `scripts/verify_lessons.py` | Checks the answers of the school lessons against Stockfish: the answer is no worse than the best move, it has no near-equal rival, the "wrong" moves are indeed worse | After editing or adding lessons (CI checks only legality) |
| `scripts/style_metrics.py PGN` | The bots' middlegame character from calibration games (`calibrate_bots.py --pgn`): sacrifices, trades, checks, pressure on the king, attack | After changing the style of the historical bots |
| `scripts/product_metrics.py [--days N]` | An owner's report from our own database (the `product_events` table, no third-party trackers): registrations, activation (first game within 5 min and within a day), retention D1/D7/D30, whether players reach puzzles, lessons, tournaments | Once a week during the beta; in production — `docker compose exec api python scripts/product_metrics.py` |
| `scripts/make_moderator.py <name> [--revoke]` | Grant or revoke the moderator role (task 17.4): the report queue, review of the unfair-play flag and appeals — the `/moderation` page | As needed. In production: `docker compose exec api python scripts/make_moderator.py <name>` |
| `scripts/feedback_digest.py [--days N] [--until YYYY-MM-DD] [--output file]` | A weekly summary of "Report a problem" messages (task 24.4) in a form ready for `ToDo.md`: totals by status and site section, the unhandled ones as items | Once a week during the beta. In production: `docker compose exec api python scripts/feedback_digest.py` |
| `scripts/build_collections.py` | "Fun collections" of the archive for the "Viewer" page (task 16.3): metrics of all archive games → `collection_entries` (replaces entirely) | After migration `60ae872759c7` and after the archive is extended; 27.6 thousand games ≈ 20 s on 8 processes. In production: `docker compose exec api python scripts/build_collections.py` |
| `scripts/build_position_index.py` | The position index (task 16.1): the first 30 plies of all finished games → `position_stats`, `position_games`; repeating is safe (the `games.positions_indexed` flag) | Once after migration `79ba65cdf46e`; afterwards a Celery task indexes games on completion; 27.6 thousand games ≈ 5 min, ≈ 180 MB in the database. In production: `docker compose exec api python scripts/build_position_index.py`. With `--library` — library games loaded before migration `a8d3f6c2e5b7` (8b), into `position_library_games`: once after it; new games are indexed by the library import |
| `scripts/build_guess_positions.py --games N` | Selection of positions for "Guess the master's move" from the archive games in the database (two Stockfish passes, the rules in `src/services/guess_selection.py`); writes `guess_positions`, skips games already processed | Once after the archive is filled (each database has its own `game_id`s), then top up; ~600 games ≈ 3,000 positions in ~40 min on 8 processes. In production: `docker compose exec api python scripts/build_guess_positions.py --games 600 --workers 4` |
| `scripts/build_guess_positions.py --refilter` | Bring previously selected positions in line with the current rules: remove book openings (the openings table) and technical endgames (≤ 7 pieces), assign themes; no engine | Once after migration `ff534b487153` (position themes), if positions were selected before it |
| `scripts/cbh_to_pgn.py <folder> <pgn-folder>` | Training databases in a closed format (`.cbh`) → PGN in the same subfolders (task 27.3): only headers and the main line; exercise positions and special encoding are skipped, `.cbv` archives and `.cib` databases are listed as unreadable | Locally, before `import_library.py`: its output is loaded by it as ordinary PGN |
| `scripts/import_library.py <folder> --collection <path> [--visibility public\|owner\|staff] [--owner <name>] [--source <code>] [--dry-run]` | The game library (tasks 27.1–27.2): the folder's PGNs recursively → a tree of collections; only headers and the main line, identical games are merged, a repeated run creates no duplicates | After migration `443506f2bd39`, then when topping up. The owner's folders are not in the repository: copy them to the server and run `docker compose exec api python scripts/import_library.py /data/library/structures --collection "Pawn structures" --source structures`; what to load and with what visibility — ToDo, task 27.2 |
| Master games (21.5) | For the masters' books and the "Master games" collection: unpack the players' files from pgnmentor.com (`https://www.pgnmentor.com/players/<Surname>.zip`: Chigorin, Tarrasch, Pillsbury, Marshall, Nimzowitsch, Reti, Tartakower, Botvinnik, Tal, Petrosian) into a folder and load them | `docker compose exec api python scripts/import_library.py /data/library/masters --collection "Master games" --source pgnmentor`; the books are already in the repository (`src/services/bots/books/`) |
| `scripts/annotate_library.py --collection <path part> [--limit N] [--workers 4]` | Draft annotations of the library (task 27.4): coach comments on moves (Stockfish), status auto; does not touch annotations edited by humans | After migration `5c657e5a912e`, starting with "Beautiful games"; slow — run on a worker with an engine |
| `scripts/build_classics.py [--count N] \| --library <moves_hash …> \| --pgn <file>` | Master games with stops (tasks 14.7, 27.6) → `frontend/src/content/classics/<id>.json`: from the champions' archive (needs `guess_positions`), or chosen games of the library (by `moves_hash` or a prefix of ≥ 12 characters) or of a PGN file; stops by the "Guess the move" selection, a game with fewer than 2 is skipped; intro/summary texts (en, uk) are kept on re-run | Locally, with Stockfish; the result is committed as client content |
| `scripts/tag_library.py [--all] [--texts]` | Tagging of the library (tasks 27.5, 27.9): pawn structure and the "ended in mate" mark for already loaded games (`--all` — recompute everything), `--texts` — repair of headings in cp1251 read as Latin and of font figurines | After migrations `af7546925853` and `875b0d34b6be` — once with `--all`, after editing the detector rules — again; new games are tagged by the import itself. `docker compose exec api python scripts/tag_library.py --all` |
| `scripts/loadtest/*` | Load test of WebSocket games (section 7) | Before launching on a new server |
| `scripts/backup/pg_backup.sh` | Backups and restore verification (section 5) | On a schedule (the `backup` service) |
