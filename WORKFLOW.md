<!-- --- FILE: WORKFLOW.md --- -->

# Development and Git Process Regulations (Regence Workflow)

A step-by-step cheat sheet for working on every new task in the project.

---

## 1. Project branch layout

1. `master` — **Release branch (Production).**
    * Only verified, fully working code lives here.
    * We never write code directly in `master`. It is updated only by merging from `dev`.

2. `dev` — **Main development branch (Integration).**
    * The base into which all finished features and fixes are merged.
    * All new branches are created from `dev` and merged back into `dev` when finished.

3. Working branches — **branches for a specific task**; the task name from `ToDo.md` is recorded next to it.
    * `feat/name` — new functionality or an interface improvement (for example, `feat/arena-schedule`);
    * `fix/name` — a bug fix (for example, `fix/timer-sync`);
    * `content/name` — chess content: lessons, "Time Machine" tournaments, texts;
    * `docs/name` — documentation;
    * `chore/name` — infrastructure, tests, CI;
    * `perf/name` — performance and database queries.

A task reaches `dev` through a **pull request (PR)** after a green CI — step 5.

---

## 2. Step-by-step procedure for working on a new feature (start to finish)

### Step 1. Creating a branch before starting work

Always start a new task in the project root folder `regence` by switching to `dev` and creating a new working branch:

    git checkout dev
    git pull origin dev
    git checkout -b feat/task-name

*(If you forgot to create a branch and have already started changing files directly in `dev`, just run
`git checkout -b feat/task-name`, and all uncommitted changes will move to the new branch automatically).*

---

### Step 2. Writing code and the DB migration rule (Alembic)

IMPORTANT RULE ABOUT THE DATABASE:

* If you changed **only the frontend** (`frontend/...`), styles, WebSocket logic or Python services without changing
  the DB tables — **Alembic migrations are NOT needed**.
* A migration is created **ONLY** when you changed or added columns/tables in the `src/models/` folder. In that case
  run:

  alembic revision --autogenerate -m "description_of_model_changes"
  alembic upgrade head

* If no running database is at hand, a migration can be written by hand following the pattern of the neighboring files in
  `migrations/versions/` (`down_revision` is the current head, shown by `alembic heads`). An error in such a migration
  will be caught by CI: it applies all migrations on an empty database, compares the result with the models
  (`alembic check`), rolls back to the start and applies them again.
* There must be a single migration head: `alembic heads` prints exactly one line.

---

### Step 3. Local check before committing

1. If Python code changed (from the project root):

   uv sync                               # environment from uv.lock (ruff, mypy, pytest-cov inside)
   ruff check .                          # linter (rules in pyproject.toml), any finding fails CI
   mypy                                  # type check of src/
   python -m pytest --cov                # tests and coverage (threshold in pyproject.toml)

   Integration tests (`tests/integration`) run only when `TEST_DATABASE_URL` and
   `TEST_REDIS_URL` are set and **drop all tables** in the given database — use a separate database, not the working one:

   docker compose exec db psql -U regence_user -d regence_db -c "CREATE DATABASE regence_test"
   $env:TEST_DATABASE_URL = "postgresql+asyncpg://regence_user:regence_password@localhost:15432/regence_test"
   $env:TEST_REDIS_URL = "redis://localhost:6379/15"
   python -m pytest tests/integration

2. If React/TypeScript code (the frontend) changed:

   cd frontend
   npm run lint
   npm run test
   npm run build
   cd ..

---

### Step 4. Committing changes to the working branch

Make sure with `git status` that no temporary files got into the list, and record the changes:

    git status
    git add .
    git commit -m "feat: short description of the completed task"

Commit prefixes:

* `feat:` — a new feature or an interface improvement
* `fix:` — a bug fix
* `refactor:` — code refactoring
* `perf:` — speed-ups and query optimization
* `chore:` — infrastructure, configs, dependencies
* `docs:` — documentation (`README.md`, `QUICKSTART.md`, `WORKFLOW.md`, `ToDo.md`, `docs/`)
* `content:` — chess content (lessons, tournaments, catalog texts)
* `test:` — tests only

The scope in parentheses and the task number at the end follow the history: `feat(arenas): berserk and a lag quota (33.3)`.

---

### Step 5. Pull request into `dev`

When the task is verified and the local checks pass:

    git push -u origin feat/task-name
    gh pr create --base dev --title "feat(scope): what was done (task number)" --body "..."
    gh pr checks <number> --watch

The PR triggers the `Regence CI` pipeline of three checks: server (linter, types, tests, migrations), client
(linter, tests, build) and a build of the production images with browser scenarios (Playwright). Merge only when
all three are green:

    gh pr merge <number> --merge

After the merge, CI runs once more, now on `dev` — wait for it as well: `gh run list --branch dev --limit 1`.
If `dev` has moved ahead in the meantime, pull it into your branch before merging: `git merge origin/dev`.

Before finishing the task: rewrite the "Now" block at the top of `ToDo.md` (no more than 15 lines), mark the task as
done and describe in one "Done" entry what was done and where.

---

### Step 6. Releasing a stable version to `master`

Performed when a logical stage (or sprint) is complete in `dev` and everything works stably:

    git checkout master
    git pull origin master
    git merge --no-ff dev -m "Release: merge stable dev into master"
    git push origin master
    git checkout dev

*(The last command `git checkout dev` is mandatory, so that you never stay on the `master` branch).*

---

## 3. Working from several hosts (gaming laptop, desktop PC, work laptop)

Code is synchronized through GitHub, and everything that is not in git (venv, `node_modules`, Stockfish, PGN archives,
the dev DB schema) is restored by the script `scripts/sync_host.ps1`. There is one rule: **arrive — sync,
leave — push**.

    .\scripts\sync_host.ps1            # arrived: git pull, dependencies, Stockfish, Docker, migrations, PGN
    .\scripts\sync_host.ps1 -Resume    # the same + continue unfinished work from another host
    .\scripts\sync_host.ps1 -GitOnly   # git only (fast)
    .\scripts\sync_host.ps1 -Leave     # leaving: commit and push everything unfinished
    .\scripts\sync_host.ps1 -Leave -Message "finish the timer"

What the script does:

* **Arriving.** Sets `pull.rebase`, `fetch.prune`, `rebase.autoStash` in the repository; pulls the current
  branch and the local `dev`/`master`; compares `.env` with `.env.example` and checks that the backend settings
  load; reinstalls the Python and npm dependencies only if `uv.lock` or
  `package-lock.json` changed (`npm ci` — exactly per the lock file); downloads Stockfish from the official GitHub if it
  is missing; starts Docker Desktop if necessary, brings up `db` and `redis`, applies migrations; imports the
  champions' games if they are missing. A repeated run reinstalls nothing.
* **Leaving.** Uncommitted changes on `dev`/`master` go to a new branch `wip/<host>-<date-time>`,
  on any other branch — as a `wip(<host>): ...` commit into that same branch; the branch is pushed. The script warns about
  other unpushed branches and about stash — they stay only on this host.
* **Continuing.** `-Resume` switches to the most recent `wip/*` branch from GitHub. When the work is ready,
  the WIP commits are collapsed into one at merge time:

      git checkout dev
      git merge --squash wip/<host>-<date-time>
      git commit -m "feat(...): ..."
      git push origin dev
      git push origin --delete wip/<host>-<date-time>

Secrets from `.env` do not get into git: keep `.env` in a password manager and when adding a new key
update both it and `.env.example`. The commit author's name and email (`git config --global user.name/user.email`)
must be the same on all hosts.
