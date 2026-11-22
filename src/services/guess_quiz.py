# --- FILE: src/services/guess_quiz.py ---
"""
Вопросы после партии в режиме «Угадай ход» (таск 14.3, «партия целиком»): три вопроса о только что разобранной партии
мастера — кто выиграл, где был ключевой момент и кончилась ли партия матом. Ответы известны по данным партии
(`games.result`, PGN) и отобранным моментам (`guess_positions.gap_cp` — отрыв лучшего хода): движок не вызывается.
Правила — чистые функции без базы: варианты и верные ответы детерминированы (зерно — id партии), поэтому сервер
ничего не хранит: проверка пересчитывает те же вопросы. Сервер отдаёт коды вариантов, текст собирает клиент.
"""

import io
import random

import chess
import chess.pgn

# Вопросы: код вопроса -> варианты по умолчанию (для «ключевого момента» варианты строятся по партии).
WINNER_OPTIONS = ("white", "black", "draw")
MATE_OPTIONS = ("yes", "no")
# Сколько вариантов у вопроса про ключевой момент: верный и до двух правдоподобных.
KEY_MOMENT_OPTIONS = 3
# Минимум отобранных моментов, чтобы спрашивать про ключевой (с одним моментом вопрос выдаёт ответ).
MIN_MOMENTS_FOR_KEY = 2


def moment_code(ply: int) -> str:
    """Код хода для варианта: номер хода и сторона («12w» — 12-й ход белых; ply — полуход с нуля)."""
    return f"{ply // 2 + 1}{'w' if ply % 2 == 0 else 'b'}"


def winner_of(result: str | None) -> str:
    """Победитель по итогу партии: white / black / draw (всё, кроме 1-0 и 0-1, — ничья)."""
    return {"1-0": "white", "0-1": "black"}.get(result or "", "draw")


def plies_and_mate(pgn: str | None) -> tuple[int, bool]:
    """(число полуходов, кончается ли партия матом на доске) по записи ходов; нечитаемая запись — (0, False)."""
    if not pgn:
        return 0, False
    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
    except (ValueError, KeyError):
        return 0, False
    if game is None:
        return 0, False
    end = game.end()
    return end.ply(), end.board().is_checkmate()


def build_quiz(
        game_id: int, result: str | None, final_mate: bool, moments: list[tuple[int, int]], total_plies: int,
) -> tuple[list[dict], dict[str, str]]:
    """
    (вопросы, верные ответы). moments — (полуход, отрыв лучшего хода) отобранных моментов партии; ключевой момент — с
    наибольшим отрывом. Неверные варианты ключевого момента — другие ходы партии (зерно — id партии, порядок
    постоянный). Вопрос про ключевой момент есть, только если моментов не меньше MIN_MOMENTS_FOR_KEY.
    """
    questions = [{"id": "winner", "options": list(WINNER_OPTIONS)}]
    answers = {"winner": winner_of(result)}
    if len(moments) >= MIN_MOMENTS_FOR_KEY:
        key_ply = max(moments, key=lambda m: (m[1], -m[0]))[0]
        rng = random.Random(game_id)
        # Игра идёт за ту сторону, что в позиции момента; неверные варианты — ходы той же стороны, не отобранные.
        selected = {ply for ply, _gap in moments}
        pool = [p for p in range(key_ply % 2, max(total_plies, key_ply + 1), 2) if p not in selected]
        wrong = rng.sample(pool, min(KEY_MOMENT_OPTIONS - 1, len(pool)))
        options = [moment_code(p) for p in [key_ply, *wrong]]
        rng.shuffle(options)
        questions.append({"id": "key_moment", "options": options})
        answers["key_moment"] = moment_code(key_ply)
    questions.append({"id": "mate", "options": list(MATE_OPTIONS)})
    answers["mate"] = "yes" if final_mate else "no"
    return questions, answers


def check_quiz(answers: dict[str, str], correct: dict[str, str]) -> dict:
    """Итог: {score, total, results: {вопрос: верно ли}, correct: верные ответы}. Нет ответа на вопрос — неверно."""
    results = {question: answers.get(question) == right for question, right in correct.items()}
    return {"score": sum(results.values()), "total": len(correct), "results": results, "correct": correct}
