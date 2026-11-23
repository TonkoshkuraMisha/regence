"""
Repertoire repetition (task 20.2). A card is a repertoire position where the player is to move: "find your move" (all of
the player's moves from the position are correct). The schedule is SM-2: a correct answer grows the interval (1 day, 6
days, then x ease), a mistake resets it to tomorrow and lowers the ease; in the same session the client shows the card once
more (a retry does not change the schedule). New cards - no more than the daily norm, from short lines to long ones.

"Game against the repertoire": the opponent replies with moves from its repertoire replies, more often popular ones (by
the position index 16.1); no replies - the line is finished.

Data: cards are the repertoire_cards table (position, ease, interval in days, number of repetitions and mistakes,
due_at); the repertoire tree is repertoire_moves via src/services/repertoire.py; move popularity is
position_stats (src/services/position_index.py). The module's functions do not commit - the route does
(src/api/repertoire.py).
"""

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import chess
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainValueError
from src.models.repertoire import Repertoire, RepertoireCard
from src.services import position_index
from src.services import repertoire as service

NEW_PER_DAY = 10  # daily norm of new cards in review mode (day - by UTC)
SESSION = 20  # cards in one review session; in learn mode - half
LEARNED_DAYS = 6  # interval after the second correct answer in a row; from it a card counts as learned
MIN_EASE = 1.3  # lower bound of ease (as in SM-2); a new card starts at 2.5


@dataclass
class Spot:
    """A position with the player's move: how to get to it and which moves are correct."""

    position: str
    line: list[str]
    answers: list[dict] = field(default_factory=list)


def spots(repertoire: Repertoire, edges: list[service.Edge]) -> dict[str, Spot]:
    """Card positions: the shortest line to the position (by breadth-first traversal) and the player's moves from it."""
    line_to: dict[str, list[str]] = {service.ROOT: []}
    found: dict[str, Spot] = {}
    for edge in edges:
        line = line_to.get(edge.position)
        if line is None:
            continue
        line_to.setdefault(edge.child, [*line, edge.uci])
        if edge.mine:
            spot = found.setdefault(edge.position, Spot(edge.position, line))
            spot.answers.append({"uci": edge.uci, "san": edge.san, "comment": edge.comment})
    return found


def status(card: RepertoireCard) -> str:
    """Card state: new - not answered yet, learned - interval not less than LEARNED_DAYS, otherwise learning."""
    if card.first_reviewed_at is None:
        return "new"
    return "learned" if card.interval_days >= LEARNED_DAYS else "learning"


def schedule(card: RepertoireCard, correct: bool, now: datetime) -> None:
    """
    SM-2 with a grade of 4 for a correct answer and 1 for a mistake. With these grades a correct answer does not change
    ease, a mistake lowers it by 0.54 (not below MIN_EASE). Intervals of consecutive correct answers: 1 day, LEARNED_DAYS,
    then the previous interval x ease; a mistake zeroes the repetition counter and returns the card to tomorrow.
    """
    quality = 4 if correct else 1
    card.ease = max(MIN_EASE, card.ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    if correct:
        card.repetitions += 1
        card.interval_days = 1 if card.repetitions == 1 else LEARNED_DAYS if card.repetitions == 2 \
            else round(card.interval_days * card.ease)
    else:
        card.repetitions = 0
        card.lapses += 1
        card.interval_days = 1
    card.due_at = now + timedelta(days=card.interval_days)
    card.first_reviewed_at = card.first_reviewed_at or now
    card.last_reviewed_at = now


def _aware(moment: datetime | None) -> datetime | None:
    """SQLite in tests returns a time without a zone - we treat it as UTC."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


async def sync_cards(db: AsyncSession, repertoire: Repertoire) -> tuple[dict[str, Spot], dict[str, RepertoireCard]]:
    """
    Cards = positions with the player's move: new positions get a card, disappeared ones lose it (together with the history
    of repetitions). Called before every session and answer, so the cards always match the tree.
    """
    found = spots(repertoire, service.build_tree(repertoire.color, await service.load_moves(db, repertoire.id)))
    cards = {c.position: c for c in (await db.execute(
        select(RepertoireCard).where(RepertoireCard.repertoire_id == repertoire.id)
    )).scalars().all()}
    gone = [c.id for key, c in cards.items() if key not in found]
    if gone:
        await db.execute(delete(RepertoireCard).where(RepertoireCard.id.in_(gone)))
    for key in found:
        if key not in cards:
            card = RepertoireCard(repertoire_id=repertoire.id, position=key, ease=2.5, interval_days=0, repetitions=0,
                                  lapses=0)
            db.add(card)
            cards[key] = card
    await db.flush()
    return found, {key: card for key, card in cards.items() if key in found}


def stats(cards: dict[str, RepertoireCard], now: datetime) -> dict:
    """
    Summary of the repertoire's cards: total, new, in progress, learned, due now and how many new ones can still be taken
    today (NEW_PER_DAY).
    """
    counts = {"new": 0, "learning": 0, "learned": 0}
    due = new_today = 0
    for card in cards.values():
        counts[status(card)] += 1
        due_at, first = _aware(card.due_at), _aware(card.first_reviewed_at)
        if due_at is not None and due_at <= now:
            due += 1
        if first is not None and first.date() == now.date():
            new_today += 1
    return {"total": len(cards), **counts, "due": due, "new_left": max(0, NEW_PER_DAY - new_today)}


def _fen(line: list[str]) -> str:
    """FEN of the card position: the starting position plus the line's moves."""
    board = chess.Board()
    for uci in line:
        board.push_uci(uci)
    return board.fen()


async def session(db: AsyncSession, repertoire: Repertoire, mode: str, now: datetime) -> dict:
    """
    review - overdue first (oldest first, up to SESSION), then new ones within the daily norm and
    the remaining room; learn - only new ones, without the norm, up to SESSION // 2. New ones go from short lines to long ones.
    The card's correct moves go to the client with it: the answer is also checked on the server (``answer``).
    """
    found, cards = await sync_cards(db, repertoire)
    summary = stats(cards, now)
    # A due date exists for answered cards and for those put "to practise" after a game (20.3), even if still new.
    overdue = sorted((key for key, card in cards.items() if (due := _aware(card.due_at)) is not None and due <= now),
                     key=lambda key: _aware(cards[key].due_at) or now)
    fresh = sorted((key for key, card in cards.items() if status(card) == "new" and key not in overdue),
                   key=lambda key: (len(found[key].line), found[key].line))
    if mode == "learn":
        chosen = fresh[:SESSION // 2]
    else:
        chosen = overdue[:SESSION]
        chosen += fresh[:max(0, min(summary["new_left"], SESSION - len(chosen)))]
    return {
        "stats": summary,
        "cards": [{"position": key, "line": found[key].line, "fen": _fen(found[key].line),
                   "answers": found[key].answers, "status": status(cards[key])} for key in chosen],
    }


async def answer(db: AsyncSession, repertoire: Repertoire, position: str, uci: str, retry: bool,
                 now: datetime) -> dict:
    """
    Answer to a card: any own move from this position is correct. The repetition schedule is changed only by the first
    answer; a retry in the same session (retry) does not touch it.
    """
    found, cards = await sync_cards(db, repertoire)
    if position not in found:
        raise DomainValueError("repertoire_move_not_found")
    answers = found[position].answers
    correct = any(a["uci"] == uci for a in answers)
    card = cards[position]
    if not retry:
        schedule(card, correct, now)
    return {"correct": correct, "answers": answers, "status": status(card),
            "due_at": due.isoformat() if (due := _aware(card.due_at)) else None,
            "stats": stats(cards, now)}


async def opponent_reply(db: AsyncSession, repertoire: Repertoire, moves: list[str],
                         rng: random.Random | None = None) -> dict:
    """
    A repertoire reply of the opponent; more often the one more popular with humans. No replies - the line is finished. The
    reply's weight is the number of games with this move in the position index plus 1 (a move without statistics may also
    come up). A request when it is the player's own move - refusal illegal_move.
    """
    pairs = service.parse_line(moves)
    board = chess.Board()
    for _, uci in pairs:
        board.push_uci(uci)
    side = chess.WHITE if repertoire.color == "white" else chess.BLACK
    if board.turn == side:
        raise DomainValueError("illegal_move", move=moves[-1] if moves else "")
    key = service.position_key(board)
    options = [e for e in service.build_tree(repertoire.color, await service.load_moves(db, repertoire.id))
               if e.position == key and not e.mine]
    if not options:
        return {"reply": None, "san": None}
    popularity = {s.move_uci: s.games for s in await position_index.moves_from(db, board)}
    weights = [popularity.get(e.uci, 0) + 1 for e in options]
    choice = (rng or random.Random()).choices(options, weights=weights)[0]
    return {"reply": choice.uci, "san": choice.san}


def utcnow() -> datetime:
    return datetime.now(UTC)


async def focus(db: AsyncSession, repertoire: Repertoire, position: str, now: datetime) -> None:
    """Put a position's card into today's repetition (after a mistake in a game, task 20.3)."""
    _, cards = await sync_cards(db, repertoire)
    card = cards.get(position)
    if card is None:
        raise DomainValueError("repertoire_move_not_found")
    card.due_at = now
