"""
Поиск позиций для уроков в партиях мастеров (data/pgns): приём находит правило, движок подтверждает.

Как работает: каждая партия проходится ход за ходом; правило приёма (registry RULES) смотрит позицию и сыгранный
ход мастера и отбирает «кандидатов». Каждый кандидат проверяется Stockfish: сыгранный ход должен быть лучшим, а
второй по силе ход — слабее не меньше чем на --margin сп (иначе вопрос «найдите ход» угадывается), и оценка для
ходящего — не ниже --min-score. Результат — JSON со списком {fen, move, san, game, rule, scores}; урок собирается из них
вручную (текст объяснения пишет человек, правду хода гарантирует движок). Не для CI: нужен Stockfish и время.

Правила (по реестру RULES):
  interference — фигура встаёт между защитником и защищённой фигурой соперника; защита рвётся, фигура остаётся без защиты;
  rook_lift    — ладья поднимается с первой горизонтали на третью к королю соперника;
  pawn_storm   — штурм пешками (g/h) короля соперника при рокировках в разные стороны;
  blockade     — фигура блокирует проходную пешку соперника;
  quiet_move   — тихий ход (не взятие и не шах), который сильно лучше остальных.

    python -m scripts.dev.mine_lesson_positions --rule interference --limit 12 --out interference.json
"""

import argparse
import glob
import json
import pathlib

import chess
import chess.engine
import chess.pgn

from src.services.bots.base import resolve_stockfish_path

ROOT = pathlib.Path(__file__).resolve().parents[2]
PGN_GLOB = str(ROOT / "data" / "pgns" / "**" / "*.pgn")
MATE_SCORE = 100_000
SLIDERS = (chess.BISHOP, chess.ROOK, chess.QUEEN)


def relative_rank(square: chess.Square, colour: chess.Color) -> int:
    """Горизонталь с точки зрения цвета: 0 — своя первая, 7 — последняя."""
    rank = chess.square_rank(square)
    return rank if colour == chess.WHITE else 7 - rank


def rule_interference(board: chess.Board, move: chess.Move) -> bool:
    """Ход встаёт на линию между защитником-слайдером и защищённой им фигурой соперника, оставляя её без защиты."""
    mover, enemy = board.turn, not board.turn
    if board.is_capture(move):
        return False
    after = board.copy(stack=False)
    after.push(move)
    for target in chess.SquareSet(board.occupied_co[enemy]):
        piece = board.piece_at(target)
        if piece is None or piece.piece_type == chess.KING:
            continue
        defenders = board.attackers(enemy, target)
        for guard in defenders:
            guard_piece = board.piece_at(guard)
            if guard_piece is None or guard_piece.piece_type not in SLIDERS:
                continue
            between = chess.SquareSet(chess.between(guard, target))
            if (move.to_square in between and len(defenders) == 1
                    and after.attackers(mover, target) and not after.attackers(enemy, target)):
                return True
    return False


def rule_rook_lift(board: chess.Board, move: chess.Move) -> bool:
    """Ладья идёт с первой горизонтали на третью к королю соперника (король — на фланге подъёма)."""
    mover, enemy = board.turn, not board.turn
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.ROOK or board.is_capture(move) or board.fullmove_number < 9:
        return False
    if relative_rank(move.from_square, mover) != 0 or relative_rank(move.to_square, mover) != 2:
        return False
    king_file = chess.square_file(board.king(enemy))
    file_ = chess.square_file(move.to_square)
    return (king_file >= 5 and file_ >= 3) or (king_file <= 2 and file_ <= 4)


def rule_pawn_storm(board: chess.Board, move: chess.Move) -> bool:
    """Пешка g/h идёт к королю соперника, рокировки в разные стороны, ходящий уже рокировался."""
    mover, enemy = board.turn, not board.turn
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.PAWN or board.is_capture(move):
        return False
    file_, rank = chess.square_file(move.to_square), relative_rank(move.to_square, mover)
    own_king, enemy_king = board.king(mover), board.king(enemy)
    opposite = (chess.square_file(own_king) <= 2) != (chess.square_file(enemy_king) <= 2)
    return (opposite and rank in (3, 4) and board.fullmove_number >= 10
            and abs(file_ - chess.square_file(enemy_king)) <= 1 and relative_rank(enemy_king, enemy) == 0)


def rule_blockade(board: chess.Board, move: chess.Move) -> bool:
    """Фигура (не король и не пешка) становится перед проходной пешкой соперника, продвинувшейся далеко."""
    mover, enemy = board.turn, not board.turn
    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type in (chess.KING, chess.PAWN) or board.is_capture(move):
        return False
    step = 8 if enemy == chess.WHITE else -8
    pawn_sq = move.to_square - step
    if not 0 <= pawn_sq < 64:
        return False
    pawn = board.piece_at(pawn_sq)
    if pawn is None or pawn.piece_type != chess.PAWN or pawn.color != enemy or relative_rank(pawn_sq, enemy) < 3:
        return False
    file_ = chess.square_file(pawn_sq)
    for our in board.pieces(chess.PAWN, mover):
        ahead = (chess.square_rank(our) - chess.square_rank(pawn_sq)) * (1 if enemy == chess.WHITE else -1) > 0
        if ahead and abs(chess.square_file(our) - file_) <= 1:
            return False
    return True


def rule_quiet_move(board: chess.Board, move: chess.Move) -> bool:
    """Тихий ход: не взятие, не шах, не превращение и не ход короля."""
    piece = board.piece_at(move.from_square)
    return (piece is not None and piece.piece_type != chess.KING and not board.is_capture(move)
            and not board.gives_check(move) and move.promotion is None and board.fullmove_number >= 12)


RULES = {"interference": rule_interference, "rook_lift": rule_rook_lift, "pawn_storm": rule_pawn_storm,
         "blockade": rule_blockade, "quiet_move": rule_quiet_move}


def candidates(rule_name: str):
    """Позиции-кандидаты по правилу: (fen до хода, ход, описание партии)."""
    rule = RULES[rule_name]
    seen: set[str] = set()
    for path in sorted(glob.glob(PGN_GLOB, recursive=True)):
        with open(path, encoding="utf-8", errors="ignore") as handle:
            while True:
                try:
                    game = chess.pgn.read_game(handle)
                except Exception:  # noqa: BLE001 — битая запись PGN пропускается, поиск идёт дальше
                    break
                if game is None:
                    break
                node = game
                while node.variations:
                    nxt = node.variation(0)
                    board = node.board()
                    if rule(board, nxt.move):
                        key = board.board_fen()
                        if key not in seen:
                            seen.add(key)
                            info = f"{game.headers.get('White')} — {game.headers.get('Black')}, {game.headers.get('Date')}"
                            yield board.fen(), nxt.move, info
                    node = nxt


def main() -> None:
    """Проверяет кандидатов движком и сохраняет подтверждённые."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rule", required=True, choices=sorted(RULES))
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--time", type=float, default=0.8)
    parser.add_argument("--margin", type=int, default=150)
    parser.add_argument("--min-score", type=int, default=120)
    parser.add_argument("--max-candidates", type=int, default=600)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    engine = chess.engine.SimpleEngine.popen_uci(resolve_stockfish_path())
    found: list[dict] = []
    checked = 0
    try:
        for fen, move, game in candidates(args.rule):
            checked += 1
            if checked > args.max_candidates or len(found) >= args.limit:
                break
            board = chess.Board(fen)
            infos = engine.analyse(board, chess.engine.Limit(time=args.time), multipv=2)
            if len(infos) < 2 or infos[0]["pv"][0] != move:
                continue
            scores = [i["score"].pov(board.turn).score(mate_score=MATE_SCORE) for i in infos]
            if scores[0] >= args.min_score and scores[0] - scores[1] >= args.margin:
                item = {"fen": fen, "move": move.uci(), "san": board.san(move), "game": game, "rule": args.rule,
                        "scores": scores}
                found.append(item)
                print(item, flush=True)
    finally:
        engine.quit()
    args.out.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"проверено {checked}, найдено {len(found)} -> {args.out}")


if __name__ == "__main__":
    main()
