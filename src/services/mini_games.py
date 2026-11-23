# --- FILE: src/services/mini_games.py ---
"""
Trainer games (task 19.8) - teaching games with simplified rules on top of python-chess (the ordinary engine does not know
them).

* pawn_war - "Pawn War": pawns only; the first to get a pawn through or capture all of the opponent's pawns wins.
* king_pawns - "King and Pawns": kings and eight pawns each; the first to get a pawn through (or deliver mate) wins.
* queen_vs_pawns - "Queen against Eight Pawns": the white queen captures all pawns - White wins; a pawn arrives or
  the queen is lost - Black wins.
* rook_vs_pawns - "Rook against Pawns": a white rook against four pawns, the same conditions.
* capture_flag - "Capture the Flag": kings and pawns; the first to bring the king to the opponent's back rank wins
  (or gets a pawn through - this rule is common to all games).

If the side to move has no moves it is a draw (in games with kings: if in check - a loss). Promotion ends
the game at once (to a queen). Without kings there is no check test - moves are pseudo-legal. The bot is a search with
alpha-beta pruning and a simple evaluation (material, pawn advancement, the king's path to the flag): for these games that
is enough.

The server stores nothing: the client sends the position (FEN) with each move, the server checks the move by the game rules,
sums up the result and replies with the bot's move (src/api/mini_games.py). These games have no rating and no result records.
"""

from dataclasses import dataclass

import chess

from src.core.errors import DomainError


@dataclass(frozen=True)
class MiniGame:
    """Game: code, starting position and whether there are kings on the board (kings: legal moves, none: pseudo-legal)."""

    id: str
    fen: str
    kings: bool


GAMES: dict[str, MiniGame] = {
    "pawn_war": MiniGame("pawn_war", "8/pppppppp/8/8/8/8/PPPPPPPP/8 w - - 0 1", kings=False),
    "king_pawns": MiniGame("king_pawns", "4k3/pppppppp/8/8/8/8/PPPPPPPP/4K3 w - - 0 1", kings=True),
    "queen_vs_pawns": MiniGame("queen_vs_pawns", "8/pppppppp/8/8/8/8/8/3Q4 w - - 0 1", kings=False),
    "rook_vs_pawns": MiniGame("rook_vs_pawns", "8/pppp4/8/8/8/8/8/7R w - - 0 1", kings=False),
    "capture_flag": MiniGame("capture_flag", "4k3/pppppppp/8/8/8/8/PPPPPPPP/4K3 w - - 0 1", kings=True),
}

# Bot evaluation (in conventional centipawns): WIN is a won game, deliberately larger than any sum of material and bonuses.
WIN = 100_000
PIECE_VALUE = {chess.PAWN: 100, chess.KNIGHT: 300, chess.BISHOP: 300, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}


def get_game(game_id: str) -> MiniGame:
    game = GAMES.get(game_id)
    if game is None:
        raise DomainError("mini_game_not_found")
    return game


def board_of(game: MiniGame, fen: str) -> chess.Board:
    """
    Board from the client's FEN. Only the syntax and the presence of both kings in games with kings are checked: positions
    without kings are impossible for ordinary chess, so the general position validation is not applied here.
    """
    try:
        board = chess.Board(fen)
    except ValueError:
        raise DomainError("mini_game_bad_position") from None
    if game.kings and (board.king(chess.WHITE) is None or board.king(chess.BLACK) is None):
        raise DomainError("mini_game_bad_position")
    return board


def moves(game: MiniGame, board: chess.Board) -> list[chess.Move]:
    """Moves by the game rules: with kings - legal, without - pseudo-legal; promotion - only to a queen."""
    source = board.legal_moves if game.kings else board.pseudo_legal_moves
    return [m for m in source if m.promotion in (None, chess.QUEEN)]


def result(game: MiniGame, board: chess.Board) -> str | None:
    """Result: '1-0', '0-1', '1/2-1/2' or None (the game continues). Checked after every move."""
    last_rank = {chess.WHITE: 7, chess.BLACK: 0}
    # A pawn arrived (promoted) - its side wins. There are no queens at the start of the games (except White's in "Queen
    # against Pawns"), so a queen on the last rank is a promotion.
    for color in (chess.WHITE, chess.BLACK):
        if game.id == "queen_vs_pawns" and color == chess.WHITE:
            continue
        if any(chess.square_rank(sq) == last_rank[color] for sq in board.pieces(chess.QUEEN, color)):
            return "1-0" if color == chess.WHITE else "0-1"
    if game.id == "capture_flag":
        for color in (chess.WHITE, chess.BLACK):
            king = board.king(color)
            if king is not None and chess.square_rank(king) == last_rank[color]:
                return "1-0" if color == chess.WHITE else "0-1"
    # All opponent pawns captured; in the "piece against pawns" games, losing the white piece is a Black win.
    if game.id == "pawn_war":
        if not board.pieces(chess.PAWN, chess.BLACK):
            return "1-0"
        if not board.pieces(chess.PAWN, chess.WHITE):
            return "0-1"
    if game.id in ("queen_vs_pawns", "rook_vs_pawns"):
        if not board.pieces(chess.PAWN, chess.BLACK):
            return "1-0"
        if not board.pieces(chess.QUEEN, chess.WHITE) and not board.pieces(chess.ROOK, chess.WHITE):
            return "0-1"
    if not moves(game, board):
        if game.kings and board.is_check():
            return "0-1" if board.turn == chess.WHITE else "1-0"
        return "1/2-1/2"
    return None


def play(game: MiniGame, board: chess.Board, uci: str) -> str | None:
    """Player move (UCI; promotion may be omitted - queen). Returns the result after the move."""
    if result(game, board) is not None:
        raise DomainError("mini_game_over")
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        raise DomainError("mini_game_illegal_move") from None
    piece = board.piece_at(move.from_square)
    if piece and piece.piece_type == chess.PAWN and chess.square_rank(move.to_square) in (0, 7) and move.promotion is None:
        move = chess.Move(move.from_square, move.to_square, promotion=chess.QUEEN)
    if move not in moves(game, board):
        raise DomainError("mini_game_illegal_move")
    board.push(move)
    return result(game, board)


def evaluate(game: MiniGame, board: chess.Board) -> int:
    """
    Evaluation from the point of view of the side to move: a finished game is +-WIN (a draw is 0), otherwise material by
    PIECE_VALUE plus a bonus for advancement - the square of the number of ranks travelled x 6 for a pawn and x 25 for a
    king in "Capture the Flag".
    """
    outcome = result(game, board)
    if outcome is not None:
        score = {"1-0": WIN, "0-1": -WIN, "1/2-1/2": 0}[outcome]
        return score if board.turn == chess.WHITE else -score
    total = 0
    for square, piece in board.piece_map().items():
        value = PIECE_VALUE[piece.piece_type]
        if piece.piece_type == chess.PAWN:
            advance = chess.square_rank(square) if piece.color == chess.WHITE else 7 - chess.square_rank(square)
            value += advance * advance * 6
        if piece.piece_type == chess.KING and game.id == "capture_flag":
            advance = chess.square_rank(square) if piece.color == chess.WHITE else 7 - chess.square_rank(square)
            value += advance * advance * 25
        total += value if piece.color == chess.WHITE else -value
    return total if board.turn == chess.WHITE else -total


def _search(game: MiniGame, board: chess.Board, depth: int, alpha: int, beta: int) -> int:
    """Search to depth plies with alpha-beta pruning (negamax): evaluation for the side to move."""
    if depth == 0 or result(game, board) is not None:
        return evaluate(game, board)
    best = -WIN * 2
    # Captures and advances first - cutoffs work better.
    ordered = sorted(moves(game, board), key=lambda m: (board.is_capture(m), m.promotion is not None), reverse=True)
    for move in ordered:
        board.push(move)
        score = -_search(game, board, depth - 1, -beta, -alpha)
        board.pop()
        if score > best:
            best = score
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def bot_move(game: MiniGame, board: chess.Board, depth: int = 3) -> chess.Move | None:
    """
    Bot move: the best by search to depth plies; on a tie, the first in the order "captures, promotions, move
    notation" (deterministic, no randomness). None - there are no moves.
    """
    best_move, best_score = None, -WIN * 3
    ordered = sorted(moves(game, board), key=lambda m: (board.is_capture(m), m.promotion is not None, m.uci()), reverse=True)
    for move in ordered:
        board.push(move)
        score = -_search(game, board, depth - 1, -WIN * 2, WIN * 2)
        board.pop()
        if score > best_score:
            best_move, best_score = move, score
    return best_move
