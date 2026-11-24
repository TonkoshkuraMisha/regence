"""
The weekly tournament against legends (task 26.1): the pure rules (week, line-up, points, ranking), the client path
(GET /events/weekly-legends, POST .../start, POST /bots/save-game with weekly=true) and the Monday results.
"""

import datetime as dt

import chess
import pytest
from sqlalchemy import select

from src.core.security import create_user_token
from src.models.social import Notification
from src.models.user import User
from src.models.weekly_legends import WeeklyLegendGame
from src.services import weekly_legends
from src.services import weekly_legends_rules as rules
from src.services.bots import base as bots_base

EVENT = "/api/v1/events/weekly-legends"
SAVE = "/api/v1/bots/save-game"
# White mates in 4 moves (Scholar's mate): the player as White wins.
SCHOLARS_MATE = ["e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6", "h5f7"]
TC = {"base_time_ms": rules.BASE_TIME_MS, "increment_ms": rules.INCREMENT_MS}


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def no_engine(monkeypatch):
    monkeypatch.setattr(bots_base, "analyse_with_stockfish", lambda **kwargs: {})


def play_bot_moves(client, token, bot_id: str, moves: list[str], color: str = "white") -> None:
    """The opponent's move requests, as the client makes them (the fair-session check sees growing plies)."""
    board = chess.Board()
    for uci in moves:
        if (board.turn == chess.WHITE) != (color == "white"):
            assert client.post("/api/v1/bots/move", headers=auth(token),
                               json={"bot_id": bot_id, "fen": board.fen()}).status_code == 200
        board.push_uci(uci)


def save(client, token, bot_id: str, moves=SCHOLARS_MATE, result="1-0", color="white", **extra):
    body = {"bot_id": bot_id, "player_color": color, "result": result, "moves_uci": moves, "weekly": True, **TC,
            **extra}
    return client.post(SAVE, headers=auth(token), json=body)


def start(client, token, bot_id: str, color="white"):
    return client.post(f"{EVENT}/start", headers=auth(token), json={"bot_id": bot_id, "color": color})


# --- Pure rules -------------------------------------------------------------------------------------------------------

def test_week_starts_on_monday_and_ends_next_monday():
    assert rules.week_start(dt.date(2026, 11, 29)) == dt.date(2026, 11, 23)  # a Sunday
    assert rules.week_end(dt.date(2026, 11, 23)) == dt.datetime(2026, 11, 30, tzinfo=dt.UTC)


def test_line_up_is_one_per_strength_band_and_changes_by_week():
    bots = [(f"b{i:02d}", 1000 + i * 50) for i in range(20)]
    week = rules.pick_legends(dt.date(2026, 11, 23), bots)
    assert len(week) == rules.LEGENDS_PER_WEEK
    assert week == rules.pick_legends(dt.date(2026, 11, 23), list(reversed(bots)))  # same for every process
    bands = [int(b[1:]) // 4 for b in week]  # 20 bots, 5 bands of 4
    assert bands == list(range(rules.LEGENDS_PER_WEEK))
    weeks = {tuple(rules.pick_legends(dt.date(2026, 11, 23) + dt.timedelta(weeks=n), bots)) for n in range(8)}
    assert len(weeks) > 1
    assert rules.pick_legends(dt.date(2026, 11, 23), bots[:3]) == ["b00", "b01", "b02"]


def test_points_and_ranking():
    assert rules.player_half_points("1-0", "white") == 2 and rules.player_half_points("1-0", "black") == 0
    assert rules.player_half_points("1/2-1/2", "black") == 1
    t0 = dt.datetime(2026, 11, 24, tzinfo=dt.UTC)
    a = rules.Entry(1, 6, 2, 4, t0 + dt.timedelta(hours=2))
    b = rules.Entry(2, 6, 3, 3, t0 + dt.timedelta(hours=3))  # same points, more wins
    c = rules.Entry(3, 6, 2, 4, t0 + dt.timedelta(hours=1))  # same points and wins as a, got there earlier
    assert [e.user_id for e in rules.rank([a, b, c])] == [2, 3, 1]


# --- Client path ------------------------------------------------------------------------------------------------------

def test_guest_sees_the_line_up(client):
    body = client.get(EVENT).json()
    assert len(body["legends"]) == rules.LEGENDS_PER_WEEK
    assert body["base_time_ms"] == rules.BASE_TIME_MS and body["standings"]["top"] == []
    assert all(legend["points"] is None for legend in body["legends"])
    assert client.post(f"{EVENT}/start", json={"bot_id": body["legends"][0]["bot_id"]}).status_code == 401


async def test_a_fair_win_counts_once_and_enters_the_standings(client, db_session, test_user_1, token_user_1):
    bot_id = client.get(EVENT).json()["legends"][0]["bot_id"]
    assert start(client, token_user_1, "no-such-bot").status_code == 404
    opened = start(client, token_user_1, bot_id).json()
    assert opened["color"] == "white" and opened["base_time_ms"] == rules.BASE_TIME_MS

    play_bot_moves(client, token_user_1, bot_id, SCHOLARS_MATE)
    saved = save(client, token_user_1, bot_id)
    assert saved.status_code == 200, saved.text
    assert saved.json()["weekly"] == {"points": 1.0, "forfeit": None, "total": 1.0}

    event = client.get(EVENT, headers=auth(token_user_1)).json()
    mine = next(legend for legend in event["legends"] if legend["bot_id"] == bot_id)
    assert mine["points"] == 1.0 and event["open_game"] is None
    assert event["standings"]["me"] == {"place": 1, "username": test_user_1.username, "avatar": None, "points": 1.0,
                                        "wins": 1, "games": 1}
    # The same legend once a week; saving without an open weekly game is refused.
    again = start(client, token_user_1, bot_id)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "weekly_legend_played"
    assert save(client, token_user_1, bot_id).status_code == 409


def test_a_hint_or_another_time_control_is_a_loss(client, token_user_1):
    legends = [legend["bot_id"] for legend in client.get(EVENT).json()["legends"]]
    start(client, token_user_1, legends[0])
    board = chess.Board()
    # A move request for the player's own side is an engine hint.
    client.post("/api/v1/bots/move", headers=auth(token_user_1), json={"bot_id": legends[0], "fen": board.fen()})
    hinted = save(client, token_user_1, legends[0]).json()["weekly"]
    assert hinted["points"] == 0 and hinted["forfeit"] == "engine_hint"

    start(client, token_user_1, legends[1])
    play_bot_moves(client, token_user_1, legends[1], SCHOLARS_MATE)
    blitz = save(client, token_user_1, legends[1], base_time_ms=180_000, increment_ms=0).json()["weekly"]
    assert blitz["points"] == 0 and blitz["forfeit"] == "time_control"


async def test_an_abandoned_game_counts_as_a_loss(client, db_session, test_user_1, token_user_1):
    legends = [legend["bot_id"] for legend in client.get(EVENT).json()["legends"]]
    start(client, token_user_1, legends[0])
    play_bot_moves(client, token_user_1, legends[0], SCHOLARS_MATE[:2])  # the game has started
    second = start(client, token_user_1, legends[1]).json()
    assert second["abandoned"] == legends[0]
    row = (await db_session.execute(select(WeeklyLegendGame).where(WeeklyLegendGame.bot_id == legends[0]))).scalar_one()
    assert row.half_points == 0 and row.forfeit == "abandoned" and row.game_id is None


async def test_monday_notifies_last_weeks_places_once(db_session, test_user_1, test_user_2):
    last_week = rules.week_start(dt.date.today()) - dt.timedelta(days=7)
    db_session.add_all([
        WeeklyLegendGame(week=last_week, user_id=test_user_1.id, bot_id="morphy", half_points=1),
        WeeklyLegendGame(week=last_week, user_id=test_user_2.id, bot_id="morphy", half_points=2),
    ])
    await db_session.commit()
    assert await weekly_legends.notify_results(db_session) == 2
    assert await weekly_legends.notify_results(db_session) == 0
    notes = (await db_session.execute(select(Notification).where(Notification.kind == "weekly_legends")
                                      .order_by(Notification.user_id))).scalars().all()
    assert [(n.payload["place"], n.payload["points"], n.payload["players"]) for n in notes] == [(2, 0.5, 2), (1, 1.0, 2)]


async def test_flagged_players_are_not_in_the_table(client, db_session, test_user_1):
    test_user_1.is_cheater = True
    db_session.add(WeeklyLegendGame(week=rules.week_start(dt.date.today()), user_id=test_user_1.id, bot_id="morphy",
                                    half_points=2))
    await db_session.commit()
    token = create_user_token(await db_session.get(User, test_user_1.id))
    assert client.get(EVENT, headers=auth(token)).json()["standings"] == {"top": [], "me": None, "players": 0}
