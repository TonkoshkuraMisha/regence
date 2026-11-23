# --- FILE: tests/test_analysis_service.py ---

import chess
import chess.engine
import pytest

from src.core.errors import DomainValueError
from src.models.game import Game, GameStatus
from src.services import analysis_service as module
from src.services.analysis_service import (
    GameDataNotFoundError,
    GameNotFinishedError,
    _count_mainline_plies,
    _evaluate_board_sequence_sync,
    analysis_service,
    calculate_accuracy,
    classify_move_by_cp_loss,
    ensure_game_finished,
)
from src.services.engine_pool import EngineUnavailableError


def test_classify_move_by_cp_loss_thresholds():
    assert classify_move_by_cp_loss(0, is_best_move=True) == ("Best", "!")
    assert classify_move_by_cp_loss(8) == ("Best", "!")
    assert classify_move_by_cp_loss(25) == ("Good", "")
    assert classify_move_by_cp_loss(70) == ("Inaccuracy", "?!")
    assert classify_move_by_cp_loss(140) == ("Mistake", "?")
    assert classify_move_by_cp_loss(320) == ("Blunder", "??")


def test_calculate_accuracy_bounds_and_monotonicity():
    perfect = calculate_accuracy([0, 0, 5, 0])
    decent = calculate_accuracy([15, 35, 60, 20])
    blunder_heavy = calculate_accuracy([250, 400, 310, 500])

    assert 95.0 <= perfect <= 100.0
    assert decent < perfect
    assert blunder_heavy < decent
    assert 0.0 <= blunder_heavy <= 100.0


@pytest.mark.asyncio
async def test_evaluate_board_sequence_fools_mate():
    sample_pgn = (
        '[Event "Test Game"]\n'
        '[White "Player1"]\n'
        '[Black "Player2"]\n'
        '[Result "0-1"]\n\n'
        '1. f3 e5 2. g4 Qh4# 0-1\n'
    )
    report = _evaluate_board_sequence_sync(sample_pgn, depth=5)

    assert "white" in report and "black" in report
    assert len(report["moves"]) == 4
    assert report["moves"][-1]["san"] == "Qh4#"
    assert report["moves"][-1]["eval_cp"] <= -900
    assert 0.0 <= report["white"]["accuracy"] <= 100.0
    assert 0.0 <= report["black"]["accuracy"] <= 100.0


def test_game_phase():
    import chess

    from src.services.analysis_service import game_phase

    assert game_phase(chess.Board()) == "opening"
    middle = chess.Board("r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 12")
    assert game_phase(middle) == "middlegame"
    assert game_phase(chess.Board("4k3/pp3ppp/8/8/8/8/PP3PPP/R3K3 w - - 0 5")) == "endgame"


@pytest.mark.asyncio
async def test_report_has_accuracy_by_phase():
    report = _evaluate_board_sequence_sync('[Result "0-1"]\n\n1. f3 e5 2. g4 Qh4# 0-1\n', depth=5)
    assert {m["phase"] for m in report["moves"]} == {"opening"}
    for side in ("white", "black"):
        phases = report[side]["phases"]
        assert set(phases) == {"opening", "middlegame", "endgame"}
        assert phases["middlegame"] is None and phases["endgame"] is None
        assert phases["opening"] == report[side]["accuracy"]
    # The engine's best move loses nothing — neither in the review nor in accuracy.
    best = [m for m in report["moves"] if m["uci"] == m["best_move_uci"]]
    assert all(m["cp_loss"] == 0 for m in best)


# --- Extra coverage: stub engine, review failures, full-review cache ---------------------------------


SHORT_PGN = '[Result "1-0"]\n\n1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0\n'


class _FakeEngine:
    """Stub engine: evaluation +30 and best move e2e4; fail mode — every evaluation fails; multipv — a list answer."""

    def __init__(self, fail: bool = False, as_list: bool = False):
        self.id = {"name": "FakeFish"}
        self.fail = fail
        self.as_list = as_list

    def analyse(self, board, limit):
        if self.fail:
            raise chess.engine.EngineError("failure")
        info = {"score": chess.engine.PovScore(chess.engine.Cp(30), chess.WHITE), "pv": [chess.Move.from_uci("e2e4")]}
        return [info] if self.as_list else info


def _use_engine(monkeypatch, engine=None, acquire_error: Exception | None = None):
    class Pool:
        def acquire(self):
            class Ctx:
                def __enter__(self_inner):
                    if acquire_error is not None:
                        raise acquire_error
                    return engine

                def __exit__(self_inner, *exc):
                    return False

            return Ctx()

    monkeypatch.setattr(module, "resolve_stockfish_path", lambda *a, **k: "stockfish")
    monkeypatch.setattr(module.os.path, "exists", lambda path: True)
    monkeypatch.setattr(module, "get_engine_pool", lambda path: Pool())


def test_accuracy_of_empty_list_is_perfect():
    assert calculate_accuracy([]) == 100.0


def test_unreadable_pgn_is_a_domain_error():
    with pytest.raises(DomainValueError):
        _evaluate_board_sequence_sync("", 5)
    assert _count_mainline_plies("") == -1
    assert _count_mainline_plies(SHORT_PGN) == 7


@pytest.mark.parametrize("as_list", [False, True])
def test_full_game_with_engine_uses_its_scores(monkeypatch, as_list):
    _use_engine(monkeypatch, _FakeEngine(as_list=as_list))
    report = _evaluate_board_sequence_sync(SHORT_PGN, 5)
    assert report["engine"] == "FakeFish"
    assert len(report["moves"]) == 7 and report["moves"][-1]["uci"] == "h5f7"


def test_engine_failure_on_a_position_falls_back_to_static_evaluation(monkeypatch):
    _use_engine(monkeypatch, _FakeEngine(fail=True))
    report = _evaluate_board_sequence_sync(SHORT_PGN, 5)
    assert len(report["moves"]) == 7


def test_engine_unavailable_at_start_uses_static_fallback(monkeypatch):
    _use_engine(monkeypatch, acquire_error=EngineUnavailableError("failed to start"))
    report = _evaluate_board_sequence_sync(SHORT_PGN, 5)
    assert report["engine"] == "Static Fallback Evaluator"


def test_unfinished_game_cannot_be_analysed():
    with pytest.raises(GameNotFinishedError):
        ensure_game_finished(Game(id=1, status=GameStatus.IN_PROGRESS))
    ensure_game_finished(Game(id=1, status=GameStatus.COMPLETED))
    ensure_game_finished(Game(id=1, status=GameStatus.ABORTED))


async def test_analyze_position_with_engine_and_fallbacks(monkeypatch):
    _use_engine(monkeypatch, _FakeEngine(as_list=True))
    result = await analysis_service.analyze_position(None, ["e4", "e7e5", "not-a-move", "Nf3"])
    assert result["best_move"] == "e2e4" and result["evaluation_cp"] == 30
    assert result["fen"].startswith("rnbqkbnr/pppp1ppp/8/4p3/4P3/8")  # the move after the garbage was not played
    _use_engine(monkeypatch, acquire_error=EngineUnavailableError("busy"))
    static = await analysis_service.analyze_position(None, ["e4"])
    assert static["best_move"] is None


async def test_full_game_analysis_cache_and_save_failure(db_session, test_user_1, test_user_2, monkeypatch):
    monkeypatch.setattr(module, "resolve_stockfish_path", lambda *a, **k: None)
    with pytest.raises(GameDataNotFoundError):
        await analysis_service.analyze_full_game(db_session, 999999)
    game = Game(white_player_id=test_user_1.id, black_player_id=test_user_2.id, status=GameStatus.COMPLETED,
                base_time_ms=180000, increment_ms=0, is_rated=False, result="1-0", pgn=SHORT_PGN)
    db_session.add(game)
    await db_session.commit()
    game_id = game.id
    first = await analysis_service.analyze_full_game(db_session, game_id)
    assert first["game_id"] == game_id and game.analysis_json
    # The repeat is taken from the stored review, without a new calculation.
    monkeypatch.setattr(module, "evaluate_pgn", lambda pgn: pytest.fail("the review must come from the cache"))
    assert (await analysis_service.analyze_full_game(db_session, game_id))["game_id"] == game_id
    # A corrupted cache is recalculated; a save failure is only written to the log.
    game.analysis_json = "{not json"
    await db_session.commit()

    async def fresh(pgn):
        return {"format_version": module.ANALYSIS_FORMAT_VERSION, "moves": []}

    async def failing_commit():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(module, "evaluate_pgn", fresh)
    monkeypatch.setattr(db_session, "commit", failing_commit)
    report = await analysis_service.analyze_full_game(db_session, game_id, force=True)
    assert report["game_id"] == game_id
