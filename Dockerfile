# --- FILE: Dockerfile ---
# Backend image: the same one for the API (uvicorn), the Celery worker and migrations -
# only the start command differs (see docker-compose.prod.yml).

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# uv is the package manager; it installs dependencies strictly from uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /usr/local/bin/uv

# Stockfish from Debian packages (/usr/games/stockfish - this is where resolve_stockfish_path looks for it).
RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Manifests first: the package layer is cached while they do not change. No dev group.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini .
COPY migrations ./migrations
COPY scripts ./scripts
# Puzzle subset (CC0) - loaded into the database by the migrate service.
COPY data/puzzles ./data/puzzles
# Seed table of generator drills (task 13.7) - positions are restored from it.
COPY data/drills ./data/drills
COPY src ./src

# Not root: if the app is compromised, the process has no rights over the container system.
RUN useradd --create-home --uid 10001 regence \
    && mkdir -p /app/src/db/data/pgns \
    && chown -R regence:regence /app/src/db/data
USER regence

EXPOSE 8000

# --proxy-headers + FORWARDED_ALLOW_IPS: the real client IP comes from X-Forwarded-For set by nginx
#   (otherwise per-IP limits would be shared by all users).
# --ws-max-size: a WebSocket frame larger than 16 KB is dropped before it reaches the app.
# The number of processes is set by WEB_CONCURRENCY (uvicorn reads it itself).
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--ws-max-size", "16384"]
