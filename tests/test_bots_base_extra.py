"""
Основа ботов (src/services/bots/base.py): поиск движка, загрузка книги, обращения к движку и отказы.

Движок — заглушка с готовыми ответами, Stockfish не запускается. Случайность выбора книги фиксируется seed.
"""

import json
import random
from contextlib import contextmanager

import chess
import chess.engine
import pytest

from src.services.bots import base as bots_base
from src.services.bots.base import HistoricalBot

BOARD = chess.Board("r2q1rk1/pp2bppp/2n1pn2/3p4/3P4/2NBPN2/PP3PPP/R2Q1RK1 w - - 0 10")
E4 = chess.Move.from_uci("e2e4")


# --- поиск движка -----------------------------------------------------------------------------------------------

def test_resolve_stockfish_path_order(monkeypatch, tmp_path):
    monkeypatch.undo()  # настоящие функции вместо заглушек conftest
    custom = tmp_path / "custom-engine"
    custom.write_text("x")
    assert bots_base.resolve_stockfish_path(str(custom)) == str(custom)

    root = tmp_path / "root"
    (root / "bin").mkdir(parents=True)
    monkeypatch.setattr(bots_base, "PROJECT_ROOT", root)
    monkeypatch.setattr(bots_base.shutil, "which", lambda name: None)
    real_exists = bots_base.os.path.exists  # Path.exists в Python 3.14 тоже идёт через os.path.exists
    monkeypatch.setattr(bots_base.os.path, "exists", lambda path: False)
    assert bots_base.resolve_stockfish_path("/no/such/path") is None  # нигде нет

    monkeypatch.setattr(bots_base.shutil, "which", lambda name: "/opt/stockfish")
    assert bots_base.resolve_stockfish_path() == "/opt/stockfish"  # из PATH

    monkeypatch.setattr(bots_base.shutil, "which", lambda name: None)
    monkeypatch.setattr(bots_base.os.path, "exists", lambda path: path == "/usr/games/stockfish" or real_exists(path))
    monkeypatch.setattr(bots_base.os.path, "isfile", lambda path: True)
    assert bots_base.resolve_stockfish_path() == "/usr/games/stockfish"  # пути Linux

    (root / "bin" / "stockfish").write_text("x")
    assert bots_base.resolve_stockfish_path() == str(root / "bin" / "stockfish")  # bin/ проекта — раньше PATH


# --- книга ---------------------------------------------------------------------------------------------------------

def test_book_merges_file_with_signature_moves_and_survives_broken_files(monkeypatch, tmp_path):
    books = tmp_path / "books"
    books.mkdir()
    monkeypatch.setattr(bots_base, "BOOKS_DIR", books)
    monkeypatch.setattr(bots_base, "PROJECT_ROOT", tmp_path)
    key = "start w KQkq -"
    fallback = {key: [("e2e4", 10, "signature"), ("d2d4", 5, "other")], "only": [("a2a3", 1, "x")]}
    (books / "demo.json").write_text(json.dumps({
        key: [["e2e4", 7, 100], ["g1f3", 3, 50], ["0000", 1, 1], ["bad", 1]],
        "empty": [["0000", 1, 1]],
    }), encoding="utf-8")
    book = bots_base.load_bot_opening_book("demo", fallback)
    assert {m[0] for m in book[key]} == {"e2e4", "g1f3", "d2d4"}  # ходы файла + фирменные, которых в файле нет
    assert "only" in book and "empty" not in book
    # Файл с мусором: ошибка в лог, остаётся книга-запас.
    (books / "broken.json").write_text("{не json", encoding="utf-8")
    assert bots_base.load_bot_opening_book("broken", fallback) == fallback


# --- обращения к движку ---------------------------------------------------------------------------------------------

class _Engine:
    def __init__(self, info=None, move=None, error: Exception | None = None):
        self.info, self.move, self.error = info, move, error

    def analyse(self, board, limit, **kwargs):
        if self.error:
            raise self.error
        return self.info

    def play(self, board, limit):
        if self.error:
            raise self.error
        return chess.engine.PlayResult(self.move, None)


def _install(monkeypatch, engine: _Engine, tmp_path):
    @contextmanager
    def fake(path, lease, options):
        yield engine

    monkeypatch.setattr(bots_base, "_engine", fake)
    binary = tmp_path / "stockfish"
    binary.write_text("x")
    return str(binary)


def _info(move: chess.Move | None, cp: int | None = 40) -> dict:
    score = chess.engine.PovScore(chess.engine.Cp(cp) if cp is not None else chess.engine.MateGiven, chess.WHITE)
    return {"score": score, **({"pv": [move]} if move else {})}


def test_analyse_without_path_or_with_engine_error_is_empty(monkeypatch, tmp_path):
    assert bots_base.analyse_with_stockfish(BOARD, None) == {}
    assert bots_base.analyse_with_stockfish(BOARD, "/no/such/engine") == {}
    path = _install(monkeypatch, _Engine(error=RuntimeError("сбой")), tmp_path)
    assert bots_base.analyse_with_stockfish(BOARD, path) == {}


def test_analyse_reads_single_and_multiple_lines_and_skips_empty_pv(monkeypatch, tmp_path):
    path = _install(monkeypatch, _Engine(info=_info(E4)), tmp_path)
    assert bots_base.analyse_with_stockfish(BOARD, path) == {E4: 40.0}  # ответ-словарь одной линии
    lines = [_info(E4), _info(None), _info(chess.Move.from_uci("d3e4"), cp=None)]
    path = _install(monkeypatch, _Engine(info=lines), tmp_path)
    assert set(bots_base.analyse_with_stockfish(BOARD, path)) == {E4, chess.Move.from_uci("d3e4")}


def test_reference_move_and_scoring_report_failures(monkeypatch, tmp_path):
    monkeypatch.undo()
    path = _install(monkeypatch, _Engine(move=E4), tmp_path)
    assert bots_base.strength_reference_move(BOARD, path, 1500, 0.1) == E4
    failing = _install(monkeypatch, _Engine(error=RuntimeError("сбой")), tmp_path)
    assert bots_base.strength_reference_move(BOARD, failing, 1500, 0.1) is None
    assert bots_base.score_move(BOARD, failing, E4, 5, 0.1) is None
    path = _install(monkeypatch, _Engine(info=_info(E4, cp=55)), tmp_path)
    assert bots_base.score_move(BOARD, path, E4, 5, 0.1) == 55.0
    path = _install(monkeypatch, _Engine(info={"score": chess.engine.PovScore(chess.engine.Cp(0), chess.WHITE)}), tmp_path)
    assert bots_base.score_move(BOARD, path, E4, 5, 0.1) == 0.0


# --- бот ---------------------------------------------------------------------------------------------------------------

class _Bot(HistoricalBot):
    bot_id = "extra"
    opening_book = {}


def test_active_engine_path_rules(tmp_path):
    existing = tmp_path / "engine"
    existing.write_text("x")
    assert _Bot(stockfish_path=str(tmp_path / "missing"))._get_active_engine_path() is None  # явный путь потерян
    assert _Bot(stockfish_path=str(existing))._get_active_engine_path() == str(existing)
    bot = _Bot()
    bot.stockfish_path = str(existing)
    assert bot._get_active_engine_path() == str(existing)
    bot.stockfish_path = str(tmp_path / "gone")  # найденный движок пропал — ищется заново
    assert bot._get_active_engine_path() == bots_base.resolve_stockfish_path()


def test_book_move_skips_bad_entries(monkeypatch):
    random.seed(1)
    bot = _Bot()
    key = bots_base.normalize_fen_key(chess.Board())
    bot.opening_book = {key: [("0000", 1, "n"), ("zzzz", 1, "n"), ("e2e5", 1, "n")]}
    assert bot._book_move(chess.Board()) is None  # ни одного легального хода
    bot.opening_book = {key: [("0000", 1, "n"), ("e2e4", 3, 12)]}
    move, comment = bot._book_move(chess.Board())
    assert move == E4 and comment["params"] == {"games": 12}  # число партий архива вместо фирменной фразы


def test_unscorable_reference_is_dropped(monkeypatch):
    bot = _Bot(stockfish_path="stockfish")
    monkeypatch.setattr(bots_base.os.path, "exists", lambda path: True)
    monkeypatch.setattr(bots_base, "analyse_with_stockfish", lambda **kwargs: {E4: 10.0})
    monkeypatch.setattr(bots_base, "strength_reference_move", lambda *a, **k: chess.Move.from_uci("d2d4"))
    monkeypatch.setattr(bots_base, "score_move", lambda *a, **k: None)
    candidates = bot._candidate_scores(chess.Board())
    assert candidates.reference is None and candidates.used_engine


def test_finished_game_cannot_be_played():
    with pytest.raises(ValueError):
        _Bot().choose_move("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
