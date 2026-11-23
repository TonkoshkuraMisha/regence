# --- FILE: tests/test_tournament_rating.py ---
"""
All tournaments are rated (owner decision, 15.11): a player's tournament game changes their rating in the tournament's
time-control category; an abandoned started game and a resignation mid-game are a rated loss;
unplayed games do not change the rating.
"""

from sqlalchemy import select

from src.models.game import Game
from src.models.user import User
from src.services.rating import classify_time_control
from tests.test_tournament_play import SAVE, auth, create, my_game, save_body, start

CATEGORY = classify_time_control(300_000, 2_000)
# Weak opponents (archetypes ~800-1000): losing to them noticeably lowers the player's rating from 1200.
WEAK = [{"kind": "archetype", "id": a} for a in ("rusher", "quiet", "pawn_keeper")]


async def _rating(db, user_id: int) -> tuple[int, int]:
    user = await db.get(User, user_id)
    await db.refresh(user)
    return user.rating_for(CATEGORY), user.games_played_for(CATEGORY)


async def test_win_against_stronger_bot_raises_rating(client, token_user_1, test_user_1, db_session, published_simulations):
    before, games = await _rating(db_session, test_user_1.id)
    t = create(client, token_user_1)
    game, color, opponent = my_game(t)
    start(client, token_user_1, t, game)
    # Fool's mate: playing Black this is a win, playing White a loss.
    saved = client.post(SAVE, headers=auth(token_user_1), json=save_body(game, color, opponent)).json()
    after, games_after = await _rating(db_session, test_user_1.id)
    won = color == "black"
    assert (after > before) is won and (after < before) is not won
    assert games_after == games + 1
    assert (saved["rating_before"], saved["rating_after"], saved["rating_delta"]) == (before, after, after - before)
    record = (await db_session.execute(select(Game).where(Game.id == saved["game_id"]))).scalar_one()
    assert record.is_rated is True
    delta = record.white_rating_delta if color == "white" else record.black_rating_delta
    assert delta == after - before


async def test_abandoned_game_is_a_rated_loss(client, token_user_1, test_user_1, db_session):
    before, games = await _rating(db_session, test_user_1.id)
    t = create(client, token_user_1, WEAK)
    game, _, _ = my_game(t)
    start(client, token_user_1, t, game)
    assert start(client, token_user_1, t, game).json()["forfeited"] is True
    after, games_after = await _rating(db_session, test_user_1.id)
    assert after < before and games_after == games + 1


async def test_withdrawal_rates_only_the_started_game(client, token_user_1, test_user_1, db_session):
    before, games = await _rating(db_session, test_user_1.id)
    t = create(client, token_user_1, WEAK)
    client.post(f"/api/v1/tournaments/{t['id']}/withdraw", headers=auth(token_user_1))
    unchanged, games_unchanged = await _rating(db_session, test_user_1.id)
    assert (unchanged, games_unchanged) == (before, games)       # no game was started - the rating is unchanged

    t2 = create(client, token_user_1, WEAK)
    game, _, _ = my_game(t2)
    start(client, token_user_1, t2, game)
    client.post(f"/api/v1/tournaments/{t2['id']}/withdraw", headers=auth(token_user_1))
    after, games_after = await _rating(db_session, test_user_1.id)
    assert after < before and games_after == games + 1          # only the started game counts
