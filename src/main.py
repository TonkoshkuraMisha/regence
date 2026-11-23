# --- FILE: src/main.py ---
"""
The API entry point: assembles the FastAPI application and connects all routes.

* create_app - the list of routes by section (`src/api/*.py`), CORS from the CORS_ORIGINS setting, HTTP metrics collection,
  a single format of request validation errors (without echoing submitted values - a password, for example, would end up in the
  response).
  The API description (/docs) is published only outside production.
* lifespan - at startup runs the game clock check loop (flags, no-shows, abandoned games -
  game_state.check_timeouts_loop; of several processes one leader runs it), at shutdown closes the Stockfish engines
  and the Redis connection.
* /health - whether PostgreSQL and Redis respond (503 if not): Docker and the balancer use it to decide whether
  the instance can be loaded. /metrics - Prometheus metrics, not published outside through nginx.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.api import (
    account,
    arenas,
    beta,
    bots,
    chess960,
    client_errors,
    conferences,
    exam,
    feed,
    game_import,
    guess,
    ladder,
    learn,
    library,
    messages,
    mini_game_rooms,
    mini_games,
    moderation,
    personalities,
    public,
    puzzles,
    repertoire,
    skills,
    social,
    study,
    teams,
    themes,
    tournaments,
    trainers,
    watch,
    workout,
)
from src.api.analysis import router as analysis_router
from src.api.auth import router as auth_router
from src.api.profile import router as profile_router
from src.api.websockets import router as ws_router
from src.core.config import settings
from src.core.errors import validation_error_items
from src.core.logging_setup import REQUEST_ID_HEADER, request_log_middleware, setup_logging
from src.core.observability import (
    http_metrics_middleware,
    init_sentry,
    metrics_response,
    refresh_active_players,
    refresh_queue_lengths,
)
from src.db import redis as redis_module
from src.db.session import AsyncSessionLocal
from src.services.connection_manager import manager
from src.services.engine_pool import close_all_engine_pools
from src.services.game_state import state_manager

setup_logging("api")  # the format, file and record context - src/core/logging_setup.py
logger = logging.getLogger(__name__)

init_sentry("api")

# How long /health waits for PostgreSQL and Redis (each separately) before considering the service unavailable.
HEALTH_CHECK_TIMEOUT_S = 2.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Start and stop of the API process. At start the background game clock loop runs (flags, no-shows, abandoned
    games - state_manager.check_timeouts_loop; the loop exists in every uvicorn process, but the work is done by one leader -
    the Redis key timeouts:leader). At stop the loop is cancelled, the Stockfish processes and the Redis connection are closed.
    """
    logger.info("Starting up %s (%s)...", settings.PROJECT_NAME, settings.ENVIRONMENT)
    timeout_task = asyncio.create_task(state_manager.check_timeouts_loop(manager))

    yield

    timeout_task.cancel()
    try:
        await asyncio.gather(timeout_task, return_exceptions=True)
    except asyncio.CancelledError:
        pass

    logger.info("Shutting down %s...", settings.PROJECT_NAME)
    await asyncio.to_thread(close_all_engine_pools)
    await redis_module.redis_client.aclose()


def create_app() -> FastAPI:
    """
    Assembles the application: CORS, HTTP metrics, a single format of request validation errors and the routes of all sections.
    All routes live under the /api/v1 prefix (settings.API_V1_STR); outside it - only /health and /metrics.
    """
    # The API documentation is not published in production: it reveals all endpoints and schemas.
    docs_enabled = not settings.is_production
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url=f"{settings.API_V1_STR}/openapi.json" if docs_enabled else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # The request id is visible to the client from another origin too (Vite :3000 -> API :8000): it goes into the error
        # report.
        expose_headers=[REQUEST_ID_HEADER],
    )

    app.middleware("http")(http_metrics_middleware)
    app.middleware("http")(request_log_middleware)  # last - it is outermost: everything below has a request id

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Without echoing submitted values (a password, for example, would end up in the response) and with the check
        # parameters from which the client assembles the text in the player's language.
        return JSONResponse(status_code=422, content={"detail": validation_error_items(exc.errors())})

    app.include_router(auth_router, prefix=settings.API_V1_STR)
    app.include_router(ws_router, prefix=settings.API_V1_STR)
    app.include_router(profile_router, prefix=settings.API_V1_STR)
    app.include_router(analysis_router, prefix=settings.API_V1_STR)
    app.include_router(bots.router, prefix="/api/v1/bots", tags=["bots"])
    app.include_router(personalities.router, prefix="/api/v1/bots/personalities", tags=["bots"])
    app.include_router(ladder.router, prefix="/api/v1/bots/ladder", tags=["bots"])
    app.include_router(themes.router, prefix="/api/v1/themes", tags=["training"])
    app.include_router(puzzles.router, prefix="/api/v1/puzzles", tags=["training"])
    app.include_router(learn.router, prefix="/api/v1/learn", tags=["training"])
    app.include_router(guess.router, prefix="/api/v1/guess", tags=["training"])
    app.include_router(tournaments.router, prefix="/api/v1/tournaments", tags=["tournaments"])
    app.include_router(arenas.router, prefix="/api/v1/arenas", tags=["tournaments"])
    app.include_router(conferences.router, prefix="/api/v1/conferences", tags=["tournaments"])
    app.include_router(teams.router, prefix="/api/v1/teams", tags=["social"])
    app.include_router(study.router, prefix="/api/v1/study", tags=["social"])
    app.include_router(watch.router, prefix="/api/v1/watch", tags=["watch"])
    app.include_router(trainers.router, prefix="/api/v1/trainers", tags=["training"])
    app.include_router(social.router, prefix="/api/v1/social", tags=["social"])
    app.include_router(messages.router, prefix="/api/v1/messages", tags=["social"])
    app.include_router(feed.router, prefix="/api/v1/feed", tags=["social"])
    app.include_router(moderation.router, prefix="/api/v1/moderation", tags=["social"])
    app.include_router(mini_games.router, prefix="/api/v1/mini-games", tags=["trainers"])
    app.include_router(mini_game_rooms.router, prefix="/api/v1/mini-game-rooms", tags=["trainers"])
    app.include_router(chess960.router, prefix="/api/v1/chess960", tags=["bots"])
    app.include_router(repertoire.router, prefix="/api/v1/repertoires", tags=["repertoire"])
    app.include_router(library.router, prefix="/api/v1/library", tags=["library"])
    app.include_router(game_import.router, prefix="/api/v1/imports", tags=["library"])
    app.include_router(public.router, prefix="/api/v1/public", tags=["public"])
    app.include_router(beta.router, prefix="/api/v1/beta", tags=["beta"])
    app.include_router(skills.router, prefix="/api/v1/skills", tags=["training"])
    app.include_router(workout.router, prefix="/api/v1/workout", tags=["training"])
    app.include_router(exam.router, prefix="/api/v1/exam", tags=["training"])
    app.include_router(account.router, prefix=settings.API_V1_STR)
    app.include_router(client_errors.router, prefix=settings.API_V1_STR)

    return app


app = create_app()


async def _check_database() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT 1"))


async def _check_redis() -> None:
    await redis_module.redis_client.ping()


@app.get("/health")
async def health_check():
    """
    Service readiness: whether PostgreSQL and Redis respond. 503 if anything is unavailable -
    by this code Docker and the balancer understand that the instance must not be loaded.
    """
    checks: dict[str, str] = {}
    for name, check in (("database", _check_database), ("redis", _check_redis)):
        try:
            await asyncio.wait_for(check(), timeout=HEALTH_CHECK_TIMEOUT_S)
            checks[name] = "ok"
        except Exception as exc:
            logger.warning("Health check '%s' failed: %s", name, exc)
            checks[name] = "unavailable"

    healthy = all(status == "ok" for status in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "healthy" if healthy else "degraded", "version": settings.VERSION, "checks": checks},
    )

@app.get("/metrics", include_in_schema=False)
async def metrics():
    """
    Prometheus metrics (src/core/observability.py). Not published outside through nginx - only inside the compose network.
    Before serving, the number of players today (a counter in Redis) and the Celery queue lengths are refreshed.
    """
    await refresh_active_players()
    await refresh_queue_lengths()
    return metrics_response()


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)
