# regence: architecture and project rules

## Language policy (owner decision of 23.11.2026 — applies to everything, always)
- **Only two languages: English (primary) and Ukrainian.** The site's default language is English; the client has
  exactly two catalogs, `en` and `uk`. **Russian must not appear anywhere** — not in the UI, content, code, comments,
  docs, tests, data or scripts. Chinese and Hindi may be added later (keep the language list data-driven:
  `frontend/src/i18n/core.ts` and the server's `LANGUAGES` constants), but nothing is built for them now.
- **The owner writes to you in Russian; you implement everything immediately in English and Ukrainian.** Never
  answer in, translate into or store Russian in the project. Chat replies to the owner stay in Russian (that is
  the conversation, not the project).
- **English everywhere in the repository:** code, identifiers, comments, docstrings, commit messages, PR texts,
  test names, technical docs (`docs/ARCHITECTURE.md`, `DEPLOY.md`, `WORKFLOW.md`, `ATTRIBUTION.md`, `docs/research`,
  this file).
- **Ukrainian for the files the owner reads fast while developing:** `README.md`, `ToDo.md`, `TodoMe.md`,
  `docs/owner-decisions/` (the owner's decision papers). When you add a line to them, write it in Ukrainian
  (keep the English primary names of code, files and commands as they are).
- **Player-facing text:** lessons, explanations, UI strings — `en` is the source, `uk` the translation, both always
  complete. No other language keys in lesson/content JSON.
- **Guard:** `tests/test_language_policy.py` fails on Russian-only letters (yo, hard sign, yery, reversed e) anywhere in tracked text and on
  any Cyrillic in code files (`*.py`, `*.ts`, `*.tsx`, except the Ukrainian catalog and content).

## 0. Session protocol (save tokens — always follow)
**Session start:**
1. Read ONLY the first ~40 lines of `ToDo.md` (the "▶ Now" block). Do not read the whole `ToDo.md` unless asked.
2. For the overall picture use `python project_status.py` and `docs/ARCHITECTURE.md` (sections → files → data →
   tests); do not re-read modules just for an overview.
3. Read files from the module map (section 3) directly. For large files, read the needed line range only.
4. For wide searches across many files ("where is X used", "find all places of Y") use the Explore subagent: the
   main context should receive the result, not the file contents.
5. When calling the Task tool (subagents) for reading, searching and cross-checking comments, always pass
   `model="sonnet"` explicitly.

**While working:**
- Do not re-read a file you already read in this session unless it changed.
- Do not print whole files in answers; show only changed fragments.
- Tests: first targeted (the needed file/test); full run only before the commit.
- Do not edit this `CLAUDE.md` in the middle of a session unless asked (it resets the prompt cache).

**Finishing a task (mandatory before /clear):**
1. Rewrite the "▶ Now" block at the start of `ToDo.md` (≤ 15 lines, Ukrainian).
2. Move the task result as one entry into the "Done" part of the matching `ToDo.md` section.
3. Update descriptions: the docstring of the changed module, and, if the behaviour of a section, a setting or the set
   of modules changed, `docs/ARCHITECTURE.md`, `DEPLOY.md` / `.env.example` and the module map below (rule 6).
4. Commit with a clear message; then a pull request into `dev`, green CI, merge (`WORKFLOW.md`, step 5).

## Compact instructions
On /compact or auto-compaction keep: the current task goal, the list of changed files, decisions and their reasons,
the latest test errors (error text only) and the next step. Drop: full test and command outputs, contents of files
that were read, intermediate diffs, rejected options.

## 1. Stack and running checks (save output tokens!)
- Backend: Python 3.14, FastAPI, SQLAlchemy 2.0 (asyncpg), Redis 7.4, Celery, python-chess, Stockfish 19.
- Frontend: React 19, TypeScript, Vite 6, Tailwind CSS v4, chess.js, Vitest, Playwright.
- Check commands (ALWAYS quiet, so the context is not flooded):
  - Environment: `uv sync` (Python 3.14 from `.python-version`, packages strictly from `uv.lock`); run the commands
    below through `uv run`.
  - `uv run ruff check . --quiet`
  - `uv run mypy` (print only errors; for long output `mypy | tail -30`)
  - `uv run python -m pytest -q --tb=short --no-header` (or targeted: `uv run pytest tests/test_xxx.py -q --tb=short`)
  - `cd frontend && npm run lint && npx vitest run --reporter=dot`
  - Before pushing a branch with client changes run `npm run build`: only it catches type errors.
  - Playwright locally only on explicit request (in CI it runs on the built images).

## 2. Hard project invariants (the rules of Part II of ToDo.md)
1. **Two languages (en / uk):** NOT ONE player-facing string in server or JSX code. The server returns codes
   (`src/core/errors.py`, `coach.*`, `botComments.*` keys, theme codes); the client builds the text from
   `frontend/src/i18n/messages/{en,uk}.ts`. Keys and parameters in both catalogs must match.
2. **Fair play:** endpoints with engine evaluation/moves (`/analysis/*`, `/bots/move`, `/bots/custom-move`,
   `/bots/draw-offer`, `/chess960/move`, `/chess960/bot-move`, `/repertoires/{id}/opponent`) are guarded by the
   `forbid_engine_help_during_game` dependency (`src/api/fair_play.py`) during a PvP game and are marked in ladder and
   tournament sessions (`src/services/ladder.py`, scopes `ladder` and `tournament`).
3. **Engine budget:** Stockfish is called ONLY through `get_engine_pool(path).acquire()`
   (`src/services/engine_pool.py`). CI tests do not use the binary — test with mocks or the static analyzer with a
   fixed seed.
4. **Database:** create Alembic migrations ONLY when `src/models/` changes — `alembic revision --autogenerate` or by
   hand following the neighbours (CI applies them to an empty database and compares with the models:
   `alembic check`); there is exactly one migration head. In WebSocket code (`src/api/websockets.py`) use short
   sessions per action (`ActionContext.release_db` before sending to the network).
5. **Content cleanliness:** no names of third-party commercial programs from the 2000s, their personalities or copied
   texts. Every asset must have a free licence and an entry in `ATTRIBUTION.md`.
6. **Descriptions:** the owner reviews the project through documentation and comments. Every module has a docstring
   (in client files — a comment at the top): what it does, by which rules and where it takes data from (table, file,
   setting, external source). If you change behaviour, fix the description in the same pull request. Comments are in
   **English**; they must not contain player-facing strings, but rule 1 also applies to `assert` and exception
   messages.
7. **Openness (owner decision of 17.11.2026):** no splitting of players by strength. Any registered player may enter
   any tournament and any arena; any player may challenge any other. Do not add rating or game-count thresholds or
   "only for peers" tournaments. The only restriction is fair play (the `is_cheater` flag). Pairing by closeness of
   points and rating inside an arena and the own rating range of a player challenge are not a ban but an order of
   choice.

## 3. Map of key modules (read the needed file directly, do not search again)
- **State and plan:** `python project_status.py` (summary), `ToDo.md` (the "▶ Now" block at the start + "Done/Left"
  sections), `docs/ARCHITECTURE.md` (structure by sections).
- **Bots and style:** `src/services/bots/base.py` (`HistoricalBot`, strength window around
  `strength_reference_move`), `style.py` (rules `Rule/Group/FirstOf`), `personality.py` (`BotPersonalityConfig`,
  `ERROR_RATE_CURVE`), `archetypes.py`, `calibration.py` + `calibration.json`.
- **Mentor and tactics:** `src/services/mentor_service.py` (detector of 20 motifs + SEE), `positional.py`
  (positional features), `coach.py` (template and arrow assembly), `move_check.py` (move check + Redis cache),
  `themes.py` (registry of themes in sections A–L, the `goal` of a theme).
- **Puzzles and trainers:** `src/services/puzzles.py`, `personal_puzzles.py`, `defense_drills.py`,
  `drill_generator.py`, `generated_drills.py`, `mate_patterns.py`.
- **Tournaments and ladder:** `src/services/tournaments.py`, `tournament_rules.py`, `tournament_simulation.py`
  (Celery queue `simulation`), `tournament_career.py`, `time_machine.py`, `ladder.py`.
- **Arenas and conferences:** `src/services/arena.py` (rules, points, berserk, reminders), `arena_schedule.py`
  (schedule by conference), `conferences.py` (countries, standings, Cup), `src/api/arenas.py`,
  `src/api/conferences.py`; frontend `components/arena/`, `services/arenas.ts`, `services/conferences.ts`. The
  design — `docs/research/arenas.md`.
- **Communication:** `src/services/notifications.py`, `direct_messages.py`, `feed.py`, `attachments.py`,
  `civility.py`, `moderation.py`, `league.py` (teams), `study_room.py`; frontend `components/social/`.
- **Background tasks:** `src/worker/tasks.py`, `src/worker/celery_app.py` (queues `analysis` / `simulation`, beat
  schedule), enqueueing from the API — `src/services/task_dispatch.py`.
- **PvP and WebSocket:** `src/api/websockets.py`, `src/services/game_state.py` (atomic moves in Redis, clocks and
  lag quota, `game_deadlines`, `reconcile_unfinished_games`), `matchmaker.py`, `connection_manager.py`, `rating.py`,
  `anticheat.py`.
- **Frontend — board core:** `frontend/src/components/Chessboard.tsx`, hooks in `chessboard/hooks/` (`useClock.ts`,
  `usePremoves.ts`, `useBotGame.ts`, `useCoachMode.ts`, `useGameSocket.ts`, `useBoardKeyboard.ts` — keyboard play),
  `chessboard/annotations.tsx`, `chessboard/AuxBoard.tsx`, `chessboard/gameChat.ts` (game chat), `GameViewer.tsx`.
- **Frontend — network and tests:** a component calls `services/*.ts`, and a service reaches the server only through
  `frontend/src/services/http.ts` (`apiRequest` / `apiFetch`; there is no own `fetch` anywhere); in tests a move is
  made by clicks through `frontend/src/test/boardMoves.ts`.
- **Library, course, repertoire:** `src/services/library.py` (PGN import, `repair_text`, `ends_in_mate`),
  `pawn_structures.py`, `cbh_reader.py`, `structure_quiz.py`, `miniatures.py`, `repertoire*.py`; frontend
  `content/supercourse.ts`, `content/mustKnow.ts`, `components/learn/SupercoursePage.tsx`, `components/library/`,
  `components/repertoire/`.
- **Frontend — sections:** `components/puzzles/` (`PuzzlesPage.tsx`, `PuzzleBoard.tsx`, `DefenseTrainer.tsx`,
  `GeneratedDrills.tsx`, `TrainingPanel.tsx`, `SolutionReplay.tsx`), `components/learn/` (`LearnPage.tsx`,
  `LessonPlayer.tsx`), `components/tournaments/`, `components/xray/` + `services/xray/xrayUtils.ts`.

## 4. Development rules (owner requirement of 17.11.2026 — follow in every task)
- **Single responsibility (SOLID).** A route in `src/api/` only validates input, the limit and fair play and calls a
  service; rules and calculations live in `src/services/`; pure rules without a database or network go into a
  separate module (like `tournament_rules.py`, `arena_schedule.py`) so that a simple test checks them. A component
  renders, a hook or `services/*.ts` talks to the network.
- **Extend with data, not by editing many places.** A new kind of anything is an entry in a registry
  (`ACTION_HANDLERS`, `themes.py`, `COUNTRIES`, `DAY_PLAN`, `beat_schedule`), not a new `if` branch in several files.
- **Do not repeat yourself (DRY).** Before writing, find what exists: error codes (`src/core/errors.py`), limits
  (`src/api/rate_limit.py`), the engine pool, `season_bounds`, `classify_time_control`, `berserk_fields` and so on.
  If something repeats a second time, move it to a shared function and call it from both places. One source of
  truth: the server computes, the client shows.
- **Comment the "why" and the "where from".** A docstring on every new module, class and public function (rule 6);
  a constant — what it means and what it affects; a non-obvious decision — the reason. Do not paraphrase code and do
  not leave stale comments: if behaviour changed, fix the description.
- **No magic numbers and no dead code.** Rule numbers are named constants at the top of the module; installation
  settings go to `src/core/config.py` and `.env.example`. Delete unused code, do not comment it out.
- **Errors explicitly.** A refusal is a code from the registry with parameters, not a string and not a silent
  `except`; catch an exception only where it is clear what to do with it, and log it with context.
- **Tests together with code.** New behaviour — a test of the client's real path (an HTTP request or a WebSocket
  message) plus a test of the pure rules; fix time and randomness in tests (clock substitution, seed) instead of
  relying on machine speed. A found bug — first a test that catches it.
- **Small steps.** One task — one branch and one pull request; fix an incidental finding outside the task in a
  separate pull request or record it in `ToDo.md`.
- **Security and personal data.** Validate player input on the server; secrets only in `.env`; erase personal data
  (e-mail, country) on account deletion (`src/services/account.py`) and do not send it outside.
