# --- FILE: src/services/bots/__init__.py ---
"""
Registry of ready-made bots BOT_INSTANCES (id → instance) and the entry point of the bots package.

The registry holds seven historical bots of the first wave (each in its own module nearby: philidor.py … zukertort.py, with an
opening
book and style rules) and the masters from masters.py (MASTER_BOTS). The general move selection order is base.HistoricalBot.
Workshop archetypes (archetypes.py) and the "masters of the past" (guests.py) are not in the registry: they are built on the
fly from
personality settings (personality.py).

The registry is read by bot memory (memory.py: the bot's book by id) and tournament simulation (tournament_simulation.py: a
fresh bot
as type(bot)()). The routes in src/api/bots.py take bots from this registry.
"""

from src.services.bots.anderssen import AnderssenBot, anderssen_bot
from src.services.bots.base import HistoricalBot, normalize_fen_key, resolve_stockfish_path
from src.services.bots.labourdonnais import LabourdonnaisBot, labourdonnais_bot
from src.services.bots.masters import MASTER_BOTS
from src.services.bots.morphy import MorphyBot, morphy_bot
from src.services.bots.paulsen import PaulsenBot, paulsen_bot
from src.services.bots.philidor import PhilidorBot, philidor_bot
from src.services.bots.staunton import StauntonBot, staunton_bot
from src.services.bots.zukertort import ZukertortBot, zukertort_bot

BOT_INSTANCES: dict[str, HistoricalBot] = {
    "philidor": philidor_bot,
    "labourdonnais": labourdonnais_bot,
    "staunton": staunton_bot,
    "anderssen": anderssen_bot,
    "morphy": morphy_bot,
    "paulsen": paulsen_bot,
    "zukertort": zukertort_bot,
    **MASTER_BOTS,  # masters from masters.py (task 21.5 and later waves)
}

__all__ = [
    "HistoricalBot",
    "PhilidorBot",
    "LabourdonnaisBot",
    "StauntonBot",
    "AnderssenBot",
    "MorphyBot",
    "PaulsenBot",
    "ZukertortBot",
    "philidor_bot",
    "labourdonnais_bot",
    "staunton_bot",
    "anderssen_bot",
    "morphy_bot",
    "paulsen_bot",
    "zukertort_bot",
    "BOT_INSTANCES",
    "normalize_fen_key",
    "resolve_stockfish_path",
]
