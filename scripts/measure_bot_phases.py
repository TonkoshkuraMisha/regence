# --- FILE: scripts/measure_bot_phases.py ---
"""
Профиль силы бота по фазам партии: ровная ли игра от первого хода до последнего.

Боты играют сами с собой (по `--games` партий каждый), затем сильный движок (глубина `--depth`) оценивает позицию
после каждого хода, и считается потеря бота в сантипешках: на сколько ход хуже предыдущей оценки с точки зрения
ходившего. Потери собираются по трём фазам — ходы 1–8 (в основном дебютная книга), 9–20 (сразу после книги) и 21+.
Показывается средняя потеря, доля зевков (потеря > 200 сп) и доля ошибок (> 100 сп).

Зачем: человечный бот не должен менять силу скачком (чисто по книге, потом зевки, потом снова сильная игра). Скрипт —
приёмочная проверка для любого движка за ботами: профиль должен быть ровным, а потеря соответствовать заявленному
рейтингу. Данные: ходы бота — `BOT_INSTANCES[id].choose_move`; оценщик — Stockfish по `resolve_stockfish_path()`.
Результат печатается и при `--out` сохраняется таблицей Markdown.

Запуск: `uv run python -m scripts.measure_bot_phases --bots zukertort morphy --games 3`; `--bots all` — все боты.
"""

import argparse
import statistics
import sys
from dataclasses import dataclass, field

import chess
import chess.engine

from src.services.bots import BOT_INSTANCES
from src.services.bots.base import resolve_stockfish_path

# Границы фаз по номеру хода (включительно): имя → (первый ход, последний ход).
PHASES: dict[str, tuple[int, int]] = {"1-8": (1, 8), "9-20": (9, 20), "21+": (21, 999)}
BLUNDER_CP = 200  # потеря больше этого — зевок
MISTAKE_CP = 100  # потеря больше этого — ошибка
LOSS_CAP_CP = 1000  # одна потеря в среднем не считается больше (мат и зевок ферзя не перекашивают среднее)
MATE_SCORE = 3000  # цена мата в сантипешках для сравнения оценок
MAX_PLIES = 140  # партия обрывается на этом полуходе


@dataclass
class Profile:
    """Потери бота по фазам и счётчики ходов."""

    losses: dict[str, list[int]] = field(default_factory=lambda: {name: [] for name in PHASES})
    plies: int = 0
    book_plies: int = 0


def _evaluate(engine: chess.engine.SimpleEngine, board: chess.Board, depth: int) -> int:
    """Оценка позиции с точки зрения белых, сп."""
    info = engine.analyse(board, chess.engine.Limit(depth=depth))
    return int(info["score"].white().score(mate_score=MATE_SCORE) or 0)


def measure(bot_id: str, games: int, depth: int, engine: chess.engine.SimpleEngine) -> Profile:
    """Играет `games` партий бота с самим собой и собирает потери по фазам."""
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
    """Строка таблицы Markdown: по каждой фазе — средняя потеря, зевки и ошибки в процентах от ходов фазы."""
    cells = []
    for name in PHASES:
        values = profile.losses[name]
        if not values:
            cells.append("—")
            continue
        blunders = 100 * sum(v > BLUNDER_CP for v in values) / len(values)
        mistakes = 100 * sum(v > MISTAKE_CP for v in values) / len(values)
        cells.append(f"{statistics.mean(values):.0f} сп / {blunders:.0f}% / {mistakes:.0f}%")
    return f"| {bot_id} | {profile.plies} | {profile.book_plies} | " + " | ".join(cells) + " |"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bots", nargs="+", default=["all"], help="id ботов или all")
    parser.add_argument("--games", type=int, default=3, help="партий на бота")
    parser.add_argument("--depth", type=int, default=10, help="глубина оценщика")
    parser.add_argument("--out", help="файл Markdown для сохранения таблицы")
    args = parser.parse_args()

    bot_ids = sorted(BOT_INSTANCES) if args.bots == ["all"] else args.bots
    path = resolve_stockfish_path()
    if path is None:
        print("Движок не найден: положите бинарник в bin/", file=sys.stderr)
        return 1
    header = ["| бот | ходов | из книги | " + " | ".join(f"ходы {n}" for n in PHASES) + " |",
              "|---|---|---|" + "---|" * len(PHASES),
              "(ячейка фазы: средняя потеря / зевки >200 сп / ошибки >100 сп)"]
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
