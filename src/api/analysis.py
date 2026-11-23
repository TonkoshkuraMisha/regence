# --- FILE: src/api/analysis.py ---
"""
Engine and mentor on request (/analysis): position evaluation, endgame tablebases, "find mate", opening explorer,
advice, tiered hint, move check in a game with the mentor, full game review.

Everything that works with an arbitrary position is help during a game, so these endpoints (/position, /tablebase,
/find-mate, /opening-explorer, /advice, /hint, /check-move) are closed by the fair-play rule
(src/api/fair_play.forbid_engine_help_during_game): during one's own game with a human the player gets a refusal, and
a request during a ladder or tournament game is noted in its session (note_ladder_analysis) - a ladder game is not
counted, a tournament game is counted as lost. Reviewing a game by id (/game/{id}) is not closed by this dependency:
it is protected by another rule - only a finished game is reviewed, a game in progress gets 409. "Disagree" (/dispute)
does not call the engine.

The load is limited: every endpoint has its own requests-per-minute limit (settings RATE_LIMIT_*, lower for guests),
when the engine pool is busy the answer is 503 engine_busy, one request at a time reviews a single game
(_game_analysis_lock - within one API process). With FREE_TIER_LIMITS there are daily quotas for game review
and for the mentor. All endpoints are available without logging in.

Calculations - src/services/analysis_service.py, move_check.py, coach.py, tablebase.py, mate_finder.py,
opening_explorer.py; response format - src/schemas/analysis.py. The finished review is stored in games.analysis_json.
"""

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.fair_play import forbid_engine_help_during_game, optional_user_id
from src.api.ladder import note_ladder_analysis
from src.api.rate_limit import DailyQuota, rate_limit
from src.core.errors import ApiError, DomainError, DomainValueError
from src.db.session import get_db
from src.models.game import Game
from src.schemas.analysis import (
    AdviceRequest,
    AdviceResponse,
    DisputeRequest,
    FullGameAnalysisResponse,
    HintRequest,
    HintResponse,
    MoveCheckRequest,
    MoveCheckResponse,
    PositionAnalysisRequest,
)
from src.services import mate_finder, move_check, opening_explorer, tablebase
from src.services.analysis_service import (
    GameDataNotFoundError,
    GameNotFinishedError,
    analysis_service,
    ensure_game_finished,
    is_current_analysis,
)
from src.services.engine_pool import EngineBusyError, EngineUnavailableError, engine_work
from src.services.game_engine import InvalidStartPositionError, board_from_start_fen
from src.services.game_summary import summarize

router = APIRouter(prefix="/analysis", tags=["Game Analysis"])


class TablebaseRequest(BaseModel):
    fen: str = Field(..., max_length=120)


class FindMateRequest(BaseModel):
    fen: str = Field(..., max_length=120)
    moves: int = Field(3, ge=1, le=mate_finder.MAX_MOVES, description="Look for a mate no longer than this many moves")


class OpeningExplorerRequest(BaseModel):
    moves: list[str] = Field(default_factory=list, max_length=opening_explorer.MAX_MOVES,
                             description="Moves from the starting position in UCI")

# game_id -> [lock, number of requests waiting for or holding the lock]. The entry is deleted when
# the counter drops to zero, so the dictionary does not grow with every game ever analysed.
_ANALYSIS_LOCKS: dict[int | str, list] = {}


@asynccontextmanager
async def _game_analysis_lock(game_id: int | str):
    """
    Lock for reviewing one game: a second request for the same game waits for the first and (without force) gets the already
    finished
    review from the database instead of occupying a second engine. The lock lives in process memory - it does not work
    between uvicorn processes.
    The key is the game id or the string "imported:<id>" for an imported one (src/api/game_import.py).
    """
    entry = _ANALYSIS_LOCKS.setdefault(game_id, [asyncio.Lock(), 0])
    entry[1] += 1
    try:
        async with entry[0]:
            yield
    finally:
        entry[1] -= 1
        if entry[1] == 0:
            _ANALYSIS_LOCKS.pop(game_id, None)


# Daily quotas of the free tier (task 23.3): off until FREE_TIER_LIMITS is enabled.
GAME_ANALYSIS_QUOTA = DailyQuota("game_analysis", "FREE_GAME_ANALYSES_PER_DAY")
COACH_QUOTA = DailyQuota("coach", "FREE_COACH_REQUESTS_PER_DAY")


def _engine_busy() -> HTTPException:
    """503 engine_busy: all pool engines are busy; the Retry-After header advises to retry in 5 seconds."""
    return ApiError(status.HTTP_503_SERVICE_UNAVAILABLE, "engine_busy", headers={"Retry-After": "5"})


@router.post(
    "/position",
    dependencies=[
        Depends(rate_limit(
            "analysis_position", "RATE_LIMIT_POSITION_ANALYSIS", "RATE_LIMIT_POSITION_ANALYSIS_GUEST",
        )),
        Depends(forbid_engine_help_during_game),
        Depends(note_ladder_analysis),
    ],
)
async def analyze_game_position(
        request: PositionAnalysisRequest,
        db: AsyncSession = Depends(get_db),
):
    """
    Returns the Stockfish evaluation of the position for the given array of moves (from the standard setup or from start_fen).
    Unavailable while the requester has a game with a human in progress - rated or casual
    (see src/api/fair_play.py). Available without login too - for a guest with a lower request limit.
    """
    try:
        with engine_work("analysis"):
            return await analysis_service.analyze_position(db, request.moves, request.start_fen)
    except InvalidStartPositionError as exc:
        raise exc.to_http(400) from exc
    except EngineBusyError:
        raise _engine_busy() from None


@router.post(
    "/tablebase",
    dependencies=[
        Depends(rate_limit(
            "tablebase", "RATE_LIMIT_POSITION_ANALYSIS", "RATE_LIMIT_POSITION_ANALYSIS_GUEST",
        )),
        Depends(forbid_engine_help_during_game),
        Depends(note_ladder_analysis),
    ],
)
async def probe_tablebase(request: TablebaseRequest):
    """
    Endgame trainer (task 14.4): the result of the position by tablebase and the best move of the side to move (the "ideal
    defender"
    answers with it). This is an exact evaluation - under the fair-play rule, like analysis. If the tablebase server is
    unavailable -
    Stockfish from the pool answers (source="engine", see src/services/tablebase.py); all engines busy - 503 engine_busy.
    """
    try:
        board = board_from_start_fen(request.fen)
        with engine_work("analysis"):
            return await tablebase.probe(board)
    except InvalidStartPositionError as exc:
        raise exc.to_http(400) from exc
    except EngineBusyError:
        raise _engine_busy() from None
    except DomainError as exc:
        raise exc.to_http(503 if exc.code == "tablebase_unavailable" else 400) from exc


@router.post(
    "/find-mate",
    dependencies=[
        Depends(rate_limit(
            "find_mate", "RATE_LIMIT_POSITION_ANALYSIS", "RATE_LIMIT_POSITION_ANALYSIS_GUEST",
        )),
        Depends(forbid_engine_help_during_game),
        Depends(note_ladder_analysis),
    ],
)
async def find_mate(request: FindMateRequest):
    """"Find mate" (task 16.4): a mate no longer than moves moves and its line; this is the engine - under the fair-play
    rule."""
    try:
        with engine_work("analysis"):
            return await mate_finder.find_mate(request.fen, request.moves)
    except InvalidStartPositionError as exc:
        raise exc.to_http(400) from exc
    except (EngineBusyError, EngineUnavailableError):
        raise _engine_busy() from None


@router.post(
    "/opening-explorer",
    dependencies=[
        Depends(rate_limit(
            "opening_explorer", "RATE_LIMIT_POSITION_ANALYSIS", "RATE_LIMIT_POSITION_ANALYSIS_GUEST",
        )),
        Depends(forbid_engine_help_during_game),
        Depends(note_ladder_analysis),
    ],
)
async def explore_opening(request: OpeningExplorerRequest, db: AsyncSession = Depends(get_db)):
    """
    Opening explorer (task 16.2): moves from the position with game statistics, the opening name and master games.
    This is help during a game - under the fair-play rule, like analysis.
    """
    try:
        return await opening_explorer.explore(db, request.moves)
    except DomainValueError as exc:
        raise exc.to_http(400) from exc


@router.post(
    "/advice",
    response_model=AdviceResponse,
    dependencies=[
        Depends(rate_limit("analysis_advice", "RATE_LIMIT_ADVICE", "RATE_LIMIT_ADVICE_GUEST")),
        Depends(COACH_QUOTA.check),
        Depends(forbid_engine_help_during_game),
        Depends(note_ladder_analysis),
    ],
)
async def get_position_advice(request: AdviceRequest, http: Request):
    """
    Mentor advice for the position (task 11.2): the opponent's threat, own opportunity, the idea of the best move and arrows.
    This is an engine hint: unavailable during a game with a human, in a ladder game it makes the game uncounted.
    The text is assembled by the client from the keys of the coach catalogue.
    """
    try:
        with engine_work("coach"):
            advice = await analysis_service.advise(request.fen)
    except DomainValueError as exc:
        raise exc.to_http(400) from exc
    except EngineBusyError:
        raise _engine_busy() from None
    await COACH_QUOTA.record(http)
    return advice


@router.post(
    "/hint",
    response_model=HintResponse,
    dependencies=[
        Depends(rate_limit("analysis_hint", "RATE_LIMIT_ADVICE", "RATE_LIMIT_ADVICE_GUEST")),
        Depends(COACH_QUOTA.check),
        Depends(forbid_engine_help_during_game),
        Depends(note_ladder_analysis),
    ],
)
async def graded_hint(request: HintRequest, http: Request):
    """
    Tiered hint (task 11.4): 1 - a hint in words, 2 - which piece to move, 3 - the move with an arrow and
    an explanation. The move is revealed only on the last tier. Fair-play rules are the same as for advice.
    """
    try:
        with engine_work("coach"):
            hint = await analysis_service.hint(request.fen, request.step)
    except DomainValueError as exc:
        raise exc.to_http(400) from exc
    except EngineBusyError:
        raise _engine_busy() from None
    await COACH_QUOTA.record(http)
    return hint


@router.post(
    "/dispute",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(rate_limit("analysis_dispute", "RATE_LIMIT_ADVICE", "RATE_LIMIT_ADVICE_GUEST"))],
)
async def dispute_coach_warning(payload: DisputeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """"Disagree" with a mentor warning: the position goes to the queue of disputed evaluations for review."""
    try:
        await move_check.record_dispute(payload.fen, payload.move, payload.cp_loss, await optional_user_id(request, db))
    except DomainValueError as exc:
        raise exc.to_http(400) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/check-move",
    response_model=MoveCheckResponse,
    response_model_exclude_none=True,
    dependencies=[
        Depends(rate_limit("analysis_check_move", "RATE_LIMIT_MOVE_CHECK", "RATE_LIMIT_MOVE_CHECK_GUEST")),
        Depends(COACH_QUOTA.check),
        Depends(forbid_engine_help_during_game),
        Depends(note_ladder_analysis),
    ],
)
async def check_player_move(request: MoveCheckRequest, http: Request):
    """
    Game with the mentor (task 11.3): evaluation of the player's move - loss, classification, best move, the opponent's reply,
    the missed capture and the mentor's explanation. This is an engine hint: unavailable in a game with a human, in a ladder
    game it makes the game uncounted.
    """
    try:
        with engine_work("coach"):
            checked = await analysis_service.check_move(request.fen, request.move)
    except DomainValueError as exc:
        raise exc.to_http(400) from exc
    except EngineBusyError:
        raise _engine_busy() from None
    await COACH_QUOTA.record(http)
    return checked


@router.get("/game/{game_id}", response_model=FullGameAnalysisResponse | None)
async def get_cached_game_analysis(
        game_id: int,
        db: AsyncSession = Depends(get_db),
):
    """
    Returns an already saved computer analysis of a finished game from the DB (games.analysis_json), if there is one;
    the engine is not called. null - there is no review yet or it is outdated (a different format version or it does not match
    the game
    record). A game in progress - 409. Available without login; the game summary (summary) is completed when answering.
    """
    game = await db.get(Game, game_id)
    if not game:
        raise ApiError(404, "game_not_found", game_id=game_id)
    try:
        ensure_game_finished(game)
    except GameNotFinishedError as exc:
        raise exc.to_http(status.HTTP_409_CONFLICT) from exc
    if not game.analysis_json:
        return None
    try:
        data = json.loads(game.analysis_json)
    except ValueError:
        return None
    # A review in the old format (without mentor comments) is not served: the client will offer to recompute it.
    if not game.pgn or not is_current_analysis(data, game.pgn):
        return None
    data["game_id"] = game_id
    data["summary"] = summarize(data.get("moves", []), game.result)
    return data


@router.post(
    "/game/{game_id}",
    response_model=FullGameAnalysisResponse,
    dependencies=[Depends(rate_limit("analysis_game", "RATE_LIMIT_GAME_ANALYSIS")), Depends(GAME_ANALYSIS_QUOTA.check)],
)
async def analyze_full_game_endpoint(
        game_id: int,
        http: Request,
        force: bool = Query(default=False, description="Force recomputing the analysis"),
        db: AsyncSession = Depends(get_db),
):
    """
    Performs a full review of a finished game with accuracy calculation and blunder classification.
    Games in progress are not analysed (409). Parallel requests for one game are serialised
    so that several pool engines are not occupied by the same work.
    The finished review is taken from games.analysis_json, recomputation happens with force=true or an outdated format; the
    result
    is saved there too. The limit is RATE_LIMIT_GAME_ANALYSIS per minute (shared by players and guests), with
    FREE_TIER_LIMITS there is also a daily quota, to which only an executed request counts.
    """
    async with _game_analysis_lock(game_id):
        try:
            with engine_work("analysis"):
                report = await analysis_service.analyze_full_game(db, game_id, force=force)
        except GameDataNotFoundError as exc:
            raise exc.to_http(404) from exc
        except GameNotFinishedError as exc:
            raise exc.to_http(status.HTTP_409_CONFLICT) from exc
        except EngineBusyError:
            raise _engine_busy() from None
        except DomainValueError as exc:
            raise exc.to_http(400) from exc
    await GAME_ANALYSIS_QUOTA.record(http)
    game = await db.get(Game, game_id)
    return {**report, "summary": summarize(report.get("moves", []), game.result if game else None)}
