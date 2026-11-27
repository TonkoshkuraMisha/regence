"""
"Theme" marks of library games (task 27.5): which tactical motifs decided a game.

The rule needs no engine, it works on the game's moves with the static motif detector of the mentor
(`mentor_service.analyze_move`). A move is a key moment when the side that played it is at least PAYOFF_MIN_POINTS points
of material up within the next PAYOFF_PLIES half-moves (values as in `beauty.PIECE_POINTS`). The motifs this move created
in favour of the mover are then the game's themes, translated to registry themes (`themes.THEMES`, the `detector` codes)
and limited to GAME_THEMES: the techniques that can be seen on the board and explain a win of material. Positional motifs
(open file, passed pawn, battery) and `hanging` (almost every capture) are not marks.

The cheap material check goes first and the detector runs only for the moves that pay off, so a game costs a few dozen
detector calls. The marks are stored in `library_games.themes` as ",fork,pin," (see `encode`) and set on import
(`services/library.py`) and by `scripts/tag_library.py --all`; they are searched with the filter `theme` of
`GET /library/games`. The mark says "the motif was created and material followed", not that the motif won the material.
"""

import chess

from src.services.beauty import PIECE_POINTS
from src.services.mentor_service import analyze_move
from src.services.themes import THEMES

# Registry themes that can be a mark of a game, in the order they are shown in the library filter.
GAME_THEMES = ("fork", "double_check", "pin", "skewer", "discovered_attack", "discovered_check", "overload",
               "interference", "trapped_piece")
PAYOFF_PLIES = 3  # the move, the reply and the mover's next move: a tactic pays off at once or it is not a tactic
PAYOFF_MIN_POINTS = 2  # at least two pawns net: a pawn won by a quiet move is not a key moment
# Detector motif code -> registry theme, taken from the registry so that a new detector code is added in one place.
MOTIF_THEME = {motif: theme.code for theme in THEMES if theme.code in GAME_THEMES for motif in theme.detector}


def _balance(board: chess.Board) -> int:
    """White's material advantage in points (without the kings)."""
    return sum((len(board.pieces(kind, chess.WHITE)) - len(board.pieces(kind, chess.BLACK))) * points
               for kind, points in PIECE_POINTS.items())


def game_themes(start_fen: str | None, moves: list[str]) -> list[str]:
    """Registry themes (GAME_THEMES order) of the tactics that paid off in the game; broken moves end the search."""
    board = chess.Board(start_fen) if start_fen else chess.Board()
    played: list[tuple[chess.Board, chess.Move]] = []
    balances = [_balance(board)]
    try:
        for uci in moves:
            move = chess.Move.from_uci(uci)
            played.append((board.copy(stack=False), move))
            board.push(move)
            balances.append(_balance(board))
    except (ValueError, AssertionError):
        return []
    found: set[str] = set()
    for index, (before, move) in enumerate(played):
        sign = 1 if before.turn == chess.WHITE else -1
        later = balances[min(index + 1 + PAYOFF_PLIES, len(balances) - 1)]
        if sign * (later - balances[index]) < PAYOFF_MIN_POINTS:
            continue
        for motif in analyze_move(before, move).created:
            if motif.code in MOTIF_THEME:
                found.add(MOTIF_THEME[motif.code])
    return [code for code in GAME_THEMES if code in found]


def encode(codes: list[str]) -> str:
    """Storage form ",fork,pin," (empty for no marks): a theme is searched as the substring ",code,"."""
    return f",{','.join(codes)}," if codes else ""


def decode(stored: str) -> list[str]:
    """The theme codes of a stored value."""
    return [code for code in stored.split(",") if code]
