"""Second-wave masters (task 21.5): registry, books from their own games, a class per master, portraits, off the ladder."""

import pathlib

import chess

from src.api.bots import AVAILABLE_BOTS, BOT_METADATA, reserved_bot_usernames
from src.services import ladder
from src.services.bots import BOT_INSTANCES
from src.services.bots.masters import MASTER_BOTS, MASTERS

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_masters_are_registered_with_books():
    assert [m.id for m in MASTERS] == ["steinitz", "lasker", "rubinstein", "capablanca", "alekhine", "chigorin",
                                       "tarrasch", "pillsbury", "marshall", "nimzowitsch", "reti", "tartakower",
                                       "botvinnik", "tal", "petrosian"]
    for master in MASTERS:
        bot = BOT_INSTANCES[master.id]
        assert bot is MASTER_BOTS[master.id] and bot.bot_id == master.id
        assert len(bot.opening_book) > 100, master.id
        move, comment = bot._book_move(chess.Board())
        assert move in chess.Board().legal_moves
        assert comment["key"] == f"book.{master.id}" and comment["params"]["games"] > 0
        assert bot.strength.uci_elo == master.rating
        # The tournament simulation creates a fresh bot without arguments.
        fresh = type(bot)()
        assert fresh.bot_id == master.id and fresh is not bot


def test_metadata_portraits_ladder_and_names():
    for master in MASTERS:
        meta = BOT_METADATA[master.id]
        assert meta["rating"] == master.rating
        portrait = ROOT / "frontend" / "public" / meta["avatar"].lstrip("/")
        assert portrait.is_file(), portrait
        assert master.id in reserved_bot_usernames()
    # Since 18.11 (plan task 7) all masters are ladder rungs.
    rung_keys = {r.key for r in ladder.rungs()}
    assert {m.id for m in MASTERS} <= rung_keys
    assert {str(b["id"]) for b in AVAILABLE_BOTS} <= rung_keys


def test_books_cover_only_the_masters_own_moves():
    """The book holds the master's side's moves: White and Black positions differ, but both exist (he played both colors)."""
    book = BOT_INSTANCES["capablanca"].opening_book
    turns = {key.split(" ")[1] for key in book}
    assert turns == {"w", "b"}
