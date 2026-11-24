"""Fischer random chess (task 21.3): setups, 960 castling, results, a bot move via the engine pool (stubbed)."""

from contextlib import contextmanager
from types import SimpleNamespace

import chess
import pytest

from src.core.errors import DomainValueError
from src.models.game import GameStatus
from src.services import chess960 as c960

API = "/api/v1/chess960"


def test_start_positions_and_castling_rules():
    assert c960.start_board(518).fen() == chess.STARTING_FEN
    board = c960.start_board(0)
    assert board.chess960 and board.board_fen() == "bbqnnrkr/pppppppp/8/8/8/8/PPPPPPPP/BBQNNRKR"
    with pytest.raises(DomainValueError):
        c960.start_board(960)
    # Castling in 960 is "the king takes its own rook". Setup 709 (RKBBQNNR): king b1 and rook a1 -> king c1,
    # rook d1 (long castling: the king moves right).
    game = c960.replay(709, ["e2e3", "e7e6", "d1e2", "d8e7", "d2d3", "d7d6", "c1d2", "c8d7", "b1a1"])
    assert game.sans[-1] == "O-O-O"
    assert game.board.piece_at(chess.C1).piece_type == chess.KING and game.board.piece_at(chess.D1).piece_type == chess.ROOK
    with pytest.raises(DomainValueError) as illegal:
        c960.replay(0, ["e2e5"])
    assert illegal.value.code == "illegal_move"


def test_outcome_by_mate_and_repetition():
    mate = c960.replay(518, ["f2f3", "e7e5", "g2g4", "d8h4"])
    assert c960.outcome(mate.board) == ("0-1", "checkmate")
    shuffle = ["g1f3", "g8f6", "f3g1", "f6g8"] * 2
    assert c960.outcome(c960.replay(518, shuffle).board) == ("1/2-1/2", "threefold_repetition")
    with pytest.raises(DomainValueError):
        c960.push(mate.board, "e1e2")


def test_bot_move_uses_the_pool_with_limited_strength(monkeypatch):
    seen = {}

    @contextmanager
    def acquire(options):
        seen["options"] = options

        def play(board, limit):
            seen["chess960"], seen["time"] = board.chess960, limit.time
            return SimpleNamespace(move=next(iter(board.legal_moves)))

        yield SimpleNamespace(play=play)

    monkeypatch.setattr(c960, "resolve_stockfish_path", lambda: "stockfish")
    monkeypatch.setattr(c960, "get_engine_pool", lambda path: SimpleNamespace(acquire=acquire))
    board = c960.start_board(100)
    assert c960.bot_move(board, 4) in board.legal_moves
    assert seen == {"options": {"UCI_LimitStrength": True, "UCI_Elo": 2200}, "chess960": True, "time": 0.25}


def test_api_game_flow(client, monkeypatch):
    monkeypatch.setattr(c960, "bot_move", lambda board, level: next(iter(board.legal_moves)))
    new = client.get(f"{API}/new", params={"number": 0}).json()
    assert new["number"] == 0 and new["moves"] == [] and new["fen"].startswith("bbqnnrkr/")
    assert 0 <= client.get(f"{API}/new").json()["number"] <= 959

    after = client.post(f"{API}/move", json={"number": 0, "moves": [], "move": "g2g3", "level": 1}).json()
    assert after["moves"][0] == "g2g3" and len(after["moves"]) == 2 and after["bot_move"] == after["moves"][1]
    assert after["sans"][0] == "g3" and after["result"] is None

    first = client.post(f"{API}/bot-move", json={"number": 0, "moves": []}).json()
    assert len(first["moves"]) == 1 and first["bot_move"] == first["moves"][0]

    bad = client.post(f"{API}/move", json={"number": 0, "moves": [], "move": "e2e5"})
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "illegal_move"
    over = client.post(f"{API}/move", json={"number": 518, "moves": ["f2f3", "e7e5", "g2g4", "d8h4"], "move": "e1f2"})
    assert over.json()["detail"]["code"] == "mini_game_over"
    assert client.get(f"{API}/new", params={"number": 960}).status_code == 422


def test_api_engine_unavailable(client, monkeypatch):
    def broken(board, level):
        raise c960.EngineUnavailableError("no engine")

    monkeypatch.setattr(c960, "bot_move", broken)
    reply = client.post(f"{API}/move", json={"number": 518, "moves": [], "move": "e2e4"})
    assert reply.status_code == 503 and reply.json()["detail"]["code"] == "engine_busy"


# --- Archive of finished games (21.3): replay and analysis ---

def _pgn_960(moves: list[str]) -> str:
    """The PGN of a finished game as the server stores it: Variant and FEN headers (Shredder-FEN) plus the movetext."""
    from src.services.odds import pgn_header
    board = c960.start_board(0)
    start = board.fen(shredder=True)
    body = []
    for index, uci in enumerate(moves):
        san = board.san(board.parse_uci(uci))
        board.push(board.parse_uci(uci))
        body.append(f"{index // 2 + 1}. {san}" if index % 2 == 0 else san)
    return f'{pgn_header(start)}\n[Result "1-0"]\n\n{" ".join(body)} 1-0'


def test_archive_record_replays_a_960_game():
    record = c960.archive_record(_pgn_960(["e2e4", "e7e5", "b2b3"]))
    assert record.moves == ["e2e4", "e7e5", "b2b3"] and len(record.fens) == 4
    assert record.fens[0] == record.start_fen == c960.start_board(0).fen(shredder=True)
    assert record.sans[0] == "e4" and record.result == "1-0"


def test_archive_record_rejects_standard_and_broken_games():
    standard = '[Event "t"]\n[Result "1-0"]\n\n1. e4 e5 1-0'
    for text in (standard, "", "garbage"):
        with pytest.raises(DomainValueError) as refused:
            c960.archive_record(text)
        assert refused.value.code == "not_chess960_game"


def test_evaluate_positions_goes_through_the_pool(monkeypatch):
    seen = {}

    @contextmanager
    def acquire(options):
        seen["options"] = options

        def analyse(board, limit):
            seen["chess960"] = board.chess960
            return {"score": chess.engine.PovScore(chess.engine.Cp(35), chess.WHITE)}
        yield SimpleNamespace(analyse=analyse)

    monkeypatch.setattr(c960, "resolve_stockfish_path", lambda: "stockfish")
    monkeypatch.setattr(c960, "get_engine_pool", lambda path: SimpleNamespace(acquire=acquire))
    mate = c960.start_board(518)
    for uci in ("f2f3", "e7e5", "g2g4", "d8h4"):
        mate.push_uci(uci)
    scores = c960.evaluate_positions([c960.start_board(0).fen(shredder=True), mate.fen(shredder=True)])
    assert scores == [35, -c960.MATE_SCORE_CP] and seen["chess960"] is True and seen["options"] == {}


async def _stored(db_session, test_user_1, test_user_2, pgn: str, status: GameStatus = GameStatus.COMPLETED) -> int:
    from src.models.game import Game
    game = Game(white_player_id=test_user_1.id, black_player_id=test_user_2.id, status=status, result="1-0",
                termination="checkmate", is_rated=False, base_time_ms=300000, increment_ms=0, pgn=pgn)
    db_session.add(game)
    await db_session.commit()
    return game.id


async def test_api_archive_and_analysis(client, db_session, test_user_1, test_user_2, monkeypatch):
    stored = await _stored(db_session, test_user_1, test_user_2, _pgn_960(["e2e4", "e7e5"]))
    view = client.get(f"{API}/archive/{stored}").json()
    assert view["moves"] == ["e2e4", "e7e5"] and len(view["fens"]) == 3 and view["result"] == "1-0"

    monkeypatch.setattr(c960, "evaluate_positions", lambda fens: [10] * len(fens))
    analysis = client.get(f"{API}/archive/{stored}/analysis").json()
    assert analysis == {"game_id": stored, "scores": [10, 10, 10], "complete": True}

    standard = await _stored(db_session, test_user_1, test_user_2, '[Result "1-0"]\n\n1. e4 e5 1-0')
    assert client.get(f"{API}/archive/{standard}").json()["detail"]["code"] == "not_chess960_game"
    running = await _stored(db_session, test_user_1, test_user_2, _pgn_960(["e2e4"]), GameStatus.IN_PROGRESS)
    assert client.get(f"{API}/archive/{running}").status_code == 404
    assert client.get(f"{API}/archive/999999").status_code == 404


async def test_api_archive_analysis_engine_unavailable(client, db_session, test_user_1, test_user_2, monkeypatch):
    from src.services.engine_pool import EngineUnavailableError

    def broken(fens):
        raise EngineUnavailableError("no engine")

    monkeypatch.setattr(c960, "evaluate_positions", broken)
    stored = await _stored(db_session, test_user_1, test_user_2, _pgn_960(["e2e4"]))
    reply = client.get(f"{API}/archive/{stored}/analysis")
    assert reply.status_code == 503 and reply.json()["detail"]["code"] == "engine_busy"
