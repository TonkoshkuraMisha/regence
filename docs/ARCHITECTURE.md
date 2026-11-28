<!-- --- FILE: docs/ARCHITECTURE.md --- -->

# How regence works: what runs, how, and where the data comes from

A guide for the project owner and for developers: for each section of the site, what it does, which files implement it,
where its data comes from and which test checks it. The detailed rules of each section are written at the top of its
module (the docstring); this document is the map that leads to them. State as of 17.11.2026 (sprint 33).

Related documents: launch — `QUICKSTART.md`, deployment — `DEPLOY.md`, working with branches — `WORKFLOW.md`, plan and
task history — `ToDo.md`, licences and sources — `ATTRIBUTION.md`, short rules for the AI assistant — `CLAUDE.md`.

## 1. What the system consists of

| Part | What it is | Where the code is |
|---|---|---|
| Client | Single-page application: React 19, TypeScript, Vite, Tailwind | `frontend/src/` |
| API | FastAPI: HTTP endpoints and one WebSocket for games, the lobby and notifications | `src/api/`, `src/main.py` |
| Services | Rules and calculations that do not depend on HTTP | `src/services/` |
| Database | PostgreSQL 16 via SQLAlchemy 2.0 (async), Alembic migrations | `src/models/`, `migrations/versions/` |
| Redis | State of games in progress, the lobby, presence, rate limits, the evaluation cache, the Celery broker | keys — in §3 |
| Background tasks | Celery: the `analysis` queue (game review, position index, reminders) and `simulation` (bot games) | `src/worker/` |
| Engine | Stockfish, only through the process pool | `src/services/engine_pool.py` |

In production these are the nine services of `docker-compose.prod.yml`: `web` (nginx with the client's static files and
a proxy to the API), `api`, `worker`, `worker-simulation`, `beat` (the Celery schedule), `migrate`, `db`, `redis` and
`backup`. Details — `DEPLOY.md`.

## 2. How a request is handled

1. The client calls an endpoint (`frontend/src/services/*.ts` — one file per section) or sends an action over the
   WebSocket (`frontend/src/services/gameSocket.ts`). Components do not touch the network themselves: all services call
   the shared `services/http.ts` — `apiRequest` (JSON response) or `apiFetch` (the whole response: PGN text, headers),
   `apiUrl` — the address for links. It adds the sign-in token and Content-Type, and turns a failure into a `UiError`
   with text chosen by the server's code (`services/apiErrors.ts`); if the network is unavailable — "no connection".
2. The route in `src/api/<section>.py` checks the input (`src/api/deps.py`), the request rate limit
   (`src/api/rate_limit.py`) and, if the endpoint returns an evaluation or an engine move, the fair play rule
   (`src/api/fair_play.py`).
3. The route calls a service from `src/services/`; the service reads and writes the database through the models in
   `src/models/`.
4. The response is data and **codes**, not texts. A failure is a code from the registry `src/core/errors.py` with
   parameters; the client assembles the text in the player's language from the catalogs
   `frontend/src/i18n/messages/{en,uk}.ts`.

The list of all routes is assembled by `src/main.py` (`create_app`); in development they are visible at `/docs`.

**WebSocket** (`src/api/websockets.py`, address `/api/v1/ws/matchmaking`). Sign-in is by a one-time ticket
(`POST /auth/ws-ticket`), not by a token in the address. Every client message is an action (`join_queue`, `make_move`,
`resign`, `offer_draw`, `berserk`, `chat_message` and others): each has its own handler function in `ACTION_HANDLERS`,
a rate limit by group (`WS_RATE_LIMITS`) and a short database session per action — the database connection is released
before the response is sent to the network (`ActionContext.release_db`).

## 3. Where the data lives

### PostgreSQL (the source of truth for everything that must persist)

| Area | Tables | Models |
|---|---|---|
| Players | `users`, `email_tokens`, `user_achievements`, `product_events` | `user.py`, `email_token.py`, `achievement.py`, `product_event.py` |
| Games | `games`, `moves`, `imported_games`, `import_subscriptions` | `game.py`, `move.py`, `imported_game.py` |
| Openings and positions | `position_stats`, `position_games`, `repertoires`, `repertoire_moves`, `repertoire_cards` | `position.py`, `repertoire.py` |
| Puzzles and training | `puzzles`, `puzzle_themes`, `puzzle_attempts`, `theme_progress`, `personal_puzzles`, `defense_drills`, `drill_records`, `guess_positions`, `lesson_progress`, `trainer_results`, `exam_results` | `puzzle.py`, `guess.py`, `lesson.py`, `trainer.py` |
| Bots | `bot_personalities`, `bot_opening_stats`, `bot_ratings`, `bot_rivals`, `bot_rival_stats`, `bot_tunings`, `bot_tuning_log`, `ladder_beaten` | `personality.py`, `bot_memory.py`, `ladder.py` |
| Tournaments with bots | `tournaments`, `tournament_players`, `tournament_games` | `tournament.py` |
| Arenas between humans | `arenas`, `arena_players`, `arena_games`, `arena_reminders`, `arena_awards` | `arena.py` |
| Teams | `teams`, `team_members` | `team.py` |
| Library and archive | `library_collections`, `library_games`, `library_game_collections`, `library_annotations`, `collection_entries` | `library.py`, `collection.py` |
| Social | `follows`, `notifications`, `direct_messages`, `blocks`, `hidden_conversations`, `posts`, `post_comments`, `post_likes`, `reports`, `study_materials` | `social.py`, `moderation.py`, `study.py` |
| Beta | `invites`, `feedback`, `users.invite_id` (partner links: who came and started to play) | `beta.py` |

The schema is changed only by migrations (`migrations/versions/`); CI applies them to an empty database and checks them
against the models with the `alembic check` command. The report on the state of the schema and the open decisions about
it — `docs/db-audit-2026-11-17.md`.

### Redis (what lives briefly or must be shared by several API processes)

| What | Keys | Who writes |
|---|---|---|
| State of a game in progress: position, clocks, version, draw offer, berserk, lag quota spent | `game:{id}:state`, `game:{id}:commands`, `game:{id}:moves` | `game_state.py` |
| Which games are in progress and the nearest deadline of each (flag, no-show, abandoned game) | `active_games`, `game_deadlines`, `games:pending_finish`, `user:{id}:current_game` | `game_state.py` |
| Lobby and private challenges | `queue:prefs:{id}` and the queue keys | `matchmaker.py` |
| Presence and spectators | `presence:user:{id}`, `game:{id}:spectators`, `user:{id}` channels | `connection_manager.py` |
| Waiting for a pairing in an arena | `arena:{id}:waiting` | `arena.py` |
| Long-lived sign-in | `refresh:<hash>` | `auth_sessions.py` |
| Fair-play game sessions (ladder, tournament) and engine requests during a game | `fairplay:*` keys, ladder sessions | `fair_play.py`, `ladder.py` |
| Position evaluation cache, endgame tablebase responses, the player's active puzzle, review rooms | — | `move_check.py`, `tablebase.py`, `puzzles.py`, `study_room.py` |
| Request rate limits | — | `rate_limit.py` |

A game is written to the database as it is played (`sync_authoritative_state_to_db`) and finally when it ends; if the
state in Redis is lost, it is restored from the database (`_recover_state_from_db`). Long-lived sign-in sessions are not
covered by a database snapshot: a Redis reset signs everyone out.

### Files in the repository

| File | What it contains | How it is built |
|---|---|---|
| `data/puzzles/lichess_subset.csv.gz`, `lichess_themes_extra.csv.gz` | A selection of puzzles from the open lichess database (CC0) | `scripts/dev/build_puzzle_subset.py`, `build_theme_extra.py` |
| `data/puzzles/defense_drills.csv.gz` | Defence exercises | `scripts/dev/build_defense_drills.py` |
| `data/drills/seeds.json` | Verified positions for the generator exercises | `scripts/dev/build_drill_seeds.py` |
| `src/services/data/openings.tsv` | Opening table (CC0) | `scripts/build_openings.py` |
| `src/services/data/level_exams.json` | Level exams of the Grand Course | `scripts/build_level_exams.py` (strategy branch: quiet moves from library games; rest: puzzles) |
| `src/services/bots/books/*.json` (22) | Bot opening books from masters' games | `scripts/build_opening_books.py`, `build_master_books.py` |
| `src/services/bots/calibration.json` | Measured bot strength | `scripts/calibrate_bots.py` |
| `src/services/civility_lexicon.txt` | Dictionary of the insult filter | by hand |
| `frontend/src/content/endgames.json` | Exercises of the endgame trainer, checked against tablebases | `scripts/build_endgames.py` |
| `frontend/src/content/lessons/*.json` | School lessons in two languages (en, uk) | by hand; checked by `validate.ts` and `scripts/verify_lessons.py` |
| `frontend/src/i18n/messages/{en,uk}.ts` | All interface texts in two languages (en, uk) | by hand; keys are checked by a test |

Puzzles are loaded into the database by the `migrate` service at every deployment (`scripts/import_puzzles.py`). The
owner's library games and the masters' archive are not part of the repository — they are loaded by scripts (`DEPLOY.md`,
section 9).

### External services

The server reaches out only in four cases: endgame tablebases (`TABLEBASE_URL`, only the position is sent), import of a
player's games from lichess and chess.com (the nickname the player entered is sent), mail over SMTP, Sentry (if
`SENTRY_DSN` is set). What exactly and to whom — `ATTRIBUTION.md`, section "External services".

## 4. Sections of the site

For each section: what it does → files → where the data comes from → how it is checked. Test names are the files
`tests/test_<name>.py`.

### 4.1. Sign-in and account

- **What.** Registration by name and password (age 16+; a younger player only in kid mode, registered by a guardian
  with a guardian code), sign-in, long-lived session, password change, optional e-mail with password reset, export of
  one's own data, kid mode, account deletion with a grace period (the account closes at once, can be restored by
  logging in for `ACCOUNT_DELETION_GRACE_DAYS` = 10 days, then it is anonymised: personal and social data erased, the
  games stay with the opponents without a name).
- **Files.** `src/api/auth.py` (`/login`, `/restore`), `src/api/account.py` (`/delete`, `/kid-mode`),
  `src/api/deps.py` (`refuse_kid_mode`), `src/core/security.py` (password hash, JWT), `src/services/auth_sessions.py`,
  `email_links.py`, `mailer.py`, `account.py` (request, restore, daily purge `purge_deleted_accounts`),
  `account_state.py` (one rule "the account is open" for profiles, search, leaderboards, feeds and messages),
  `kid_mode.py` (what kid mode closes: free-text game chat, messages, the feed, the study room chat), `onboarding.py`,
  `legal.py` (consent and the age rule at registration, `/privacy`, `/terms`); client — `services/authToken.ts`,
  `services/account.ts` (sign-in, restore, registration, e-mail, password, export, deletion, kid mode),
  `services/kidMode.ts` (the shared flag that hides social UI), `components/AuthModal.tsx`, `components/Settings.tsx`,
  `components/settings/KidModeSection.tsx`, `components/EmailLinkPages.tsx`.
- **How.** A short-lived access token (15 minutes) lives only in the page's memory; the long-lived sign-in keeps a
  refresh token in an HttpOnly cookie, and only its hash is stored in Redis. A password change, "sign out
  everywhere" and a deletion request increment `users.token_version` — all previous tokens stop working. Data:
  `users.deletion_requested_at`, `users.kid_mode`, `users.kid_guardian_hash` (bcrypt, like a password).
- **Tests.** `auth_sessions`, `auth_hardening`, `token_lifecycle`, `account`, `kid_mode`, `email_links`, `onboarding`,
  `legal_consent`.

### 4.2. A game between humans

- **What.** A lobby with challenges, automatic matching, an invitation by link, rated and casual games, clocks with an
  increment, premoves, draws, resignation, rematch, spectators, chat, odds (material, time, "hourglass" — the mover's
  time goes to the opponent, the `games.hourglass` flag), Fischer random chess.
- **Files.** `src/api/websockets.py` (actions), `src/services/matchmaker.py` (lobby and game start),
  `game_state.py` (position, clocks, finish), `game_engine.py` (rules: legality, result, flag), `rating.py`,
  `connection_manager.py`, `odds.py`, `chess960.py` (a bot game, the archive replay of finished 960 games and their engine analysis); client — `components/Chessboard.tsx` and the hooks in
  `components/chessboard/hooks/` (`useGameSocket.ts`, `useClock.ts`, `usePremoves.ts`).
- **How a move goes.** `make_move` → `GameStateManager.process_atomic_move`: in a single Redis transaction
  (WATCH/MULTI) the turn order, the state version and legality are checked, time is deducted and the new position is
  recorded. The same move sent twice is applied once (`command_id`). Then the move is broadcast to both players and the
  spectators.
- **Clocks.** Time runs only for the side to move and is computed by the server from the moment of the previous move; a
  lost connection does not stop the clock. **Lag quota:** the client reports how long it thought over the move; the
  difference from the server's time (network delay) is returned to the player by the server — no more than 300 ms per
  move and 2 s per game (`LAG_PER_MOVE_MS`, `LAG_PER_GAME_MS`), and the flag falls with a delay equal to the remainder
  of the quota.
- **End of the game.** Checkmate, stalemate and draws by the rules are determined by `game_engine.py`; the flag, a
  no-show for the first move (30 s) and an abandoned game (the player disconnected for 3 minutes) are handled by the
  `check_timeouts_loop` cycle, run by a single leader process. Only one of the claimants can finish the game
  (`claim_game_end`). The result is written by `finish_game`: rating, archive, anti-cheat telemetry, arena points,
  position index and review — in the background.
- **Rating.** Separate for bullet, blitz, rapid and classical; the rating category is determined by the estimated
  duration "base + 40 × increment" (boundaries 3, 8 and 25 minutes). The Elo formula, K = 40 for the first 30 games in
  a category, then 20, from 2400 — 10.
- **Tests.** `game_state`, `game_moves_server`, `game_end_atomicity`, `game_end_reconciliation`, `disconnect_clock`,
  `timeouts_loop`, `multiworker`, `matchmaking_rules`, `rating_categories`, `casual_games`, `odds_pvp`,
  `chess960_pvp`, `ws_rate_limit`, `ws_db_sessions`, `arena_berserk_lag` (lag quota); browser —
  `e2e/pvp-game.e2e.ts`.

### 4.3. Fair play and anti-cheat

- **The rule.** During their own rated game the player gets no evaluations or engine moves from the server: all such
  endpoints are guarded by the dependency `forbid_engine_help_during_game` (`src/api/fair_play.py`). The list of
  endpoints — `CLAUDE.md`, rule 2. A request without a token from an address from which someone is currently playing
  is also refused.
- **Anti-cheat** (`src/services/anticheat.py`). After the game, a penalty to the player's trust factor
  (`users.trust_factor`, starting at 100) is computed from the move telemetry: an even "machine" rhythm of moves by the
  server's clock is the main signal, window focus loss only strengthens it. Below 30 — the `is_cheater` flag and a
  review request to the moderator; a human decides (`src/services/moderation.py`), and the player may file an appeal.
- **Move telemetry** (the `moves` table) is only a buffer for the anti-cheat: the per-side summary is written at once to
  `games.telemetry_summary`, and the raw rows are deleted by the scheduled task `archive_move_telemetry` 90 days after
  the game (the appeal period, `src/services/telemetry_retention.py`).
- **Tests.** `fair_play`, `anticheat`, `engine_endpoints`, `moderation`, `telemetry_retention`.

### 4.4. The Stockfish engine

- **The rule.** The engine is called only through `get_engine_pool(path).acquire()` (`src/services/engine_pool.py`): no
  more than `ENGINE_POOL_SIZE` processes; a request over the limit waits and gets a "pool busy" refusal, not a new
  process.
- **Who uses it.** A bot's move, game review, the mentor, "find the mate", tournament simulation, puzzle checking.
  Working time by kind — the metric `regence_engine_seconds_total{kind}`.
- **There is no engine in tests and CI:** calculations are checked on mocks or on a static analyser with a fixed seed.
- **Tests.** `stockfish_engine`, `engine_budget`, `engine_info`.

### 4.5. Game review and the mentor

- **What.** Review of a whole game (accuracy, mistakes, evaluation graph), an explanation of a move in words, a hint by
  steps, playing with the mentor (every one of your moves is checked), the game summary, "I disagree" with an
  evaluation.
- **Files.** `src/api/analysis.py`, `src/services/analysis_service.py` (engine evaluation of every move),
  `mentor_service.py` (rule-based motif detector, no engine), `positional.py` (positional features), `coach.py`
  (assembly of the explanation), `move_check.py` (move check and evaluation cache), `game_summary.py`; client —
  `components/GameViewer.tsx`, `chessboard/CoachPanel.tsx`, the hook `useCoachMode.ts`.
- **Where the text comes from.** The server returns facts: the motif code, fields, pieces, the template key. The client
  assembles the sentence from the `coach.*` catalog. The detector's main principle: a false explanation is worse than
  silence.
- **The "club coach" after a game.** In the game summary (`chessboard/GameSummaryPanel.tsx` → `CoachCards.tsx`) up to
  three cards: a puzzle from the player's costliest mistake (solved right in the panel), a deviation from the
  repertoire (train it or add a reply), a Grand Course lesson on the theme of the mistake. The server assembles the
  ready parts without the engine (`src/services/coach_cards.py`, `GET /learn/after-game/{id}`: the `personal_puzzles`
  table, the player's repertoires); the client picks the course module for the theme (`services/coachCards.ts`, data in
  `content/supercourse.ts`).
- **Tests.** `analysis_service`, `mentor_motifs`, `mentor_pins`, `positional`, `coach`, `coach_mode`, `game_summary`,
  `coach_cards`; client — `CoachCards.test.tsx`.

### 4.6. Bots

- **Who there is.** Seven historical bots of the first wave (Philidor … Zukertort, `src/services/bots/<name>.py`),
  masters of the second wave (`masters.py`; in all, bots with an opening book — 22), masters of the past for the "Time
  Machine" (`guests.py`, 230 people), fictional archetypes of the workshop (`archetypes.py`, 22) and opponents the
  player assembles from sliders (`personality.py`, the `bot_personalities` table). Numbers as of 17.11.2026.
- **How a bot chooses a move** (`bots/base.py`, `style.py`). The position evaluation comes only from Stockfish (up to 8
  best lines). Style does not change the evaluation: it awards bonuses to candidates within a window around the best
  move and so chooses "to taste". In the opening the bot plays from a book built from its prototype's games. Strength
  is limited through `UCI_Elo`, below 1320 — by controlled mistakes. "Thinking" time is simulated.
- **Strength** is measured: `scripts/calibrate_bots.py` plays matches against Stockfish references and writes
  `calibration.json`. **Memory** (`memory.py`): results of its own openings and a rating from games against humans.
  **Self-play** (`selfplay.py`, a beat task every 6 hours): archetypes adjust their spread to the declared strength,
  each step recorded in the public log `bot_tuning_log`.
- **Tests.** `<name>_bot` for each historical bot, `style_presets`, `personality_bot`, `bot_strength`,
  `bot_memory`, `bot_selfplay`, `masters`, `masters_catalog`, `beginner_opponents`.

### 4.7. Ladder, tournaments with bots, the "Time Machine"

- **Ladder** (`src/services/ladder.py`): all historical bots and all archetypes, including opponents for beginners,
  in ascending order of measured strength, and a separate rating. Progress is the steps passed, keyed by opponent key
  (the `ladder_beaten` table); the current step is the first unpassed one above the strongest passed one; a new
  opponent shifts nobody's progress (below a passed one it is "skipped"). The fairness of a game is checked by the
  server: a hint request, a takeback or a substituted opponent — and the game does not count.
- **Tournaments** (`tournaments.py`, rules — `tournament_rules.py`): round-robin (Berger tables) and knockout. Games of
  bots among themselves are played by a separate worker (`tournament_simulation.py`, the `simulation` queue). The result
  of the player's game comes only from the saved played game — it cannot be submitted by hand.
- **Career** (`tournament_career.py`) — a ladder of ready-made tournaments of increasing strength. **"Time Machine"**
  (`time_machine.py`, 50 tournaments) — famous tournaments of the past with the full historical field plus the player;
  the fields and the real results are checked against open sources by the scripts in `scripts/dev/time_machine/` (the
  procedure for adding a tournament — `scripts/dev/time_machine/README.md`). **Legends of the week**
  (`legends_week.py`, task 26.1) — one Time Machine event per ISO week by a fixed rotation over the registry; each player
  plays their own run, the weekly table ranks the best finished run by tournament place (derived from `tournaments`,
  no table of its own); `GET /tournaments/legends-week`, client `components/tournaments/LegendsWeek.tsx`. **Legends
  season** (`legends_season.py`) — the weeks of a calendar month (`league.season_bounds`) add up: points by the weekly
  place (25, 18, 15 … for the top ten) plus one for any finished run; `GET /tournaments/legends-week/season[?season=YYYY-MM]`,
  card `LegendsSeason` on `/time-machine`.
- **Tests.** `ladder`, `tournaments`, `tournament_rules`, `tournament_play`, `tournament_simulation`,
  `tournament_career`, `tournament_big`, `time_machine`, `time_machine_play`, `legends_week`, `legends_season`; browser — `e2e/time-machine.e2e.ts`.

### 4.8. Arenas between humans and conferences

- **What.** Timed tournaments: a player plays game after game against whoever is also waiting. A win is 2 points, a
  draw is 1; after two wins in a row the points are doubled ("fire"). There are also Swiss arenas by rounds.
- **Files.** `src/services/arena.py` (rules), `arena_schedule.py` (schedule), `conferences.py` (conferences),
  `src/api/arenas.py`, `src/api/conferences.py`; client — `components/arena/`.
- **Fair ending.** New pairs are created only until the "last start" (the end minus the game duration), the results
  are final when the last game is finished. A no-show for the first move is a loss; a draw by agreement before move 10
  is 0 points.
- **Entry is open to everyone.** Any registered player can enter any arena: there is no threshold of games played and
  no arenas "only up to such-and-such rating" (owner's decision of 17.11.2026) — a beginner may meet the strongest
  player. Only a player with the unfair-play flag is barred. At 500 participants the next division opens — that is the
  capacity of the table, not a selection.
- **Awards** (`arena_awards.py`, the `arena_awards` table): when the results are final, the top three of the table
  (those who played at least one game) receive places — a notification, trophies in the profile, the achievements
  "arena podium finisher" and "arena winner". They are handed out by the scheduled task `arena_awards` every 5 minutes.
  The arena page gives the podium finisher their place (`me.podium_place`, `arena_awards.place_of`), and any player
  `me.username`; the client shows the results screen once (`TournamentCelebration`: a trophy for the podium finisher, a
  place badge for the others, the table of participants with the player's own row, CSV download).
- **Monthly league** (`arena_league.py`, `GET /arenas/league`, the block under the list on `/arenas`): the sum of arena
  points in a season (a UTC calendar month) per time-control category; Swiss arenas are not included, the categories
  are those where the schedule creates arenas (bullet, blitz). Order: points, best arena, fewer arenas. It is computed
  on request and does not affect the rating.
- **Berserk.** Before one's first move — half the time without an increment; a win brings an extra point.
- **Schedule.** Each of the five conferences has its own time zone, the plan is set in its local time: in the evening
  3+2 blitz every hour, 2+1 bullet and an evening 5+3, at other times — blitz every three hours, plus Swiss arenas.
  Arenas are created on a list request, 6 hours ahead. The start reminder is a beat task once a minute.
- **Conferences.** The player specifies their country themselves (`users.country`); the country determines the
  conference (250 codes in `conferences.COUNTRIES`). The conference is remembered when entering an arena; the 10 best
  players of a conference count toward the arena's score; the Conference Cup is the sum of the arena scores of the
  month. A conference can be changed once a season.
- **Conference matches** (`conference_match_rules.py` — pure rules, the arena format `match` in `arena.py`): every
  Saturday two conferences play a round-robin (10 pairs, the host alternates by round), a shared evening or 19:00 of
  the host. Only players of the two conferences can sign up, up to an hour before the start; at the start the rosters
  are set by rating (`arena_players.board`), two rounds of 5+3 (on a board, with White and with Black), the score — a
  win 1, a draw ½ (`match_view`). Matches are created 8 days ahead (`ensure_schedule`), the list is on `/conferences`,
  the match page is `/arenas/{id}`. There are no trophies for a match.
- **Tests.** `arena`, `arena_swiss`, `arena_fair_end`, `arena_groups`, `arena_berserk_lag`, `arena_schedule`,
  `conferences`, `arena_league`, `conference_matches`. The concept and the owner's decisions — `docs/research/arenas.md`.

### 4.9. Puzzles and trainers

- **Puzzles** (`src/services/puzzles.py`, `src/api/puzzles.py`). The solution is not sent to the client: the server
  stores which move the solver is on, checks every move and replies with the opponent's move. The solver's rating is
  Elo against the puzzle's rating. The source is the open lichess database (CC0), themes are labelled according to the
  `themes.py` registry (127 themes in 12 sections, description — `docs/training/tactical-themes.md`).
- **Own mistakes** (`personal_puzzles.py`): from the review of one's own games, with repetition after 1, 3, 7 and 21
  days.
- **Defence** (`defense_drills.py`), **generator exercises** (`drill_generator.py`, `generated_drills.py` — positions
  are built from a seed and verified by exhaustive search), **mating patterns** (`mate_course.py`, `mate_patterns.py`),
  **"Guess the master's move"** (`guess.py`, position selection — `guess_selection.py`), **miniatures** and
  **"Recognise the structure"**.
- **"Plan in this position"** (trainer `position_plan`, 27.9): a prepared set `frontend/src/content/positionPlans.json`
  of master-game positions with three concrete plans (category + first move); the set is mined and checked by the
  engine offline (`scripts/dev/build_position_plans.py`), the client only shows it (`frontend/src/trainers/positionPlans.ts`,
  `components/trainers/PositionPlanQuiz.tsx`).
- **Trainers for vision, memory and calculation** are computed on the client (`frontend/src/trainers/`), the server
  stores the results (`src/api/trainers.py`, the `trainer_results` table); educational mini-games — `mini_games.py`;
  with a friend by link — the rooms of `mini_game_rooms.py` (Redis, polling once a second,
  `/train/games/room/{code}`).
- **Tests.** `puzzles_api`, `puzzles_data`, `themes`, `theme_training`, `theme_detectors`, `personal_puzzles`,
  `defense_drills`, `generated_drills`, `mate_course`, `mate_patterns`, `guess_api`, `guess_selection`, `trainers`,
  `mini_games`, `mini_game_rooms`, `miniatures`, `structure_quiz`, `position_plans`; browser — `e2e/puzzles.e2e.ts`,
  `puzzle-moves.e2e.ts`.

### 4.10. School, the Grand Course, the training plan

- **Lessons** are client data files: `frontend/src/content/lessons/*.json` (format — `format.ts`, validation —
  `validate.ts`, the course list — `courses.json`), components — `components/learn/`. The server stores only progress
  (`lesson_progress`). The legality of the lessons' moves is checked by a client test, the answers are checked against
  the engine by `scripts/verify_lessons.py`.
- **The Grand Course** (`content/supercourse.ts`, concept — `docs/research/supercourse.md`): levels 0–5 by rank and
  branch; a course step leads into an already existing section. A "game with stops" step opens one master game of the
  classics collection (`{kind: 'classics', id}` → `/learn/classics/<id>`) and is credited by its `classics-<id>`
  progress record once the game is played to the end. A "demo" step (`{kind: 'classics', id, demo: true}` →
  `/learn/classics/<id>?stops=off`) opens the same game without questions and is credited the same way. Games of the
  collection are built by `scripts/build_classics.py`: from the champions' archive, or chosen ones from the game library
  (`--library <moves_hash>`) or a PGN file (`--pgn`) with stops found by the "Guess the move" selection.
  Level exams — `level_exam.py`, diagnostics — `exam.py`.
  **Auto-credit:** `GET /learn/course-progress` (`src/services/course_progress.py`) collects what has been done against
  the standards (`lesson_progress` records, the `theme_progress` theme steps, `trainer_results` attempts, `exam_results`
  grades); the client (`services/courseProgress.ts`) matches it against the module's steps and closes the module by
  itself. Only modules without verifiable steps are marked manually.
- **Personal coach:** the skill map (`skills.py`), the daily warm-up (`workout.py`, the reminder is a beat task at 16:00
  UTC), training programmes (`content/programs.ts`). There are no new tables: everything is computed from data already
  collected.
- **Tests.** `learn_progress`, `course_progress`, `exam`, `level_exams`, `skills`, `workout`; client —
  `courseProgress.test.ts`, `SupercoursePage.test.tsx`; browser — `e2e/course-library.e2e.ts`.

### 4.11. Openings

- **The opening table** (`openings.py`, data `openings.tsv`): an opening is identified by the position, so transpositions
  are recognised. **The position index** (`position_index.py`): the first 30 plies of every finished game — into
  `position_stats` and `position_games`; library games — only into `position_library_games` (examples, no statistics).
  **The explorer** (`opening_explorer.py`) — moves from a position with statistics and masters' games: the archive and
  the public library collections; a duplicate (the same surnames and year) is shown once — as a library game. A library
  example carries its structure and theme marks (27.5); the client links them to `/library?structure=` / `?theme=`.
- **The repertoire** (`repertoire.py`, `repertoire_drill.py`, `repertoire_deviations.py`, `repertoire_starters.py`):
  one's own lines as a graph of positions, scheduled repetition by SM-2, playing against the repertoire, review of
  deviations in a played game.
- **Tests.** `opening_explorer`, `explorer_library`, `position_index`, `repertoire`, `repertoire_drill`,
  `repertoire_deviations`, `repertoire_advanced`.

### 4.12. Archive, library, viewing, import

- **The champions' archive** — historical games from PGN (`src/db/seed.py`); their players are stored in `users` with
  the `is_bot` flag and without `username_key`. **"Watch"** (`src/api/watch.py`): games in progress, the archive with
  filters, "Game of the day", "fun collections" (`collections.py`, the table is filled by
  `scripts/build_collections.py`).
- **The game library** (`library.py`): a tree of collections, visibility (public, owner's, service). On import only the
  headers and the main line are taken — comments and variations from editions are not. Pawn structure markup —
  `pawn_structures.py`; theme marks (tactics that won material, from the mentor's static motif detector, no engine) —
  `game_themes.py`, column `library_games.themes`, filter `theme` of `GET /library/games`. The rules for working with materials — `docs/research/books-library-review.md`, annotations —
  `docs/research/library-annotations.md`.
- **Import of one's own games** from lichess and chess.com (`game_import.py`): by nickname through open APIs or by
  pasting PGN; the opt-in daily import (`game_import_schedule.py`, table `import_subscriptions`, the hourly beat task
  `import_subscriptions`) fetches the player's new games once a day. Ordinary chess and Chess960 are imported: a
  Fischer game is stored with `Variant "Chess960"`, reviewed by the engine in 960 mode, replayed by the server for the
  960 viewer (`GET /imports/games/{id}/chess960`, page `/import/game/:id/960`, `Chess960Archive`), and gives personal
  puzzles only from positions without 960 castling rights (`personal_puzzles.readable_as_standard`).
- **Tests.** `library`, `library_text`, `library_annotations`, `pawn_structures`, `game_themes`, `cbh_reader`, `watch`,
  `game_import`, `game_import_schedule`, `pgn_normalization`.

### 4.13. Social

- **Players and notifications** (`src/api/social.py`, `notifications.py`): search, follows, a challenge to a game, the
  notification centre (a database record and delivery to open tabs over the WebSocket).
- **Direct messages** (`direct_messages.py`), **the feed** (`feed.py`), **attachment cards** (`attachments.py` — the
  server checks the link and stores a snapshot of the data as of the moment of sending).
- **Respectful communication** (`civility.py`): a dictionary filter before sending, holding, quotas for beginners and
  offenders. The automation only flags — the moderator decides (`moderation.py`, the `/moderation` page).
- **Joint review** (`study_room.py`): a room in Redis, the host controls the board. **Teams and the league**
  (`league.py`): a season is a calendar month, points are for games between players of different teams.
- **Achievements** (`achievements.py`) — only for real results, computed from data already available.
- **Tests.** `social`, `direct_messages`, `feed`, `civility`, `moderation`, `study_room`, `league`, `achievements`.

### 4.14. Languages, appearance, the phone app

- **Three languages** (en, uk, ru). Not a single player-facing string in the server code or in component markup: the
  server returns codes, the client returns texts from the catalogs. This is checked by the tests `no_russian_in_api`,
  `error_codes`, `bot_content_keys` and the catalog tests on the client (identical keys and parameters in all three
  languages).
- **Appearance:** boards, piece sets, theme bundles, backgrounds, sounds (`frontend/src/config/boardAppearance.ts`,
  `themePresets.ts`, `services/soundEngine.ts`). Every asset has a free licence and an entry in `ATTRIBUTION.md` (test
  `assets_licensing`).
- **Installation on a phone:** a service worker and a manifest (`services/pwa.ts`, `public/sw.js`).

### 4.15. System monitoring and the beta

- **"My week"** (`src/services/weekly_summary.py`, `GET /workout/week`): the results of 7 days by games, puzzles and
  days of activity, and advice as a code; client — `components/WeekSummaryCard.tsx` under the warm-up plan.
- **The timed-run leaderboard** (`src/services/puzzle_leaders.py`, the `puzzle_timed_scores` table): the weekly standing
  and records (`users.puzzle_best_3/5`), `GET /puzzles/timed/leaders`; filled in `puzzles.finish_run`.
- **The violations summary** (`src/services/moderation_report.py`, `GET /moderation/summary`, moderator only): reports
  over 30 days by kind and decision, the queue, offenders, frequent complaints; client —
  `components/social/ViolationsSummary.tsx`.
- **Alerts** (`ops/prometheus/alerts.yml`): Prometheus rules on the metrics of `observability.py` (including the length
  of the Celery queues `regence_celery_queue_length`), connected at deployment (`DEPLOY.md`, section 6).
- **Logs** (`src/core/logging_setup.py`, `src/api/client_errors.py`, `scripts/trace_logs.py`; client —
  `services/breadcrumbs.ts`, `services/clientErrors.ts`): JSON lines with the context `request_id` / `user_id` /
  `game_id`, an end-to-end request number client ↔ API ↔ worker, page reports of errors and reloads with a trail of
  events.
- **Errors and metrics** (`src/core/observability.py`): Sentry when `SENTRY_DSN` is set, Prometheus metrics at
  `/metrics` (not published externally). **Product metrics** without third-party trackers (`product_metrics.py`, the
  report — `scripts/product_metrics.py`). **Transparency:** the bot calibration logs and the open API
  (`src/api/public.py`).
- **The beta** (`beta.py`): invitation codes, "Report a problem", the weekly summary.
- **Tests.** `observability`, `product_metrics`, `public_api`, `beta`, `deploy_config`.

## 5. Background and scheduled tasks

The tasks — `src/worker/tasks.py`, the queues and the schedule — `src/worker/celery_app.py`.

| Task | Queue | When |
|---|---|---|
| `analyze_game`, `analyze_imported_game` | `analysis` | after a game finishes or an import |
| game position index | `analysis` | after a game finishes |
| `simulate_tournament_game` | `simulation` | bot games in a tournament |
| `workout_reminders` | `analysis` | beat, once a day at 16:00 UTC |
| `bot_selfplay` | `simulation` | beat, every 6 hours |
| `arena_reminders` | `analysis` | beat, every minute |
| `legends_week_start` | `analysis` | beat, Monday 08:11 UTC |

Enqueueing a task from the API does not wait for the broker (`src/services/task_dispatch.py`): the game result is
broadcast at once, and if the broker is unavailable the review can be computed later with a button on the game page.

## 6. The client

- `frontend/src/App.tsx` — the header, the menu and all routes (about 60 of them).
- `components/Chessboard.tsx` — the main board: a game with a human, with a bot and free analysis; the logic is moved
  out into the hooks in `components/chessboard/hooks/`. A game with a bot survives a reload: a snapshot in
  `localStorage` (`services/botGameSnapshot.ts`, key `regence_bot_game`, valid for a day, only for the same player) is
  written after every move and when the page is closed, and when the board is opened the game continues with the clocks
  reduced by the reload time. In a casual game with a bot there is a pause (the clocks stop, the bot does not move, the
  position is hidden; stored in the snapshot as `paused`); in a ladder or tournament game there is no pause, and there
  is no cancelling of a game with a bot at all. On the left — the "New game" button (a step-by-step window
  `chessboard/NewGameDialog.tsx`: opponent, time, start), the game in progress, the bot opponent, tournaments and the
  lobby; on the right — the tabs "Moves / Chat / Mentor / X-ray". Accessibility (26.3): squares are buttons with a
  label, moves from the keyboard (Tab to the board, arrows, Enter/Space), moves are announced in words in a live region
  and there is "Position in words" (`chessboard/BoardSpeech.tsx`); the words — `services/a11y/speech.ts` (keys
  `a11y.*`). In blindfold play hidden pieces are not named.
- `components/ui/` — shared design components (page, cards, buttons, labels, tabs, window); rules —
  `docs/design-system.md`, showcase — `/design`.
- `components/<section>/` — section pages; `services/<section>.ts` — calls to that section's API, all through
  `services/http.ts` (profile — `profile.ts`, account — `account.ts`, game viewing and review — `analysis.ts`, ladder —
  `ladder.ts`, Fischer random chess — `chess960.ts`, exams — `exam.ts`); shared rules without the network also live
  here: the game date `gameDates.ts`, move numbering `moveNumbers.ts`; board keyboard —
  `chessboard/hooks/useBoardKeyboard.ts` (the main board and the puzzle boards), game chat — `chessboard/gameChat.ts`
  (the main board and the 960 game); text limits — `config/textLimits.ts`; `config/` — appearance and bot data;
  `content/` — educational content; `trainers/` — trainer logic.
- `i18n/` — the three message catalogs and the translation functions; `test/` — shared test fixtures.

## 7. Rules that must not be broken, and how they are checked

| Rule | Check |
|---|---|
| Not a single player-facing string on the server or in component markup | `tests/test_language_policy.py`, the client catalog tests |
| The server's error codes and the client catalogs match | `tests/test_error_codes.py` |
| Engine endpoints are closed during a game | `tests/test_fair_play.py`, `test_engine_endpoints.py` |
| The engine only through the pool, with a process limit | `tests/test_engine_endpoints.py`, `test_engine_budget.py` |
| Models and migrations match | `alembic check` in CI |
| Assets have a free licence and an entry in `ATTRIBUTION.md` | `tests/test_assets_licensing.py` |
| The layout does not break on a phone and in two languages (en, uk) | `frontend/e2e/layout.e2e.ts` |
| Entry to an arena is open to any registered player (no selection by strength) | `tests/test_arena_groups.py` |

## 8. How to check for yourself

    uv run python project_status.py                 # summary: git, plan, migrations, bot calibration
    uv run ruff check . --quiet                     # linter
    uv run mypy                                     # type check
    uv run python -m pytest -q --tb=short           # all server tests (no engine or network needed)
    uv run pytest tests/test_arena.py -q            # one section: the test name is from §4
    cd frontend && npm run lint && npx vitest run --reporter=dot && npm run build

To trace a section from the button to the database: open its page in `frontend/src/components/`, find the call in
`frontend/src/services/`, by the address find the route in `src/api/`, by the route find the service in
`src/services/`. At the top of each service it is written by which rules it works and where it takes its data from.
