# --- FILE: tests/test_matchmaker_paths.py ---
"""
Matchmaker (src/services/matchmaker.py): rare branches: player reservations, stale lobby entries, start failures,
invitations with non-standard values. Complements test_matchmaking_rules.py.
"""

import pytest

from src.models.user import User
from src.services import matchmaker as mm_module
from src.services.game_state import state_manager
from src.services.matchmaker import MatchmakingError, matchmaker
from src.services.rating import classify_time_control


async def _users(db_session, *ratings: int) -> list[User]:
    users = [User(
        username=f"mp_{i}_{r}", hashed_password="pw", bullet_rating=r, blitz_rating=r, rapid_rating=r, classical_rating=r
    ) for i, r in enumerate(ratings)]
    db_session.add_all(users)
    await db_session.commit()
    return users


async def test_session_without_db_opens_own_short_session():
    async with matchmaker._session(None) as session:
        assert session is not None


async def test_fresh_rating_of_unknown_user_is_none(db_session):
    category = classify_time_control(180000, 0)
    assert await matchmaker._fresh_rating(db_session, 987654, category) is None


async def test_ensure_not_in_game_distinguishes_self_and_opponent(db_session):
    a, b = await _users(db_session, 1500, 1500)
    await state_manager.initialize_game(5001, a.id, b.id, 180000, 0)
    with pytest.raises(MatchmakingError) as own:
        await matchmaker._ensure_not_in_game(a.id, is_self=True)
    with pytest.raises(MatchmakingError) as other:
        await matchmaker._ensure_not_in_game(a.id, is_self=False)
    assert (own.value.code, other.value.code) == ("self_in_game", "opponent_in_game")


async def test_reserve_conflict_rolls_back_taken_reserves():
    token = await matchmaker._reserve_players(1, 2)
    with pytest.raises(MatchmakingError) as err:
        await matchmaker._reserve_players(0, 1, 3)  # 0 taken, 1 busy -> roll back 0
    assert err.value.code == "players_busy"
    assert await matchmaker.redis.get("matchmaking:reserve:0") is None
    await matchmaker._release_players(token, 1, 2)
    assert await matchmaker.redis.get("matchmaking:reserve:1") is None


async def test_start_pvp_game_rejects_same_player(db_session):
    (a,) = await _users(db_session, 1500)
    with pytest.raises(MatchmakingError) as err:
        await matchmaker.start_pvp_game(a.id, a.id, 180000, 0, db=db_session)
    assert err.value.code == "self_play"


async def test_start_pvp_game_with_unknown_player_is_player_not_found(db_session):
    (a,) = await _users(db_session, 1500)
    with pytest.raises(MatchmakingError) as err:
        await matchmaker.start_pvp_game(a.id, 777_777, 180000, 0, db=db_session)
    assert err.value.code == "player_not_found"
    # reservation released: can retry immediately
    assert await matchmaker.redis.get(f"matchmaking:reserve:{a.id}") is None


async def test_accept_challenge_own_gone_and_unknown_acceptor(db_session):
    a, b = await _users(db_session, 1500, 1500)
    with pytest.raises(MatchmakingError) as own:
        await matchmaker.accept_challenge(a.id, a.id, None, db=db_session)
    with pytest.raises(MatchmakingError) as gone:
        await matchmaker.accept_challenge(a.id, b.id, None, db=db_session)
    assert (own.value.code, gone.value.code) == ("own_challenge", "challenge_gone")

    await matchmaker.join_queue(a.id, "a", 1500, 180000, 0, db=db_session)
    with pytest.raises(MatchmakingError) as unknown:
        await matchmaker.accept_challenge(a.id, 888_888, None, db=db_session)
    assert unknown.value.code == "player_not_found"


async def test_accept_challenge_lost_race_for_capture(db_session, monkeypatch):
    a, b = await _users(db_session, 1500, 1500)
    await matchmaker.join_queue(a.id, "a", 1500, 180000, 0, db=db_session)

    async def lost(*names):
        return 0  # another accepter took the challenge key

    monkeypatch.setattr(matchmaker.redis, "delete", lost)
    with pytest.raises(MatchmakingError) as err:
        await matchmaker.accept_challenge(a.id, b.id, None, db=db_session)
    assert err.value.code == "challenge_gone"


async def test_accept_challenge_start_failure_is_player_not_found(db_session, monkeypatch):
    a, b = await _users(db_session, 1500, 1500)
    await matchmaker.join_queue(a.id, "a", 1500, 180000, 0, db=db_session)

    async def no_record(*args, **kwargs):
        return None

    monkeypatch.setattr(matchmaker, "_create_match_record", no_record)
    with pytest.raises(MatchmakingError) as err:
        await matchmaker.accept_challenge(a.id, b.id, None, db=db_session)
    assert err.value.code == "player_not_found"


async def test_join_queue_skips_candidates_without_prefs(db_session):
    a, ghost, b = await _users(db_session, 1500, 1500, 1500)
    queue = mm_module._queue_name(180000, 0, True)
    # the queue has an entry without parameters (inconsistency): it is skipped
    await matchmaker.redis.zadd(queue, {str(ghost.id): 1})
    await matchmaker.redis.sadd("active_queues", queue)
    assert await matchmaker.join_queue(a.id, "a", 1500, 180000, 0, db=db_session) is None
    players = await matchmaker.get_queue_players()
    assert [p["user_id"] for p in players] == [a.id]

    game_id = await matchmaker.join_queue(b.id, "b", 1500, 180000, 0, db=db_session)
    assert game_id is not None


async def test_join_queue_continues_after_challenge_taken(db_session, monkeypatch):
    a, b = await _users(db_session, 1500, 1500)
    await matchmaker.join_queue(a.id, "a", 1500, 180000, 0, db=db_session)

    async def gone(*args, **kwargs):
        raise MatchmakingError("challenge_gone")

    monkeypatch.setattr(matchmaker, "accept_challenge", gone)
    assert await matchmaker.join_queue(b.id, "b", 1500, 180000, 0, db=db_session) is None  # own challenge published


async def test_join_queue_propagates_self_in_game_from_accept(db_session, monkeypatch):
    a, b = await _users(db_session, 1500, 1500)
    await matchmaker.join_queue(a.id, "a", 1500, 180000, 0, db=db_session)

    async def busy(*args, **kwargs):
        raise MatchmakingError("self_in_game")

    monkeypatch.setattr(matchmaker, "accept_challenge", busy)
    with pytest.raises(MatchmakingError) as err:
        await matchmaker.join_queue(b.id, "b", 1500, 180000, 0, db=db_session)
    assert err.value.code == "self_in_game"


async def test_invite_normalizes_unknown_values_and_chess960_drops_odds(db_session):
    (a,) = await _users(db_session, 1500)
    inv = await matchmaker.create_private_invite(
        a.id, "a", 1500, 180000, 0, color_pref="purple", odds_kind="nonsense", odds_giver="nobody", variant="weird",
    )
    assert (inv["color_pref"], inv["odds_kind"], inv["odds_giver"], inv["variant"]) == (
        "random", "", "creator", "standard")
    assert len(inv["code"]) == mm_module.INVITE_CODE_LENGTH

    from src.services.odds import KINDS
    kind = next(iter(KINDS))
    inv960 = await matchmaker.create_private_invite(a.id, "a", 1500, 180000, 0, odds_kind=kind, variant="chess960")
    assert inv960["odds_kind"] == "" and inv960["rated"] is False


async def test_invite_acceptance_colors_and_failure_paths(db_session, monkeypatch):
    a, b = await _users(db_session, 1500, 1500)
    assert await matchmaker.get_private_invite("NOPE") is None
    assert await matchmaker.accept_private_invite("NOPE", b.id) is None

    inv = await matchmaker.create_private_invite(a.id, "a", 1500, 180000, 0, color_pref="black")
    assert await matchmaker.accept_private_invite(inv["code"], a.id) is None  # the author themself
    got = await matchmaker.accept_private_invite(inv["code"], b.id)
    assert got["white_id"] == b.id and got["black_id"] == a.id

    inv = await matchmaker.create_private_invite(a.id, "a", 1500, 180000, 0, color_pref="white")
    got = await matchmaker.accept_private_invite(inv["code"], b.id)
    assert got["white_id"] == a.id

    # coin toss: random.random() is patched for both sides
    for roll, white in ((0.1, a.id), (0.9, b.id)):
        monkeypatch.setattr(mm_module.random, "random", lambda roll=roll: roll)
        inv = await matchmaker.create_private_invite(a.id, "a", 1500, 180000, 0)
        got = await matchmaker.accept_private_invite(inv["code"], b.id)
        assert got["white_id"] == white

    # another accepter consumed the invite between the read and the delete
    inv = await matchmaker.create_private_invite(a.id, "a", 1500, 180000, 0)

    async def lost(*names):
        return 0

    monkeypatch.setattr(matchmaker.redis, "delete", lost)
    assert await matchmaker.accept_private_invite(inv["code"], b.id) is None


async def test_start_game_from_invite_invalid_code(db_session):
    (a,) = await _users(db_session, 1500)
    with pytest.raises(MatchmakingError) as err:
        await matchmaker.start_game_from_invite("MISSING", a.id, db=db_session)
    assert err.value.code == "invite_invalid"
