"""
Метка «красивая партия» (таск 27.5): жертва материала, за которой победитель ставит мат.

Правило без движка и базы, по ходам партии: победитель матует, а за последние MATE_WINDOW_PLIES полуходов до мата
отдал не меньше SACRIFICE_MIN_POINTS пунктов материала (ценности — как в разменах: пешка 1, лёгкая фигура 3,
ладья 5, ферзь 9). Размен не считается: пока победитель берёт столько же, сколько отдаёт, разность не падает.
Метка ставится при импорте (`services/library.py`) и скриптом `scripts/tag_library.py --all`; ищется фильтром
`beautiful` в `GET /library/games`. «Длинная форсированная линия» из замысла 27.5 требует движка и здесь не ищется.
"""

import chess

PIECE_POINTS = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
SACRIFICE_MIN_POINTS = 3  # отдано не меньше пешечной тройки: фигура за пешку — уже жертва
MATE_WINDOW_PLIES = 14  # жертва и мат — одна комбинация: не дальше семи ходов друг от друга


def _material(board: chess.Board, color: chess.Color) -> int:
    """Материал стороны в пунктах (без короля)."""
    return sum(len(board.pieces(kind, color)) * points for kind, points in PIECE_POINTS.items())


def is_beautiful(start_fen: str | None, moves: list[str]) -> bool:
    """Победитель поставил мат, отдав в последних ходах не меньше SACRIFICE_MIN_POINTS пунктов материала."""
    board = chess.Board(start_fen) if start_fen else chess.Board()
    balances: list[int] = []  # перевес белых после каждого полухода, включая начальную позицию
    try:
        balances.append(_material(board, chess.WHITE) - _material(board, chess.BLACK))
        for uci in moves:
            board.push(chess.Move.from_uci(uci))
            balances.append(_material(board, chess.WHITE) - _material(board, chess.BLACK))
    except (ValueError, AssertionError):
        return False
    if not board.is_checkmate():
        return False
    winner = not board.turn  # мат получил тот, чей ход
    sign = 1 if winner == chess.WHITE else -1
    window = balances[-(MATE_WINDOW_PLIES + 1):]
    peak = max(sign * value for value in window)  # лучший момент победителя в окне
    return peak - sign * window[-1] >= SACRIFICE_MIN_POINTS
