<!-- --- FILE: QUICKSTART.md --- -->

# Quick start and recovery of regence on a new host

## 1. Installation from scratch (cold start on a new PC)

### Step 1. Clone and environment variables

    git clone https://github.com/TonkoshkuraMisha/regence.git regence
    cd regence
    git checkout dev

    Copy-Item .env.example .env -ErrorAction SilentlyContinue
    Copy-Item frontend/.env.example frontend/.env -ErrorAction SilentlyContinue

### Step 2. Bring up the database and Redis

    docker compose up -d db redis
    docker compose ps

### Step 3. Set up the Python environment, migrations and the Stockfish engine (backend)

    uv sync                       # creates .venv: Python 3.14 from .python-version, packages strictly per uv.lock
    .\.venv\Scripts\Activate.ps1
    python scripts/setup_stockfish.py     # the Stockfish engine into bin/ (all tests work without it, but bots and analysis do not)
    python scripts/download_champions.py  # freely licensed portraits of chess players (Wikimedia Commons)
    alembic upgrade head                  # database schema
    python -m scripts.import_puzzles      # puzzles from data/puzzles/ into the database (re-running is safe)
    python -m src.db.seed                 # optional: archive of world champions' games

### Step 4. Install the frontend packages

    cd frontend
    npm install
    cd ..

---

## 2. Daily start

### Option A - automatic (one command from the root on any PC)

    .\start_dev.ps1

To stop the background servers:

    Get-Job | Stop-Job; Get-Job | Remove-Job

### Option B - manual (in 4 terminals)

**Terminal 1 - infrastructure (Docker):**

    docker compose up -d db redis

**Terminal 2 - backend (FastAPI):**

    .\.venv\Scripts\Activate.ps1
    alembic upgrade head
    python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload

**Terminal 3 - Celery worker (game analysis and bot games in tournaments):**

    .\.venv\Scripts\Activate.ps1
    celery -A src.worker.celery_app worker --loglevel=INFO --pool=solo -Q analysis,simulation

`--pool=solo` is needed on Windows: the Celery prefork pool does not work there. There are two queues: `analysis` (game analysis,
position index, reminders) and `simulation` (bot-vs-bot games) - in development one worker listens to both.

Scheduled tasks (warm-up and arena-start reminders, bot self-play) are run by a separate process; in ordinary
development it is not needed, `start_dev.ps1` does not start it:

    celery -A src.worker.celery_app beat --loglevel=INFO

**Terminal 4 - frontend (Vite):**

    cd frontend
    npm run dev

* **Frontend:** [http://127.0.0.1:3000](http://127.0.0.1:3000)
* **Swagger API:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## Production

Deployment in Docker (nginx, API, Celery, PostgreSQL, Redis) - see [DEPLOY.md](DEPLOY.md).

---

## 3. Project health check (linters and tests)

**Backend:**

    .\.venv\Scripts\Activate.ps1
    uv sync                               # dev tools (ruff, mypy, pytest-cov) are installed by default
    ruff check .                          # linter (rules in pyproject.toml)
    mypy                                  # type check of src/
    python -m pytest --cov                # tests and coverage (threshold in pyproject.toml)

The tests need neither PostgreSQL, nor Redis, nor Stockfish: the database is in-memory SQLite, Redis and the engine are replaced. One
section: `python -m pytest tests/test_arena.py -q`. Which test covers which section - `docs/ARCHITECTURE.md`, section 4.

**Frontend:**

    cd frontend
    npm run lint
    npm run test
    npm run build
    cd ..