# --- FILE: tests/test_defense_drills.py ---
"""
Защитные упражнения (таск 13.6): критерии отбора, готовая выборка data/puzzles/defense_drills.csv.gz и API
«Что грозит соперник?» / «Не зевни» — угроза и верные ходы не уходят клиенту до ответа, прогресс темы считается.
"""

import itertools
import pathlib

import chess
import chess.engine
import pytest
from sqlalchemy import func, select

from scripts.dev.build_defense_drills import make_score_after
from src.core.errors import DomainValueError
from src.db import redis as redis_module
from src.models.puzzle import DefenseDrill
from src.services import defense_drills as drills
from src.services.bots.base import resolve_stockfish_path
from src.services.puzzle_import import read_subset
from src.services.puzzles import STAGES, PuzzleError

API = "/api/v1/puzzles"
ROWS = list(drills.read_drills())
SUBSET = {row["PuzzleId"]: row for row in read_subset()}


def _first(kind: str) -> dict:
    return next(row for row in ROWS if row["Kind"] == kind)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- критерии отбора на поддельной оценке ----------------------------------------------------------------------

def _fake_analyse(table: dict[str, dict[str, int]]) -> drills.Analyse:
    """Оценки по позиции (fen без счётчиков) — как движок: лучшие multipv ходов, только среди moves, если заданы."""

    def analyse(board: chess.Board, multipv: int, moves: list[str] | None) -> drills.MoveScores:
        scores = table[board.board_fen() + (" w" if board.turn else " b")]
        items = [(uci, s) for uci, s in scores.items() if moves is None or uci in moves]
        items.sort(key=lambda item: -item[1])
        return {uci: (s, "a1a2") for uci, s in items[:multipv]}

    return analyse


def _key(board: chess.Board) -> str:
    return board.board_fen() + (" w" if board.turn else " b")


def _threat_source() -> tuple[dict, chess.Board, chess.Board]:
    row = SUBSET[_first("threat")["SourceId"]]
    moves = row["Moves"].split()
    attacker = chess.Board(row["FEN"])
    attacker.push_uci(moves[0])
    defender = drills.defender_position(row["FEN"], moves)
    assert defender is not None
    return row, attacker, defender


def test_real_threat_with_few_defenses_is_accepted():
    row, attacker, defender = _threat_source()
    threat = row["Moves"].split()[1]
    legal = [m.uci() for m in defender.legal_moves]
    table = {
        _key(attacker): {threat: 500, "x1": 100},
        _key(defender): {legal[0]: 20, legal[1]: -40, **{uci: -600 for uci in legal[2:]}},
    }
    drill = drills.threat_drill(row["FEN"], row["Moves"].split(), _fake_analyse(table))
    assert drill == {"fen": defender.fen(), "threat": threat, "good": sorted(legal[:2])}


def test_threat_rejected_when_any_move_defends_or_threat_is_weak():
    row, attacker, defender = _threat_source()
    moves = row["Moves"].split()
    legal = [m.uci() for m in defender.legal_moves]
    everything_defends = {_key(attacker): {moves[1]: 500}, _key(defender): {uci: 0 for uci in legal}}
    assert drills.threat_drill(row["FEN"], moves, _fake_analyse(everything_defends)) is None
    # «Ничего не делать» почти не хуже лучшей защиты — угрозы нет.
    weak = {_key(attacker): {moves[1]: 100}, _key(defender): {legal[0]: 0, **{u: -500 for u in legal[1:]}}}
    assert drills.threat_drill(row["FEN"], moves, _fake_analyse(weak)) is None
    # Тактика задачи — не лучший ход соперника: угроза не определена однозначно.
    other_best = {_key(attacker): {moves[1]: 300, "x1": 600}, _key(defender): {legal[0]: 0}}
    assert drills.threat_drill(row["FEN"], moves, _fake_analyse(other_best)) is None


def test_blunder_drill_offers_safe_blunder_and_natural_trap():
    row = SUBSET[_first("blunder")["SourceId"]]
    board = chess.Board(row["FEN"])
    blunder = row["Moves"].split()[0]
    others = [m.uci() for m in board.legal_moves if m.uci() != blunder]
    safe, trap, absurd = others[0], others[1], others[2]
    deep = {safe: 50, blunder: -400, trap: -350, absurd: -900}
    looks = {safe: 30, blunder: 40, trap: 35, absurd: -500}
    drill = drills.blunder_drill(row["FEN"], row["Moves"].split(), _fake_analyse({_key(board): deep}),
                                 _fake_analyse({_key(board): looks}), seed="x")
    assert drill is not None
    assert sorted(drill["choices"]) == sorted([safe, blunder, trap])  # ход-нелепица не предлагается
    assert drill["good"] == [safe]
    assert set(drill["refutations"]) == {blunder, trap}
    # Зевок на самом деле не проигрывает — упражнения нет.
    mild = {**deep, blunder: -100}
    assert drills.blunder_drill(row["FEN"], row["Moves"].split(), _fake_analyse({_key(board): mild}),
                                _fake_analyse({_key(board): looks}), seed="x") is None
    # «Ловушка» хуже лучшего на 300, но всё ещё выигрывает (+3): это не зевок — упражнения нет.
    still_winning = {safe: 600, blunder: -400, trap: 300, absurd: -900}
    assert drills.blunder_drill(row["FEN"], row["Moves"].split(), _fake_analyse({_key(board): still_winning}),
                                _fake_analyse({_key(board): looks}), seed="x") is None


# --- готовая выборка -----------------------------------------------------------------------------------------

def test_dataset_size_coverage_and_validity():
    assert len(ROWS) >= 500
    for kind in drills.KINDS:
        for stage in STAGES:
            assert sum(1 for r in ROWS if r["Kind"] == kind and int(r["Stage"]) == stage) >= 50, (kind, stage)
    invalid = [row["SourceId"] for row in ROWS if not drills.validate_drill_row(row)]
    assert invalid == []
    # Упражнения построены из задач выборки, без повторов внутри вида.
    assert all(row["SourceId"] in SUBSET for row in ROWS)
    keys = [(row["Kind"], row["SourceId"]) for row in ROWS]
    assert len(keys) == len(set(keys))


@pytest.mark.skipif(resolve_stockfish_path() is None, reason="Stockfish binary not available")
def test_sample_rechecked_by_engine():
    """Выборочная перепроверка движком той же проверкой, что и при сборке: верный ход лучше неверных."""
    sample = [*itertools.islice((r for r in ROWS if r["Kind"] == "blunder"), 0, 400, 100),
              *itertools.islice((r for r in ROWS if r["Kind"] == "threat"), 0, 400, 100)]
    with chess.engine.SimpleEngine.popen_uci(resolve_stockfish_path()) as engine:
        score_after = make_score_after(engine, depth=16)
        # Допуски вдвое мягче сборки: у другой версии Stockfish (в CI — из пакетов) пограничные оценки расходятся,
        # а грубую ошибку («проигрывающий» ход на деле выигрывает) проверка всё равно ловит.
        failed = [row["SourceId"] for row in sample if not drills.verify_drill(
            row, score_after, margin=drills.VERIFY_MARGIN // 2, losing=drills.LOSING // 2)]
    assert failed == []


# --- API -----------------------------------------------------------------------------------------------------

@pytest.fixture
async def seeded(db_session):
    report = await drills.import_drills(db_session, [_first("threat"), _first("blunder")])
    assert report == {"added": 2, "updated": 0, "removed": 0, "invalid": 0}
    return {"threat": _first("threat"), "blunder": _first("blunder")}


def _next(client, token, kind: str) -> dict:
    response = client.get(f"{API}/defense/next", params={"kind": kind}, headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


def _other_square(row: dict) -> str:
    taken = {row["Threat"][:2], row["Threat"][2:4]}
    return next(chess.square_name(sq) for sq in chess.SQUARES if chess.square_name(sq) not in taken)


async def test_threat_drill_found_and_defended_counts_clean(client, token_user_1, seeded):
    row = seeded["threat"]
    view = _next(client, token_user_1, "threat")
    assert set(view) == {"id", "kind", "theme", "fen", "color", "rating", "stage", "choices"}
    assert view["theme"] == "find_the_threat" and view["choices"] == [] and view["fen"] == row["FEN"]

    shown = client.post(f"{API}/defense/{view['id']}/threat", json={"square": row["Threat"][2:4]},
                        headers=_auth(token_user_1)).json()
    assert shown["correct"] and shown["threat"] == row["Threat"]

    body = client.post(f"{API}/defense/{view['id']}/answer", json={"move": row["Good"].split()[0]},
                       headers=_auth(token_user_1)).json()
    assert body["correct"] and body["clean"]
    assert body["training"]["theme"] == "find_the_threat" and body["training"]["recent"] == "1"
    # Упражнение закончено — ответы по нему больше не принимаются.
    again = client.post(f"{API}/defense/{view['id']}/answer", json={"move": row["Good"].split()[0]},
                        headers=_auth(token_user_1))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "drill_not_active"


async def test_missed_threat_makes_the_attempt_not_clean(client, token_user_1, seeded):
    row = seeded["threat"]
    view = _next(client, token_user_1, "threat")
    # Сначала — угроза: защищаться до неё нельзя.
    early = client.post(f"{API}/defense/{view['id']}/answer", json={"move": row["Good"].split()[0]},
                        headers=_auth(token_user_1))
    assert early.status_code == 409 and early.json()["detail"]["code"] == "drill_wrong_step"

    shown = client.post(f"{API}/defense/{view['id']}/threat", json={"square": _other_square(row)},
                        headers=_auth(token_user_1)).json()
    assert not shown["correct"] and shown["threat"] == row["Threat"]
    body = client.post(f"{API}/defense/{view['id']}/answer", json={"move": row["Good"].split()[0]},
                       headers=_auth(token_user_1)).json()
    assert body["correct"] and not body["clean"] and body["training"]["recent"] == "0"


async def test_blunder_check_choice_and_refutations(client, token_user_1, seeded):
    row = seeded["blunder"]
    view = _next(client, token_user_1, "blunder")
    assert view["theme"] == "blunder_check" and sorted(view["choices"]) == sorted(row["Choices"].split())
    good = row["Good"]
    losing = next(uci for uci in view["choices"] if uci != good)

    board = chess.Board(row["FEN"])
    outside = next(m.uci() for m in board.legal_moves if m.uci() not in view["choices"])
    refused = client.post(f"{API}/defense/{view['id']}/answer", json={"move": outside}, headers=_auth(token_user_1))
    assert refused.status_code == 400 and refused.json()["detail"]["code"] == "drill_not_a_choice"

    body = client.post(f"{API}/defense/{view['id']}/answer", json={"move": losing},
                       headers=_auth(token_user_1)).json()
    assert not body["correct"] and body["good"] == [good]
    assert set(body["refutations"]) == set(view["choices"]) - {good}


async def test_unknown_kind_and_training_overview(client, token_user_1, seeded):
    response = client.get(f"{API}/defense/next", params={"kind": "nonsense"}, headers=_auth(token_user_1))
    assert response.status_code == 400 and response.json()["detail"]["code"] == "unknown_drill_kind"

    overview = client.get(f"{API}/training", headers=_auth(token_user_1)).json()
    themes = {t["code"]: t for t in overview["themes"]}
    stage = int(seeded["threat"]["Stage"])
    assert themes["find_the_threat"]["available"][stage - 1] >= 1
    assert sum(themes["blunder_check"]["available"]) >= 1


async def test_import_is_idempotent(db_session, seeded):
    assert await drills.import_drills(db_session, [_first("threat"), _first("blunder")]) == {
        "added": 0, "updated": 0, "removed": 0, "invalid": 0}


async def test_import_syncs_with_the_dataset(db_session, seeded):
    """Изменённое упражнение обновляется, выпавшее из выборки (забраковано перепроверкой) — удаляется."""
    from sqlalchemy import select

    from src.models.puzzle import DefenseDrill

    changed = {**_first("threat"), "Rating": "2222"}
    broken = {**_first("blunder"), "Good": "a1a1"}
    report = await drills.import_drills(db_session, [changed, broken])
    assert report == {"added": 0, "updated": 1, "removed": 1, "invalid": 1}
    stored = (await db_session.execute(select(DefenseDrill))).scalars().all()
    assert [(d.kind, d.rating) for d in stored] == [("threat", 2222)]


# --- Дополнительное покрытие: отказы отбора, файл выборки, проверка строк, выдача и ответы -------------------------





def _scripted(table: dict[str, dict[str, tuple[int, str | None]]]) -> drills.Analyse:
    """Оценки с произвольным ответом соперника (в том числе None) — для проверки отказов."""

    def analyse(board: chess.Board, multipv: int, moves: list[str] | None) -> drills.MoveScores:
        scores = table.get(_key(board), {})
        items = sorted(((u, v) for u, v in scores.items() if moves is None or u in moves), key=lambda i: -i[1][0])
        return dict(items[:multipv])

    return analyse


def test_defender_position_refuses_checks_and_cramped_defender():
    # Ошибка даёт шах — «что грозит соперник» не построить.
    assert drills.defender_position("4k3/8/8/8/8/8/4R3/4K3 w - - 0 1", ["e2e7"]) is None
    # После пустого хода у обороняющегося единственный легальный ход — выбирать не из чего.
    assert drills.defender_position("k7/8/8/8/8/P5q1/8/7K w - - 0 1", ["a3a4"]) is None


def test_threat_drill_refusals_and_threat_outside_top():
    row, attacker, defender = _threat_source()
    moves = row["Moves"].split()
    threat = moves[1]
    legal = [m.uci() for m in defender.legal_moves]
    good_defense = {legal[0]: (20, None), **{uci: (-600, None) for uci in legal[1:]}}
    fen = row["FEN"]
    assert drills.threat_drill(fen, moves, _scripted({})) is None  # движок молчит об атаке
    # Угрозы нет среди лучших ходов, и отдельная оценка её не даёт.
    assert drills.threat_drill(fen, moves, _scripted({_key(attacker): {"x1": (500, None)}})) is None

    # Угроза вне лучших ходов, но оценивается отдельно, — упражнение строится.
    def with_separate_threat(board, multipv, only):
        if board.fen() == attacker.fen() and only == [threat]:
            return {threat: (500, None)}
        return _scripted({_key(attacker): {"x1": (500, None)}, _key(defender): good_defense})(board, multipv, only)

    assert drills.threat_drill(fen, moves, with_separate_threat)["threat"] == threat
    # Нет оценки защит / позиция уже проиграна / защит слишком много.
    attack_only = {_key(attacker): {threat: (500, None)}}
    assert drills.threat_drill(fen, moves, _scripted(attack_only)) is None
    lost = {**attack_only, _key(defender): {uci: (-900, None) for uci in legal}}
    assert drills.threat_drill(fen, moves, _scripted(lost)) is None
    many = {**attack_only, _key(defender): {uci: (0, None) for uci in legal[:5]} | {u: (-900, None) for u in legal[5:]}}
    assert drills.threat_drill(fen, moves, _scripted(many)) is None


def test_blunder_drill_refusals():
    row = SUBSET[_first("blunder")["SourceId"]]
    moves = row["Moves"].split()
    board = chess.Board(row["FEN"])
    blunder = moves[0]
    others = [m.uci() for m in board.legal_moves if m.uci() != blunder]
    safe, trap = others[0], others[1]
    key = _key(board)
    deep = {safe: (50, None), blunder: (-400, "a1a2"), trap: (-350, "a1a2")}
    looks = {safe: (30, None), blunder: (40, None), trap: (35, None)}

    def run(deep_table, looks_table):
        return drills.blunder_drill(row["FEN"], moves, _scripted({key: deep_table}), _scripted({key: looks_table}), "s")

    assert run({}, looks) is None  # нет оценки
    assert run({blunder: (50, None)}, looks) is None  # лучший ход и есть зевок
    assert run({safe: (-900, None)}, looks) is None  # позиция уже проиграна
    assert run(deep, {}) is None  # мелкий поиск пуст
    assert run(deep, {safe: (30, None), blunder: (40, None)}) is None  # естественной ловушки нет
    assert run({safe: (50, None), trap: (-350, "a1a2")}, looks) is None  # зевок не оценён глубоко
    assert run({safe: (50, None), blunder: (-400, "a1a2"), trap: (0, None)}, looks) is None  # ловушка не проигрывает
    assert run({**deep, trap: (-350, None)}, looks) is None  # нет опровержения


def test_write_and_read_drills_roundtrip(tmp_path: pathlib.Path):
    path = tmp_path / "drills.csv.gz"
    assert drills.write_drills(ROWS[:3], path) == 3
    assert list(drills.read_drills(path)) == ROWS[:3]


def test_validate_drill_row_rejections():
    threat, blunder = _first("threat"), _first("blunder")
    assert drills.validate_drill_row(threat) and drills.validate_drill_row(blunder)
    assert not drills.validate_drill_row({**threat, "Kind": "other"})
    assert not drills.validate_drill_row({**threat, "FEN": "not a fen"})
    assert not drills.validate_drill_row({**threat, "Good": ""})
    assert not drills.validate_drill_row({**threat, "Threat": "a1a1"})  # угроза нелегальна для соперника
    assert not drills.validate_drill_row({**blunder, "Choices": blunder["Choices"].split()[0]})
    assert not drills.validate_drill_row({k: v for k, v in threat.items() if k != "Good"})  # нет столбца
    assert not drills.validate_drill_row({**blunder, "Refutations": "a1a2"})  # пара без разделителя


async def test_import_without_prune_and_duplicate_rows(db_session, seeded):
    report = await drills.import_drills(db_session, [_first("threat"), _first("threat")], prune=False)
    assert report == {"added": 0, "updated": 0, "removed": 0, "invalid": 0}
    assert await db_session.scalar(select(func.count()).select_from(DefenseDrill)) == 2


async def test_pick_falls_back_to_other_stage_and_reports_empty_base(db_session, test_user_1):
    with pytest.raises(PuzzleError) as empty:
        await drills.pick(db_session, test_user_1, "threat")
    assert empty.value.status == 404
    await drills.import_drills(db_session, [_first("threat")])
    first = await drills.pick(db_session, test_user_1, "threat")
    again = await drills.pick(db_session, test_user_1, "threat")  # недавнее исключено, но других нет — повтор
    assert first.id == again.id
    # На своей ступени упражнений нет — берётся любое этого вида.
    first.stage = first.stage % 4 + 1
    await db_session.commit()
    assert (await drills.pick(db_session, test_user_1, "threat")).id == first.id


async def test_answer_and_threat_input_errors(client, db_session, token_user_1, test_user_1, seeded):
    row = seeded["threat"]
    view = _next(client, token_user_1, "threat")
    bad_square = client.post(f"{API}/defense/{view['id']}/threat", json={"square": "z9"}, headers=_auth(token_user_1))
    assert bad_square.status_code == 400 and bad_square.json()["detail"]["code"] == "invalid_square"
    client.post(f"{API}/defense/{view['id']}/threat", json={"square": row["Threat"][2:4]}, headers=_auth(token_user_1))
    for move in ("zzzz", "a1a1"):
        response = client.post(f"{API}/defense/{view['id']}/answer", json={"move": move}, headers=_auth(token_user_1))
        assert response.status_code in (400, 422)
    # Упражнение удалено, пока игрок его решал: запись об активном упражнении сбрасывается.
    await db_session.execute(DefenseDrill.__table__.delete())
    await db_session.commit()
    with pytest.raises(PuzzleError):
        await drills._active(db_session, test_user_1, view["id"], "move")
    assert await redis_module.redis_client.get(drills._session_key(test_user_1.id)) is None


async def test_answer_illegal_move_raises_domain_error(db_session, test_user_1, seeded):
    drill = await drills.pick(db_session, test_user_1, "threat")
    await drills.show_threat(db_session, test_user_1, drill.id, "a1")
    with pytest.raises(DomainValueError):
        await drills.answer(db_session, test_user_1, drill.id, "zzzz")
    with pytest.raises(DomainValueError):
        await drills.answer(db_session, test_user_1, drill.id, "a1a1")
