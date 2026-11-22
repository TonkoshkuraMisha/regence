"""Оценка позиции и очередь споров в move_check: оконченные партии, пул движка (подмена), кэш Redis и его сбои."""

import chess
import chess.engine
import pytest

from src.core.errors import DomainValueError
from src.db import redis as redis_module
from src.services import move_check
from src.services.engine_pool import EngineUnavailableError
from src.services.move_check import PositionEval

START = chess.Board()
MATE_FEN = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"  # мат белым (детский «мат Дурака»)
STALEMATE_FEN = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"


class FakeEngine:
    """Движок-заглушка: отдаёт заранее заданный ответ analyse, без Stockfish."""

    def __init__(self, info):
        self.info = info

    def analyse(self, board, limit):
        return self.info


class FakePool:
    def __init__(self, info):
        self.info = info

    def acquire(self):
        engine = FakeEngine(self.info)

        class Ctx:
            def __enter__(self_inner):
                return engine

            def __exit__(self_inner, *exc):
                return False

        return Ctx()


def _use_pool(monkeypatch, info):
    monkeypatch.setattr(move_check, "resolve_stockfish_path", lambda *a, **k: "stockfish")
    monkeypatch.setattr(move_check, "get_engine_pool", lambda path: FakePool(info))


def test_finished_games_are_evaluated_without_engine(monkeypatch):
    monkeypatch.setattr(move_check, "resolve_stockfish_path", lambda *a, **k: pytest.fail("движок не нужен"))
    mated = move_check.engine_evaluate(chess.Board(MATE_FEN))
    assert mated == PositionEval(-move_check.MATE_CP, 0, None)  # мат поставлен белым: оценка против белых
    assert move_check.engine_evaluate(chess.Board(STALEMATE_FEN)) == PositionEval(0, None, None)


def test_no_engine_means_no_evaluation(monkeypatch):
    monkeypatch.setattr(move_check, "resolve_stockfish_path", lambda *a, **k: None)
    assert move_check.engine_evaluate(START) is None


def test_engine_info_is_converted_to_white_point_of_view(monkeypatch):
    score = chess.engine.PovScore(chess.engine.Cp(35), chess.WHITE)
    _use_pool(monkeypatch, {"score": score, "pv": [chess.Move.from_uci("e2e4")]})
    assert move_check.engine_evaluate(START) == PositionEval(35, None, "e2e4")
    # Ответ-список (multipv) берётся по первой линии; мат в 2 для чёрных; линии нет — лучшего хода нет.
    mate = chess.engine.PovScore(chess.engine.Mate(-2), chess.WHITE)
    _use_pool(monkeypatch, [{"score": mate}])
    result = move_check.engine_evaluate(START)
    assert (result.mate, result.best_uci) == (-2, None) and result.cp_white < 0


async def test_cache_hit_miss_and_store(monkeypatch):
    calls = []

    def fake(board):
        calls.append(1)
        return PositionEval(10, None, "e2e4")

    monkeypatch.setattr(move_check, "engine_evaluate", fake)
    first = await move_check.evaluate_cached(START)
    second = await move_check.evaluate_cached(START)  # из кэша: движок второй раз не зовётся
    assert first == second == PositionEval(10, None, "e2e4") and len(calls) == 1


async def test_unavailable_engine_is_not_cached(monkeypatch):
    def busy(board):
        raise EngineUnavailableError("пул занят")

    monkeypatch.setattr(move_check, "engine_evaluate", busy)
    assert await move_check.evaluate_cached(START) is None
    assert await redis_module.redis_client.get(move_check._cache_key(START)) is None


async def test_broken_redis_does_not_break_evaluation(monkeypatch):
    class BrokenRedis:
        async def get(self, *a, **k):
            raise ConnectionError("нет связи")

        async def set(self, *a, **k):
            raise ConnectionError("нет связи")

    monkeypatch.setattr(redis_module, "redis_client", BrokenRedis())
    monkeypatch.setattr(move_check, "engine_evaluate", lambda board: PositionEval(5, None, None))
    assert await move_check.evaluate_cached(START) == PositionEval(5, None, None)


async def test_record_dispute_validates_and_stores():
    fen = START.fen()
    with pytest.raises(DomainValueError):
        await move_check.record_dispute(fen, "not-a-move", 100, None)
    with pytest.raises(DomainValueError):
        await move_check.record_dispute(fen, "e2e5", 100, None)  # легального хода нет
    await move_check.record_dispute(fen, "e2e4", 120, 7)
    assert await redis_module.redis_client.llen(move_check.DISPUTES_KEY) == 1
