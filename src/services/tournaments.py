# --- FILE: src/services/tournaments.py ---
"""
The course of a tournament (tasks 15.1, 15.4, A.1-A.3): creation with seeding and schedule, recording a game result and
advancing - the next games of a knockout match, the next round of a round robin or Swiss tournament, final places,
resignation from a tournament by the player. The rules themselves (schedule, tables, bracket) are in tournament_rules.py.

Data: the tables tournaments, tournament_players, tournament_games (src/models/tournament.py), the player's rating is
the User fields (src/services/rating.py), bot strength is calibration (bots/calibration.py), masters of the past -
bots/guests.py. The fair-play session of the player's game is opened and closed by ladder.py (the "tournament" scope, Redis).

Results are brought here by: the player's game (saving a game with a bot in src/api/bots.py, task 15.3, as well as
resignation and a repeated start here) and the simulation of bot-vs-bot games (tournament_simulation.py, Celery, task
15.2). The player cannot send a result themselves - there is no separate endpoint for that. The module is also called by
src/api/tournaments.py, tournament_career.py and time_machine.py.
"""

import json
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainError
from src.models.personality import BotPersonality
from src.models.tournament import Tournament, TournamentGame, TournamentPlayer
from src.models.user import User
from src.services import product_metrics
from src.services import tournament_rules as rules
from src.services.bots.archetypes import ARCHETYPE_PREFIX, ARCHETYPES_BY_KEY
from src.services.bots.calibration import strength_of
from src.services.bots.guests import GUESTS_BY_ID
from src.services.rating import classify_time_control, elo_calculator

# Tournament format: round robin, knockout, Swiss system.
Format = Literal["round_robin", "knockout", "swiss"]

# A bot game that a worker took and did not finish (crashed) can be taken again after CLAIM_TIMEOUT.
CLAIM_TIMEOUT = timedelta(minutes=15)
# A bot game that was queued but not started is queued again no sooner than after REQUEUE_AFTER (task A.1):
# the tournament page polls the server every 3 s, and without this the Celery queue would grow with every poll.
REQUEUE_AFTER = timedelta(minutes=2)
# Allowed number of participants of an ordinary player tournament by format (for historical ones - rules.OPEN_*).
SIZES: dict[str, tuple[int, ...]] = {
    "round_robin": rules.ROUND_ROBIN_SIZES, "knockout": rules.KNOCKOUT_SIZES, "swiss": rules.SWISS_SIZES,
}


@dataclass(frozen=True)
class ParticipantSpec:
    """
    An opponent in a tournament: a historical bot (id), an archetype (id), a player's personality (id in the database) or a
    master of the past from bots/guests.py (id) - it takes part as a personality with the key "guest:<id>" ("Time Machine",
    28.2).
    """

    kind: Literal["bot", "archetype", "personality", "guest"]
    id: str | int


@dataclass
class _Entrant:
    """A participant before seeding: who they are, strength at the start and listing order (order - for ties in seeding)."""
    kind: str
    rating: int
    user_id: int | None = None
    bot_key: str | None = None
    personality_name: str | None = None
    config_json: str | None = None
    order: int = 0


def _bot_ratings() -> dict[str, int]:
    """Stated ratings of the historical bots from the catalogue src/api/bots.py (id -> rating)."""
    from src.api.bots import AVAILABLE_BOTS

    return {str(b["id"]): int(str(b["rating"])) for b in AVAILABLE_BOTS}


async def _entrant(db: AsyncSession, owner: User, spec: ParticipantSpec, order: int) -> _Entrant:
    """
    Turns an entry into a participant with the strength at the start: for a bot and an archetype - by calibration, for a
    master of the past - the stated one, for a personality - target_elo from the config. Someone else's or an unknown
    personality - tournament_participant_unknown.
    """
    label = f"{spec.kind}:{spec.id}"
    if spec.kind == "bot":
        declared = _bot_ratings().get(str(spec.id))
        if declared is None:
            raise DomainError("tournament_participant_unknown", participant=label)
        return _Entrant("bot", strength_of(str(spec.id), declared).rating, bot_key=str(spec.id), order=order)
    if spec.kind == "archetype":
        archetype = ARCHETYPES_BY_KEY.get(f"{ARCHETYPE_PREFIX}{spec.id}")
        if archetype is None:
            raise DomainError("tournament_participant_unknown", participant=label)
        rating = strength_of(archetype.key, archetype.config.target_elo).rating
        return _Entrant("archetype", rating, bot_key=archetype.key, order=order)
    if spec.kind == "guest":
        guest = GUESTS_BY_ID.get(str(spec.id))
        if guest is None:
            raise DomainError("tournament_participant_unknown", participant=label)
        # A master of the past plays as a personality: the simulation and the player's game follow their character, and the key
        # lets the client show the name in the player's language.
        return _Entrant("personality", guest.rating, bot_key=guest.key, personality_name=guest.pgn_name,
                        config_json=guest.config.model_dump_json(), order=order)
    personality = await db.get(BotPersonality, int(spec.id)) if str(spec.id).isdigit() else None
    if personality is None or personality.owner_id != owner.id:
        raise DomainError("tournament_participant_unknown", participant=label)
    config = json.loads(personality.config_json)
    return _Entrant(
        "personality", int(config.get("target_elo", 1500)), personality_name=personality.name,
        config_json=personality.config_json, order=order,
    )


async def active_in_branch(db: AsyncSession, owner_id: int, stages: Collection[str]) -> Tournament | None:
    """
    The player's running tournament in the same progress branch (career stages); a resigned one (bots still
    finishing) does not interfere. Owner's decision (17.11): only its own branch blocks - own tournaments and the "Time
    Machine" run in parallel with anything, any number at once.
    """
    return (await db.execute(
        select(Tournament).where(
            Tournament.owner_id == owner_id, Tournament.status == "active", Tournament.withdrawn_at.is_(None),
            Tournament.career_stage.in_(list(stages)),
        ).limit(1)
    )).scalar_one_or_none()


async def create_tournament(
        db: AsyncSession,
        owner: User,
        fmt: Format,
        size: int,
        participants: list[ParticipantSpec],
        base_time_ms: int,
        increment_ms: int,
        career_stage: str | None = None,
        cycles: int = 1,
        open_size: bool = False,
        event_key: str | None = None,
        progress_branch: Collection[str] = (),
) -> Tournament:
    """
    Creates a tournament: checks the size and the field, seeds participants by strength at the start (the player first on a
    tie), writes the participants and the games of the first round (for a round robin - the schedule of all rounds at
    once). Commits itself. open_size - a tournament with a historical field ("Time Machine", 28.1): a round robin or a
    bracket for any number of participants within rules.OPEN_*; cycles - the number of circuits of a round robin. The
    player's own tournaments are created without them: sizes come from SIZES. progress_branch - career stages of the same
    branch: while one of them runs, a new one cannot start. The field is size - 1 opponents plus the player.
    """
    allowed: tuple[int, ...] | range = SIZES[fmt]
    if open_size and fmt == "round_robin":
        allowed = rules.OPEN_ROUND_ROBIN_SIZES
    elif open_size and fmt == "knockout":
        allowed = rules.OPEN_KNOCKOUT_SIZES
    if size not in allowed or not 1 <= cycles <= rules.MAX_CYCLES or (cycles > 1 and fmt != "round_robin"):
        raise DomainError("tournament_size_invalid", sizes=", ".join(map(str, SIZES[fmt])))
    if len(participants) != size - 1:
        raise DomainError("tournament_participants_count", expected=size - 1)
    keys = [f"{p.kind}:{p.id}" for p in participants]
    for key in keys:
        if keys.count(key) > 1:
            raise DomainError("tournament_participant_duplicate", participant=key)
    if progress_branch and await active_in_branch(db, owner.id, progress_branch) is not None:
        raise DomainError("tournament_active_exists")

    category = classify_time_control(base_time_ms, increment_ms)
    entrants = [_Entrant("user", owner.rating_for(category), user_id=owner.id, order=0)]
    entrants += [await _entrant(db, owner, spec, i + 1) for i, spec in enumerate(participants)]
    # Seeding: by rating at the start; on a tie - in listing order (the player first).
    entrants.sort(key=lambda e: (-e.rating, e.order))

    tournament = Tournament(
        owner_id=owner.id, format=fmt, size=size, status="active",
        base_time_ms=base_time_ms, increment_ms=increment_ms, current_round=1, career_stage=career_stage,
        event_key=event_key,
    )
    db.add(tournament)
    await db.flush()
    for seat, e in enumerate(entrants, 1):
        db.add(TournamentPlayer(
            tournament_id=tournament.id, seat=seat, kind=e.kind, user_id=e.user_id, bot_key=e.bot_key,
            personality_name=e.personality_name, config_json=e.config_json, rating=e.rating,
        ))

    if fmt == "round_robin":
        for rnd, pairs in enumerate(rules.round_robin_schedule(size, cycles), 1):
            for board, (white, black) in enumerate(pairs, 1):
                _add_game(db, tournament, rnd, board, rules.MatchGame("main", white, black, False))
    elif fmt == "swiss":
        for board, (white, black) in enumerate(rules.swiss_pairings(list(range(1, size + 1)), []), 1):
            _add_game(db, tournament, 1, board, rules.MatchGame("main", white, black, False))
    else:
        # The board number is the match's place in the bracket; those who passed the first round without playing have no game.
        for board, (high, low) in enumerate(rules.bracket_slots(size), 1):
            if low is not None:
                _add_game(db, tournament, 1, board, rules.match_game(high, low, "main"))
    await product_metrics.record_event(db, owner.id, product_metrics.TOURNAMENT_CREATED)
    await db.commit()
    await db.refresh(tournament)
    return tournament


def _add_game(db: AsyncSession, tournament: Tournament, rnd: int, board: int, game: rules.MatchGame) -> None:
    """Adds a game to the session; for a replay and a deciding game the time control is shortened (rules.shortened_control)."""
    base, inc = tournament.base_time_ms, tournament.increment_ms
    if game.shortened:
        base, inc = rules.shortened_control(base, inc)
    db.add(TournamentGame(
        tournament_id=tournament.id, round=rnd, board=board, stage=game.stage,
        white_seat=game.white, black_seat=game.black, base_time_ms=base, increment_ms=inc,
    ))


async def players_of(db: AsyncSession, tournament_id: int) -> list[TournamentPlayer]:
    """Participants of a tournament in seeding order (seat)."""
    return list((await db.execute(
        select(TournamentPlayer).where(TournamentPlayer.tournament_id == tournament_id).order_by(TournamentPlayer.seat)
    )).scalars().all())


async def games_of(db: AsyncSession, tournament_id: int) -> list[TournamentGame]:
    """All games of a tournament by rounds and boards."""
    return list((await db.execute(
        select(TournamentGame).where(TournamentGame.tournament_id == tournament_id)
        .order_by(TournamentGame.round, TournamentGame.board, TournamentGame.id)
    )).scalars().all())


def _record(game: TournamentGame) -> rules.GameRecord:
    """A played game as a record for the pure rules (result is not None)."""
    return rules.GameRecord(game.white_seat, game.black_seat, game.result)  # type: ignore[arg-type]


async def record_result(
        db: AsyncSession, tournament: Tournament, game: TournamentGame, result: str, game_id: int | None = None,
) -> None:
    """
    Records a tournament game result and advances the tournament. Commits itself. The tournament and the game are re-read under
    row locks (SELECT ... FOR UPDATE): the result of a bot-game simulation (a Celery worker) and the player's game may
    arrive at the same time - the round then advances once, and a repeated record of the same game gets
    tournament_game_closed.
    """
    if result not in ("1-0", "0-1", "1/2-1/2"):
        raise ValueError(f"bad result {result}")
    await db.flush()  # the caller's unsaved changes must not be lost on re-read
    await db.refresh(tournament, with_for_update=True)
    await db.refresh(game, with_for_update=True)
    if game.tournament_id != tournament.id or tournament.status != "active" or game.result is not None:
        raise DomainError("tournament_game_closed")
    game.result = result
    game.game_id = game_id
    await db.flush()
    if tournament.format == "round_robin":
        await _advance_round_robin(db, tournament)
    elif tournament.format == "swiss":
        await _advance_swiss(db, tournament)
    else:
        await _advance_knockout(db, tournament)
    await db.commit()


async def _finish(tournament: Tournament) -> None:
    """Closes the tournament: status "finished" and the end time."""
    tournament.status = "finished"
    tournament.finished_at = datetime.now(UTC)


async def _notify_round(db: AsyncSession, tournament: Tournament) -> None:
    """Notification centre (17.1): a round opened in which the player has a game. No socket delivery - the bell asks itself."""
    from src.services import notifications

    if tournament.withdrawn_at is not None:
        return
    mine = next((p.seat for p in await players_of(db, tournament.id) if p.kind == "user"), None)
    pending = [g for g in await games_of(db, tournament.id)
               if g.round == tournament.current_round and g.result is None and mine in (g.white_seat, g.black_seat)]
    if pending:
        await notifications.record(db, tournament.owner_id, "tournament_round",
                                   {"tournament_id": tournament.id, "round": tournament.current_round}, commit=False)


async def _advance_round_robin(db: AsyncSession, tournament: Tournament) -> None:
    """
    Round robin: while the current round has unplayed games - wait; the round is closed - the next one opens; everything
    played - final places by the table (rules.round_robin_standings).
    """
    games = await games_of(db, tournament.id)
    if any(g.result is None for g in games if g.round == tournament.current_round):
        return
    if any(g.result is None for g in games):
        # The round is closed - the next one opens (its bot-vs-bot games can be computed).
        tournament.current_round += 1
        await _notify_round(db, tournament)
        return
    players = await players_of(db, tournament.id)
    table = rules.round_robin_standings([p.seat for p in players], [_record(g) for g in games])
    place = {s.seat: s.place for s in table}
    for p in players:
        p.place = place[p.seat]
    await _finish(tournament)


async def _advance_swiss(db: AsyncSession, tournament: Tournament) -> None:
    """The round is closed - pairs of the next one by points (rules.swiss_pairings); the last round - final places."""
    games = await games_of(db, tournament.id)
    if any(g.result is None for g in games):
        return
    players = await players_of(db, tournament.id)
    seats = [p.seat for p in players]
    records = [_record(g) for g in games]
    if tournament.current_round >= rules.SWISS_ROUNDS[tournament.size]:
        place = {s.seat: s.place for s in rules.swiss_standings(seats, records)}
        for p in players:
            p.place = place[p.seat]
        await _finish(tournament)
        return
    tournament.current_round += 1
    # A player who resigned from the tournament (task A.3) does not play in new rounds: their game is recorded as a loss at
    # once.
    withdrawn = {p.seat for p in players if p.kind == "user"} if tournament.withdrawn_at is not None else set()
    for board, (white, black) in enumerate(rules.swiss_pairings(seats, records), 1):
        _add_game(db, tournament, tournament.current_round, board, rules.MatchGame("main", white, black, False))
    await db.flush()
    await _notify_round(db, tournament)
    if withdrawn:
        for game in await games_of(db, tournament.id):
            if game.round == tournament.current_round and {game.white_seat, game.black_seat} & withdrawn:
                game.result = loss_for("white" if game.white_seat in withdrawn else "black")
        await db.flush()
        await _advance_swiss(db, tournament)


async def _advance_knockout(db: AsyncSession, tournament: Tournament) -> None:
    """
    Knockout: a drawn match gets the next game (replay, then the deciding one); when all matches of a round are decided,
    the losers get the elimination round and the winners get the pairs of the next round; the final closes the tournament
    and assigns places.
    """
    games = [g for g in await games_of(db, tournament.id) if g.round == tournament.current_round]
    boards = sorted({g.board for g in games})
    won: dict[int, int] = {}
    pending = False
    for board in boards:
        match = [g for g in games if g.board == board]
        if any(g.result is None for g in match):
            pending = True
            continue
        main = next(g for g in match if g.stage == "main")
        high, low = sorted((main.white_seat, main.black_seat))
        state = rules.match_state(high, low, [(g.stage, _record(g)) for g in match])  # type: ignore[misc]
        if state.winner is None:
            assert state.next_game is not None
            _add_game(db, tournament, tournament.current_round, board, state.next_game)
            pending = True
        else:
            won[board] = state.winner
    if pending:
        return
    if tournament.current_round == 1:
        # Winners in bracket order; those who passed the first round without playing stand in their places.
        winners = [won[slot] if low is not None else high
                   for slot, (high, low) in enumerate(rules.bracket_slots(tournament.size), 1)]
    else:
        winners = [won[board] for board in boards]

    players = {p.seat: p for p in await players_of(db, tournament.id)}
    for board in boards:
        main = next(g for g in games if g.board == board and g.stage == "main")
        for seat in (main.white_seat, main.black_seat):
            if seat not in winners:
                players[seat].eliminated_round = tournament.current_round

    if len(winners) == 1:
        eliminated = {s: p.eliminated_round for s, p in players.items() if p.eliminated_round is not None}
        for seat, place in rules.knockout_places(tournament.size, eliminated, winners[0]).items():
            players[seat].place = place
        await _finish(tournament)
        return

    tournament.current_round += 1
    for board, (high, low) in enumerate(rules.knockout_next_round(winners), 1):
        _add_game(db, tournament, tournament.current_round, board, rules.match_game(high, low, "main"))
    await db.flush()
    await _notify_round(db, tournament)


@dataclass(frozen=True)
class PlayerGame:
    """The tournament game the player plays: tournament, game, their colour and opponent."""

    tournament: Tournament
    game: TournamentGame
    color: Literal["white", "black"]
    opponent: TournamentPlayer


async def player_game(db: AsyncSession, user: User, tournament_game_id: int) -> PlayerGame:
    """A game of the current round of the player's active tournament, still without a result; otherwise DomainError."""
    game = await db.get(TournamentGame, tournament_game_id)
    tournament = await db.get(Tournament, game.tournament_id) if game else None
    if game is None or tournament is None or tournament.owner_id != user.id:
        raise DomainError("tournament_not_found")
    if tournament.status != "active" or game.result is not None or game.round != tournament.current_round:
        raise DomainError("tournament_game_closed")
    seats = {p.seat: p for p in await players_of(db, tournament.id)}
    mine = next((p.seat for p in seats.values() if p.user_id == user.id), None)
    if mine not in (game.white_seat, game.black_seat):
        raise DomainError("tournament_game_mismatch")
    color: Literal["white", "black"] = "white" if game.white_seat == mine else "black"
    opponent = seats[game.black_seat if color == "white" else game.white_seat]
    return PlayerGame(tournament, game, color, opponent)


@dataclass(frozen=True)
class RatingChange:
    """Change of the player's rating for a tournament game: time-control category, rating before and after, the difference."""

    category: str
    before: int
    after: int
    delta: int


def apply_rating(user: User, played: PlayerGame, result: str) -> RatingChange:
    """
    All tournaments are rated (owner's decision, 15.11): the player's game changes their rating in the tournament's
    time-control category. The opponent has the strength at the start of the tournament (TournamentPlayer.rating), their
    "rating" does not change. Without commit.
    """
    category = classify_time_control(played.tournament.base_time_ms, played.tournament.increment_ms)
    before = user.rating_for(category)
    games = user.games_played_for(category)
    opponent = played.opponent.rating
    if played.color == "white":
        after, delta, _, _ = elo_calculator.calculate_new_ratings(before, opponent, result, white_games=games)
    else:
        _, _, after, delta = elo_calculator.calculate_new_ratings(opponent, before, result, black_games=games)
    setattr(user, f"{category}_rating", after)
    setattr(user, f"{category}_games_played", games + 1)
    return RatingChange(category, before, after, delta)


def opponent_matches(opponent: TournamentPlayer, bot_id: str, personality_name: str | None) -> bool:
    """The game was played with the tournament opponent: a bot - by id, an archetype - by key, a personality - by name."""
    if opponent.kind == "bot":
        return bot_id == opponent.bot_key
    expected = opponent.bot_key if opponent.kind == "archetype" else opponent.personality_name
    return bot_id == "custom" and personality_name == expected


async def simulatable_games(db: AsyncSession, tournament: Tournament) -> list[TournamentGame]:
    """Games of the current round without a result where both are bots: they are played by the server (task 15.2)."""
    if tournament.status != "active":
        return []
    humans = {p.seat for p in await players_of(db, tournament.id) if p.kind == "user"}
    return [
        g for g in await games_of(db, tournament.id)
        if g.round == tournament.current_round and g.result is None
        and g.white_seat not in humans and g.black_seat not in humans
    ]



def _aware(moment: datetime | None) -> datetime | None:
    """SQLite in tests returns a time without a zone - we treat it as UTC."""
    return moment.replace(tzinfo=UTC) if moment is not None and moment.tzinfo is None else moment


async def mark_for_queue(db: AsyncSession, tournament: Tournament) -> list[int]:
    """
    Bot games that are due to be queued: not started (or abandoned by a crashed worker) and not queued
    recently. Marks them with queued_at and returns the ids - the caller publishes them.
    """
    now = datetime.now(UTC)
    ids = []
    for game in await simulatable_games(db, tournament):
        started, queued = _aware(game.started_at), _aware(game.queued_at)
        if started is not None and started > now - CLAIM_TIMEOUT:
            continue
        if queued is not None and queued > now - REQUEUE_AFTER and started is None:
            continue
        game.queued_at = now
        ids.append(game.id)
    if ids:
        await db.commit()
    return ids


def opponent_session_key(opponent: TournamentPlayer) -> str:
    """Opponent key for a fair-play game session (src/services/ladder.py): this is how the client requests their moves."""
    if opponent.kind in ("bot", "archetype") and opponent.bot_key:
        return opponent.bot_key
    return "custom:other"


def loss_for(color: str) -> str:
    """The game result as a loss of side color ("white" or "black")."""
    return "0-1" if color == "white" else "1-0"


@dataclass(frozen=True)
class StartResult:
    """Outcome of a player starting a tournament game: the game and a flag that a repeated start recorded a loss."""

    played: PlayerGame
    # The game was already started and abandoned: a repeated start is a loss (task A.2).
    forfeited: bool


async def start_player_game(db: AsyncSession, user: User, tournament_game_id: int) -> StartResult:
    """
    The player starts their tournament game. The first start - taking the game and a fair-play session; a repeated start of
    an already started game is a loss: otherwise a game being lost could be abandoned and started anew.
    """
    from src.services import ladder

    played = await player_game(db, user, tournament_game_id)
    if played.game.started_at is not None:
        await ladder.clear_session(user.id, "tournament")
        # An abandoned game is a rated loss (the user comes from this same session, otherwise the change will not be written).
        apply_rating(await db.get(User, user.id) or user, played, loss_for(played.color))
        await record_result(db, played.tournament, played.game, loss_for(played.color))
        return StartResult(played, forfeited=True)
    played.game.started_at = datetime.now(UTC)
    await db.commit()
    await ladder.open_session(
        user.id, opponent_session_key(played.opponent), played.color, scope="tournament",
        tournament_game_id=played.game.id,
    )
    return StartResult(played, forfeited=False)


async def withdraw(db: AsyncSession, user: User, tournament: Tournament) -> None:
    """The player resigns from the tournament: their unplayed games are losses, bot games finish by themselves (task A.3)."""
    from src.services import ladder

    if tournament.status != "active" or tournament.withdrawn_at is not None:
        raise DomainError("tournament_game_closed")
    mine = next((p.seat for p in await players_of(db, tournament.id) if p.user_id == user.id), None)
    tournament.withdrawn_at = datetime.now(UTC)
    await db.commit()
    await ladder.clear_session(user.id, "tournament")
    while True:
        await db.refresh(tournament)
        pending = [
            g for g in await games_of(db, tournament.id)
            if g.result is None and mine in (g.white_seat, g.black_seat)
        ]
        if not pending or tournament.status != "active":
            return
        game = pending[0]
        color = "white" if game.white_seat == mine else "black"
        if game.started_at is not None:
            # Resigning in the middle of a started game is a rated loss; unplayed games do not change the rating.
            seats = {p.seat: p for p in await players_of(db, tournament.id)}
            opponent = seats[game.black_seat if color == "white" else game.white_seat]
            fresh = await db.get(User, user.id) or user
            apply_rating(fresh, PlayerGame(tournament, game, color, opponent), loss_for(color))  # type: ignore[arg-type]
        await record_result(db, tournament, game, loss_for(color))
