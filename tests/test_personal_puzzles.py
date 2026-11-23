# --- FILE: tests/test_personal_puzzles.py ---
"""Puzzles from the player's own games (task 13.5): picking solvable moments, spaced repetition, API, background analysis."""

import datetime as dt
import json

import chess
import chess.engine
import pytest
from sqlalchemy import func, select

from src.core.errors import DomainValueError
from src.models.game import Game, GameStatus
from src.models.imported_game import ImportedGame
from src.models.puzzle import PersonalPuzzle
from src.models.user import User
from src.services import personal_puzzles as service
from src.services.engine_pool import EngineUnavailableError
from src.services.puzzles import PuzzleError

API = "/api/v1/puzzles"
# 1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6?? 4. Qxf7# - Black blunders into mate on ply 6 (3...g6 was better).
UCI = ["e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"]
PGN = '[Event "t"]\n[Result "1-0"]\n\n1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0'


def _analysis() -> str:
    moves = []
    for ply, uci in enumerate(UCI, start=1):
        bad = ply == 6
        moves.append({"ply": ply, "move_number": (ply + 1) // 2, "color": "white" if ply % 2 else "black",
                      "san": "", "uci": uci, "eval_cp": 0, "eval_display": "0", "best_move_uci": "g7g6" if bad else uci,
                      "cp_loss": 950 if bad else 0, "classification": "Blunder" if bad else "Best", "symbol": ""})
    return json.dumps({"format_version": 2, "engine": "t", "moves": moves})


@pytest.fixture
async def game(db_session, test_user_1, test_user_2):
    record = Game(white_player_id=test_user_2.id, black_player_id=test_user_1.id, status=GameStatus.COMPLETED,
                  base_time_ms=180000, increment_ms=0, is_rated=False, result="1-0", pgn=PGN,
                  analysis_json=_analysis())
    db_session.add(record)
    await db_session.commit()
    return record


@pytest.fixture
def engine(monkeypatch):
    """Stubbed engine: the two best moves with a given gap."""
    state = {"top": [("g7g6", 0), ("d8e7", -350)]}
    monkeypatch.setattr(service, "top_two", lambda board: state["top"])
    return state


async def test_blunder_becomes_a_personal_puzzle(db_session, game, engine, test_user_1):
    assert await service.extract_for_game(db_session, game.id) == 1
    puzzle = await db_session.scalar(select(PersonalPuzzle))
    assert puzzle.user_id == test_user_1.id and puzzle.ply == 6
    assert puzzle.solution == "g7g6" and puzzle.played == "g8f6" and puzzle.previous_move == "d1h5"
    assert chess.Board(puzzle.fen).turn == chess.BLACK
    # Re-analysing does not duplicate anything.
    assert await service.extract_for_game(db_session, game.id) == 0
    assert await db_session.scalar(select(func.count()).select_from(PersonalPuzzle)) == 1


async def test_guessable_moments_are_skipped(db_session, game, engine):
    engine["top"] = [("g7g6", 0), ("d8e7", -120)]  # the second move is hardly worse: this is guessing
    assert await service.extract_for_game(db_session, game.id) == 0


async def test_bots_and_unanalysed_games_give_nothing(db_session, game, engine, test_user_1):
    user = await db_session.get(User, test_user_1.id)
    user.is_bot = True
    await db_session.commit()
    assert await service.extract_for_game(db_session, game.id) == 0
    game.analysis_json = None
    await db_session.commit()
    assert await service.extract_for_game(db_session, game.id) == 0


def test_obvious_capture_is_not_a_puzzle():
    board = chess.Board("4k3/8/8/3n4/8/4N3/8/4K3 w - - 0 1")
    capture = chess.Move.from_uci("e3d5")
    assert service.obvious_capture(board, capture)
    assert not service.is_solvable(board, capture, [("e3d5", 300), ("e1d2", 0)])
    quiet = chess.Move.from_uci("e1d2")
    assert service.is_solvable(board, quiet, [("e1d2", 400), ("e3c4", 50)])
    assert not service.is_solvable(board, quiet, [("e1d2", 400)])  # the only move: nothing to solve
    assert service.is_solvable(board, quiet, [("e1d2", 9_995), ("e3c4", 3_000)])  # mate versus "just winning"


async def test_spaced_repetition(db_session, game, engine, test_user_1):
    await service.extract_for_game(db_session, game.id)
    user = await db_session.get(User, test_user_1.id)
    puzzle = await service.next_due(db_session, user)
    assert puzzle is not None

    wrong = await service.answer(db_session, user, puzzle.id, "d8e7")
    assert wrong["correct"] is False and wrong["solution"] == "g7g6" and wrong["played"] == "g8f6"
    due = dt.datetime.fromisoformat(wrong["next_due_at"])
    assert dt.timedelta(hours=23) < due - dt.datetime.now(dt.UTC) < dt.timedelta(hours=25)
    assert await service.next_due(db_session, user) is None  # not shown until tomorrow

    first = await service.answer(db_session, user, puzzle.id, "g7g6")
    assert first["correct"] and not first["done"] and first["solved_streak"] == 1
    assert dt.timedelta(days=2) < dt.datetime.fromisoformat(first["next_due_at"]) - dt.datetime.now(dt.UTC)
    second = await service.answer(db_session, user, puzzle.id, "g7g6")
    assert second["done"] and second["next_due_at"] is None
    summary = await service.summary(db_session, user)
    assert summary == {"due": 0, "active": 0, "mastered": 1, "next_due_at": None}


async def test_api(client, db_session, game, engine, token_user_1, token_user_2):
    await service.extract_for_game(db_session, game.id)
    auth = {"Authorization": f"Bearer {token_user_1}"}
    assert client.get(f"{API}/personal", headers=auth).json()["due"] == 1
    view = client.get(f"{API}/personal/next", headers=auth).json()
    assert view["color"] == "black" and view["previous_move"] == "d1h5" and "solution" not in view
    # Where the mistake came from (task B.3): the opponent and the game date.
    assert isinstance(view["opponent"], str) and view["opponent"] and view["opponent_is_bot"] is False
    assert dt.datetime.fromisoformat(view["played_at"]).tzinfo is not None
    assert client.get(f"{API}/personal/game/{game.id}", headers=auth).json()["plies"] == [6]
    # Another player's puzzle is unavailable, and another player's analysis shows no badges.
    other = {"Authorization": f"Bearer {token_user_2}"}
    assert client.post(f"{API}/personal/{view['id']}/answer", json={"move": "g7g6"}, headers=other).status_code == 404
    assert client.get(f"{API}/personal/game/{game.id}", headers=other).json()["plies"] == []
    illegal = client.post(f"{API}/personal/{view['id']}/answer", json={"move": "a1a8"}, headers=auth)
    assert illegal.status_code == 400
    body = client.post(f"{API}/personal/{view['id']}/answer", json={"move": "g7g6"}, headers=auth).json()
    assert body["correct"] is True
    assert client.get(f"{API}/personal/next", headers=auth).status_code == 404


def test_bot_game_is_analysed_in_the_background(client, token_user_1, no_celery_publish):
    saved = client.post("/api/v1/bots/save-game", headers={"Authorization": f"Bearer {token_user_1}"}, json={
        "bot_id": "morphy", "player_color": "white", "result": "0-1", "moves_uci": ["f2f3", "e7e5", "g2g4", "d8h4"],
    })
    assert saved.status_code == 200
    import time

    for _ in range(50):
        if no_celery_publish:
            break
        time.sleep(0.02)
    assert saved.json()["game_id"] in no_celery_publish


# --- Extra coverage: engine (stub), extraction refusals, puzzle source, answers ---




class _Pool:
    """Stub engine pool: analyse returns a predefined answer."""

    def __init__(self, info):
        self.info = info

    def acquire(self):
        info = self.info

        class Engine:
            def analyse(self, board, limit, multipv=None):
                return info

        class Ctx:
            def __enter__(self):
                return Engine()

            def __exit__(self, *exc):
                return False

        return Ctx()


def _info(move: str, cp: int) -> dict:
    return {"pv": [chess.Move.from_uci(move)], "score": chess.engine.PovScore(chess.engine.Cp(cp), chess.WHITE)}


def test_top_two_without_engine_and_with_single_line(monkeypatch):
    monkeypatch.setattr(service, "resolve_stockfish_path", lambda *a, **k: None)
    assert service.top_two(chess.Board()) is None
    monkeypatch.setattr(service, "resolve_stockfish_path", lambda *a, **k: "sf")
    monkeypatch.setattr(service, "get_engine_pool", lambda path: _Pool(_info("e2e4", 30)))  # not a list
    assert service.top_two(chess.Board()) == [("e2e4", 30)]
    monkeypatch.setattr(service, "get_engine_pool", lambda path: _Pool([_info("e2e4", 30), {"score": None}]))
    assert service.top_two(chess.Board()) == [("e2e4", 30)]  # a line without a move is dropped


def test_is_solvable_edge_cases():
    board = chess.Board()
    best = chess.Move.from_uci("e2e4")
    assert not service.is_solvable(board, best, [])  # the engine returned nothing
    assert not service.is_solvable(board, best, [("d2d4", 0), ("e2e4", -300)])  # the best move is not first
    assert not service.is_solvable(board, best, [("e2e4", 0)])  # the only move: nothing to solve
    capture = chess.Board("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1")
    assert not service.is_solvable(capture, chess.Move.from_uci("e4d5"), [("e4d5", 0), ("e1e2", -400)])


async def _imported(db_session, user, analysis: str | None, pgn: str = PGN, color: str = "black") -> ImportedGame:
    record = ImportedGame(user_id=user.id, source="lichess", external_id=f"x{user.id}{len(pgn)}", color=color,
                          white_name="Rival", black_name="Me", pgn=pgn, analysis_json=analysis,
                          played_at=dt.datetime(2026, 1, 2, tzinfo=dt.UTC))
    db_session.add(record)
    await db_session.commit()
    return record


async def test_extract_for_imported_game(db_session, engine, test_user_1):
    assert await service.extract_for_imported(db_session, 999999) == 0  # no such game
    bare = await _imported(db_session, test_user_1, None)
    assert await service.extract_for_imported(db_session, bare.id) == 0  # no analysis
    record = await _imported(db_session, test_user_1, _analysis(), pgn=PGN + " ")
    assert await service.extract_for_imported(db_session, record.id) == 1
    puzzle = await db_session.scalar(select(PersonalPuzzle).where(PersonalPuzzle.imported_game_id == record.id))
    assert puzzle.game_id is None and puzzle.ply == 6
    context = await service.game_context(db_session, puzzle, test_user_1)
    assert context["opponent"] == "Rival" and context["source"] == "lichess" and context["played_at"].startswith("2026-01-02")
    assert await service.plies_for_imported(db_session, record.id, test_user_1) == [6]
    # The imported game was deleted: the source is unknown, not an error.
    await db_session.delete(record)
    await db_session.commit()
    gone = await service.game_context(db_session, puzzle, test_user_1)
    assert gone["opponent"] is None and gone["source"] is None


async def test_extract_stops_on_bad_data_and_unavailable_engine(db_session, game, monkeypatch, test_user_1):
    broken = await _imported(db_session, test_user_1, "{not json")
    assert await service.extract_for_imported(db_session, broken.id) == 0
    no_pgn = await _imported(db_session, test_user_1, _analysis(), pgn="")
    assert await service.extract_for_imported(db_session, no_pgn.id) == 0

    def busy(board):
        raise EngineUnavailableError("pool busy")

    monkeypatch.setattr(service, "top_two", busy)
    assert await service.extract_for_game(db_session, game.id) == 0
    monkeypatch.setattr(service, "top_two", lambda board: None)  # no engine at all
    assert await service.extract_for_game(db_session, game.id) == 0


async def test_game_context_for_human_bot_and_missing_game(db_session, game, engine, test_user_1, test_user_2):
    await service.extract_for_game(db_session, game.id)
    puzzle = await db_session.scalar(select(PersonalPuzzle))
    human = await service.game_context(db_session, puzzle, test_user_1)
    assert human["opponent"] == test_user_2.username and human["opponent_is_bot"] is False
    # The opponent is a bot with its own personality: its name is shown, the bot flag is cleared.
    opponent = await db_session.get(User, test_user_2.id)
    opponent.is_bot = True
    game.personality_name = "Persona"
    await db_session.commit()
    persona = await service.game_context(db_session, puzzle, test_user_1)
    assert persona["opponent"] == "Persona" and persona["opponent_is_bot"] is False
    game.personality_name = None
    await db_session.commit()
    assert (await service.game_context(db_session, puzzle, test_user_1))["opponent_is_bot"] is True
    puzzle.game_id = None
    assert (await service.game_context(db_session, puzzle, test_user_1))["opponent"] is None


async def test_answer_rejects_unknown_puzzle_and_bad_moves(db_session, game, engine, test_user_1, test_user_2):
    await service.extract_for_game(db_session, game.id)
    puzzle = await db_session.scalar(select(PersonalPuzzle))
    with pytest.raises(PuzzleError):
        await service.answer(db_session, test_user_1, 999999, "g7g6")
    with pytest.raises(PuzzleError):
        await service.answer(db_session, test_user_2, puzzle.id, "g7g6")  # another player's puzzle
    with pytest.raises(DomainValueError):
        await service.answer(db_session, test_user_1, puzzle.id, "zzzz")
    with pytest.raises(DomainValueError):
        await service.answer(db_session, test_user_1, puzzle.id, "a1a8")


async def test_plies_for_game_without_user(db_session):
    assert await service.plies_for_game(db_session, 1, None) == []
