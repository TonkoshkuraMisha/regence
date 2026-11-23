# --- FILE: scripts/measure_bot_phases.py ---
"""
A bot's strength profile by game phase: whether play is even from the first move to the last.

Bots play against themselves (`--games` games each), then a strong engine (depth `--depth`) evaluates the position
after every move, and the bot's loss is counted in centipawns: how much worse the move is than the previous
evaluation, from the mover's view. Losses are collected over three phases: moves 1-8 (mostly the book), 9-20, 21+.
The average loss, the share of blunders (loss > 200 cp) and the share of mistakes (> 100 cp) are shown.

Why: a human-like bot must not change strength abruptly (by the book, then blunders, then strong play again). The script is
an acceptance check for any engine behind the bots: the profile must be even and the loss must match the declared
rating. Data: bot moves - `BOT_INSTANCES[id].choose_move`; the evaluator - Stockfish via `resolve_stockfish_path()`.
The result is printed and, with `--out`, saved as a Markdown table.

Run: `uv run python -m scripts.measure_bot_phases --bots zukertort morphy --games 3`; `--bots all` - all bots.
"""

import argparse
import statistics
import sys
from dataclasses import dataclass, field

import chess
import chess.engine

from src.services.bots import BOT_INSTANCES
from src.services.bots.base import resolve_stockfish_path

# Phase boundaries by move number (inclusive): name -> (first move, last move).
PHASES: dict[str, tuple[int, int]] = {"1-8": (1, 8), "9-20": (9, 20), "21+": (21, 999)}
BLUNDER_CP = 200  # a loss above this is a blunder
MISTAKE_CP = 100  # a loss above this is a mistake
LOSS_CAP_CP = 1000  # a single loss is not counted above this in the average (a mate or a queen blunder does not skew the mean)
MATE_SCORE = 3000  # the price of a mate in centipawns for comparing evaluations
MAX_PLIES = 140  # the game is cut off at this ply


@dataclass
class Profile:
    """The bot's losses by phase and move counters."""

    losses: dict[str, list[int]] = field(default_factory=lambda: {name: [] for name in PHASES})
    plies: int = 0
    book_plies: int = 0


def _evaluate(engine: chess.engine.SimpleEngine, board: chess.Board, depth: int) -> int:
    """Evaluation of a position from White's point of view, cp."""
    info = engine.analyse(board, chess.engine.Limit(depth=depth))
    return int(info["score"].white().score(mate_score=MATE_SCORE) or 0)


def measure(bot_id: str, games: int, depth: int, engine: chess.engine.SimpleEngine) -> Profile:
    """Plays `games` games of the bot against itself and collects losses by phase."""
    bot = BOT_INSTANCES[bot_id]
    profile = Profile()
    for _ in range(games):
        board = chess.Board()
        previous = _evaluate(engine, board, depth)
        while not board.is_game_over(claim_draw=True) and board.ply() < MAX_PLIES:
            reply = bot.choose_move(board.fen())
            mover, move_number = board.turn, board.fullmove_number
            profile.plies += 1
            profile.book_plies += reply["source"] == "opening_book"
            board.push(chess.Move.from_uci(reply["uci"]))
            current = _evaluate(engine, board, depth)
            loss = max(0, (previous - current) if mover == chess.WHITE else (current - previous))
            for name, (first, last) in PHASES.items():
                if first <= move_number <= last:
                    profile.losses[name].append(min(loss, LOSS_CAP_CP))
            previous = current
    return profile


def table_row(bot_id: str, profile: Profile) -> str:
    """A Markdown table row: for each phase - the average loss, blunders and mistakes as a percentage of the phase's moves."""
    cells = []
    for name in PHASES:
        values = profile.losses[name]
        if not values:
            cells.append("—")
            continue
        blunders = 100 * sum(v > BLUNDER_CP for v in values) / len(values)
        mistakes = 100 * sum(v > MISTAKE_CP for v in values) / len(values)
        cells.append(f"{statistics.mean(values):.0f} cp / {blunders:.0f}% / {mistakes:.0f}%")
    return f"| {bot_id} | {profile.plies} | {profile.book_plies} | " + " | ".join(cells) + " |"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bots", nargs="+", default=["all"], help="bot ids or all")
    parser.add_argument("--games", type=int, default=3, help="games per bot")
    parser.add_argument("--depth", type=int, default=10, help="evaluator depth")
    parser.add_argument("--out", help="Markdown file to save the table to")
    args = parser.parse_args()

    bot_ids = sorted(BOT_INSTANCES) if args.bots == ["all"] else args.bots
    path = resolve_stockfish_path()
    if path is None:
        print("Engine not found: put the binary into bin/", file=sys.stderr)
        return 1
    header = ["| bot | moves | from book | " + " | ".join(f"moves {n}" for n in PHASES) + " |",
              "|---|---|---|" + "---|" * len(PHASES),
              "(phase cell: average loss / blunders >200 cp / mistakes >100 cp)"]
    rows = []
    engine = chess.engine.SimpleEngine.popen_uci(path)
    try:
        for bot_id in bot_ids:
            rows.append(table_row(bot_id, measure(bot_id, args.games, args.depth, engine)))
            print(rows[-1], flush=True)
    finally:
        engine.quit()
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write("\n".join([header[0], header[1], *rows, "", header[2], ""]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
