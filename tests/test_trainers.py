# --- FILE: tests/test_trainers.py ---
"""Trainer framework (task 19.1): recording a result, the level's personal record, records and history for the chart."""

import re
from pathlib import Path

from src.api.trainers import TRAINERS

API = "/api/v1/trainers"
CLIENT_IDS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "services" / "trainers.ts"


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def result(**extra) -> dict:
    return {"trainer": "quiet_path", "level": 2, "score": 80, "time_ms": 30_000, "mistakes": 1, **extra}


def test_records_per_level(client, token_user_1):
    first = client.post(f"{API}/results", headers=auth(token_user_1), json=result()).json()
    assert first == {"record": True, "best": 80}
    worse = client.post(f"{API}/results", headers=auth(token_user_1), json=result(score=50)).json()
    assert worse == {"record": False, "best": 80}
    other_level = client.post(f"{API}/results", headers=auth(token_user_1), json=result(level=3, score=10)).json()
    assert other_level["record"] is True
    records = client.get(f"{API}/records", headers=auth(token_user_1)).json()["records"]
    assert records == {"quiet_path": {"best": 80, "max_level": 3, "attempts": 3}}


def test_history_oldest_first(client, token_user_1):
    for score in (10, 20, 30):
        client.post(f"{API}/results", headers=auth(token_user_1), json=result(trainer="knight_route", score=score))
    assert client.post(f"{API}/results", headers=auth(token_user_1), json=result(trainer="tail")).status_code == 200
    history = client.get(f"{API}/history/knight_route", headers=auth(token_user_1)).json()["results"]
    assert [r["score"] for r in history] == [10, 20, 30]


def test_results_are_private(client, token_user_1, token_user_2):
    client.post(f"{API}/results", headers=auth(token_user_1), json=result())
    assert client.get(f"{API}/records", headers=auth(token_user_2)).json() == {"records": {}}


def test_validation(client, token_user_1):
    unknown = client.post(f"{API}/results", headers=auth(token_user_1), json=result(trainer="nope"))
    assert unknown.status_code == 404 and unknown.json()["detail"]["code"] == "trainer_not_found"
    assert client.post(f"{API}/results", headers=auth(token_user_1), json=result(level=0)).status_code == 422
    assert client.post(f"{API}/results", headers=auth(token_user_1), json=result(score=-1)).status_code == 422
    assert client.post(f"{API}/results", json=result()).status_code == 401


def test_coordinate_trainers_accepted(client, token_user_1):
    """Task 19.2: coordinate trainers; level 1-8 is a combination of attempt settings."""
    for trainer in ("coord_find", "coord_name", "coord_color", "coord_diagonal", "memory_position", "memory_game",
                    "board_placement", "knight_tour", "blind_move", "blind_where",
                    "calc_checks", "calc_exchange", "calc_distance", "calc_square", "calc_eval"):
        response = client.post(f"{API}/results", json=result(trainer=trainer, level=8, score=12), headers=auth(token_user_1))
        assert response.status_code == 200 and response.json()["record"] is True


def test_server_accepts_every_client_trainer():
    """The client saves results under TRAINER_IDS; a code missing on the server is answered with 404 and the result is lost."""
    source = CLIENT_IDS.read_text(encoding="utf-8")
    block = re.search(r"TRAINER_IDS = \[(.*?)\] as const", source, re.S)
    assert block is not None
    assert set(re.findall(r"'([a-z_0-9]+)'", block.group(1))) == set(TRAINERS)


def test_miniatures_result_is_saved(client, token_user_1):
    saved = client.post(f"{API}/results", headers=auth(token_user_1), json=result(trainer="miniatures", level=1))
    assert saved.status_code == 200
