# --- FILE: scripts/build_endgames.py ---
"""
Endgame trainer exercises (task 14.4) -> frontend/src/content/endgames.json. Every position is verified against
the endgame tablebases (settings.TABLEBASE_URL): the result for the side to move must match the goal
(a win for mate/promote/convert, a draw for draw), and for mates the optimum is recorded - moves to mate per the tablebases.

    python scripts/build_endgames.py
"""

import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import chess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "content" / "endgames.json"

# (id, FEN, goal). Goals: mate - deliver mate; promote - queen the pawn without throwing away the win; convert - leave
# the opponent a lone king without throwing away the win; draw - hold the draw.
EXERCISES = [
    ("kq_center", "8/8/8/4k3/8/8/8/KQ6 w - - 0 1", "mate"),
    ("kq_far", "8/8/3k4/8/8/8/1Q6/6K1 w - - 0 1", "mate"),
    ("kr_edge", "4k3/8/8/8/8/8/8/R3K3 w - - 0 1", "mate"),
    ("kr_center", "8/8/8/4k3/8/8/8/R3K3 w - - 0 1", "mate"),
    ("kr_box", "8/8/2k5/8/8/8/8/1R2K3 w - - 0 1", "mate"),
    ("bb_corner", "7k/8/5K2/8/8/8/8/2B2B2 w - - 0 1", "mate"),
    ("bb_center", "8/8/8/4k3/8/8/8/2B1KB2 w - - 0 1", "mate"),
    ("bn_near", "k7/8/1K6/8/8/8/8/3BN3 w - - 0 1", "mate"),
    ("bn_corner", "7k/8/5K2/8/8/8/8/2B1N3 w - - 0 1", "mate"),
    ("square_win", "8/8/8/k7/8/8/6P1/7K w - - 0 1", "promote"),
    ("square_race", "8/8/8/8/2k5/8/6P1/7K w - - 0 1", "promote"),
    ("kp_key_square", "8/8/4k3/8/3K4/3P4/8/8 w - - 0 1", "promote"),
    ("two_pawns", "8/8/8/4k3/8/8/3PP3/4K3 w - - 0 1", "promote"),
    ("two_pawns_connected", "8/8/3k4/8/8/8/5PP1/6K1 w - - 0 1", "promote"),
    ("lucena", "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1", "promote"),
    ("kp_sixth", "3k4/8/2KP4/8/8/8/8/8 w - - 0 1", "promote"),
    ("rook_behind_pawn", "8/8/8/P7/8/6k1/8/R5K1 w - - 0 1", "promote"),
    ("q_vs_pawn", "8/8/8/8/8/1K6/5kp1/7Q w - - 0 1", "convert"),
    ("rook_vs_pawn", "8/8/8/8/8/3k4/2p5/K5R1 w - - 0 1", "convert"),
    ("q_vs_knight", "8/8/8/3k4/3n4/8/8/KQ6 w - - 0 1", "convert"),
    ("q_vs_rook", "8/8/8/3k4/8/2r5/8/KQ6 w - - 0 1", "convert"),
    ("bishop_vs_knight", "6B1/8/8/n7/4P2K/8/5k2/8 w - - 0 1", "promote"),
    ("kp_opposition_def", "4k3/8/8/4K3/4P3/8/8/8 b - - 0 1", "draw"),
    ("rook_pawn_def", "7k/8/6K1/7P/8/8/8/8 b - - 0 1", "draw"),
    ("wrong_bishop", "7k/8/5K2/7P/8/3B4/8/8 b - - 0 1", "draw"),
    ("philidor", "4k3/8/r7/4PK2/8/8/8/4R3 b - - 0 1", "draw"),
    ("rook_vs_bishop_def", "8/8/8/3k4/8/3b4/8/K2R4 b - - 0 1", "draw"),
    ("rook_vs_knight_def", "8/8/8/8/4k3/4n3/8/1K1R4 b - - 0 1", "draw"),
    ("q_vs_c_pawn_def", "8/6K1/8/Q7/8/8/2pk4/8 b - - 0 1", "draw"),
    ("q_vs_a_pawn_def", "8/6K1/8/8/Q7/8/p1k5/8 b - - 0 1", "draw"),
    ("opposite_bishops_def", "8/8/2b1k3/4P3/3K4/3B4/8/8 b - - 0 1", "draw"),
    ("vancura", "R7/6k1/P4r2/8/8/8/8/K7 b - - 0 1", "draw"),
    # Fortresses (27.9, course module T5.2): any drawing move counts.
    ("fortress_q_vs_rook", "3Q4/6pk/5r2/3K4/8/8/8/8 b - - 0 1", "draw"),
    ("fortress_opposite_bishops", "8/8/4k3/2b5/4PP2/3K4/8/3B4 b - - 0 1", "draw"),
    # Studies by long-dead composers (27.9, entries in ATTRIBUTION.md). The key move of each is the only move that keeps
    # the result per the tablebases (checked below), which also confirms the position was copied from the source correctly.
    ("study_saavedra", "8/8/1KP5/3r4/8/8/8/k7 w - - 0 1", "promote"),
    ("study_reti", "7K/8/k1P5/7p/8/8/8/8 w - - 0 1", "draw"),
    ("study_kling_horwitz", "3R4/5k2/3K4/3P4/8/8/8/3r4 b - - 0 1", "draw"),
    ("study_troitzky_1909", "1q6/2n5/8/8/N2k4/6Q1/3K4/8 w - - 0 1", "mate"),
    ("study_grigoriev_1928", "6K1/8/pp5p/8/7k/3PP3/8/8 w - - 0 1", "promote"),
    ("study_grigoriev_1930", "8/p2p4/8/8/8/k7/5P1P/7K w - - 0 1", "promote"),
    ("study_grigoriev_1936", "8/8/8/3k3p/7P/7K/4P3/8 w - - 0 1", "promote"),
    ("study_grigoriev_1936_draw", "8/8/4pk2/8/8/2p5/2P5/1K6 w - - 0 1", "draw"),
]
STUDY_PREFIX = "study_"
LIMITS = {"promote": 30, "convert": 30, "draw": 15}
MATE_SLACK = 8


def probe(fen: str) -> dict:
    """Requests the evaluation and the optimal move count of a position from the endgame tablebases."""
    from src.core.config import settings

    url = settings.TABLEBASE_URL + "?" + urllib.parse.urlencode({"fen": fen})
    request = urllib.request.Request(url, headers={"User-Agent": "regence-endgame-trainer"})
    return json.load(urllib.request.urlopen(request, timeout=15))


def main() -> None:
    """Checks the canonical endgame trainer positions against Syzygy tablebases."""
    result = []
    for exercise_id, fen, goal in EXERCISES:
        board = chess.Board(fen)
        assert board.is_valid() and not board.is_game_over(), exercise_id
        data = probe(fen)
        category = data.get("category")
        expected = "draw" if goal == "draw" else "win"
        if category != expected:
            raise SystemExit(f"{exercise_id}: tablebases say {category}, but the goal is {expected}")
        keys = [move["san"] for move in data["moves"] if move["category"] == data["moves"][0]["category"]]
        if exercise_id.startswith(STUDY_PREFIX) and len(keys) != 1:
            raise SystemExit(f"{exercise_id}: a study needs a single key move, the tablebases keep the result with {keys}")
        optimum = math.ceil(data["dtm"] / 2) if goal == "mate" and data.get("dtm") else None
        limit = optimum + MATE_SLACK if optimum else LIMITS[goal]
        if exercise_id == "lucena":
            limit = 25
        result.append({"id": exercise_id, "fen": fen, "goal": goal, "limit": limit, "optimum": optimum,
                       "side": "white" if board.turn else "black"})
        print(f"{exercise_id:22} {goal:8} {category:5} optimum={optimum} limit={limit}", flush=True)
        time.sleep(0.6)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(result)} exercises -> {OUT}")


if __name__ == "__main__":
    main()
