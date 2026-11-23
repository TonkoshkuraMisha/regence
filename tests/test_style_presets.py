# --- FILE: tests/test_style_presets.py ---
"""
Historical bots are expressed as declarative presets of the common style model (src/services/bots/style.py).
The test compares each bot's bonus and comment for every legal move with a "golden" snapshot
taken from the former separate evaluate_*_style_bonus functions (scripts/dev/make_style_golden.py):
92 positions - opening, castling by both sides, middlegame, endgame.
"""

import json
from pathlib import Path

import chess
import pytest

from src.services.bots import BOT_INSTANCES
from src.services.bots.masters import MASTER_BOTS

# The snapshot was taken from the first wave (7 bots). The second-wave masters (task 21.5) are workshop-character
# opponents: their style is set by sliders and is checked by the personality tests.
FIRST_WAVE = sorted(set(BOT_INSTANCES) - set(MASTER_BOTS))

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "style_bonus_golden.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("bot_id", FIRST_WAVE)
def test_preset_matches_previous_style_function(bot_id: str):
    bot = BOT_INSTANCES[bot_id]
    notes = GOLDEN["notes"]
    mismatches = []
    for position in GOLDEN["positions"]:
        board = chess.Board(position["fen"])
        for uci, (bonus, note_id) in zip(position["moves"], position["bots"][bot_id], strict=True):
            got_bonus, got_note = bot.evaluate_style_bonus(board, chess.Move.from_uci(uci))
            if round(got_bonus, 6) != bonus or got_note != notes[note_id]:
                mismatches.append((position["fen"], uci, (bonus, notes[note_id]), (got_bonus, got_note)))
    assert not mismatches, f"{len(mismatches)} mismatches, first ones: {mismatches[:3]}"


def test_golden_covers_every_bot_and_many_moves():
    assert set(GOLDEN["positions"][0]["bots"]) == set(FIRST_WAVE)
    assert sum(len(p["moves"]) for p in GOLDEN["positions"]) > 2000
