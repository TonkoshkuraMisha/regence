# --- FILE: src/services/game_engine.py ---
"""
Chess rules for games: move validation, the game result, starting positions, PGN writing. All on python-chess,
without an engine.

* process_move -- whether a move is legal in the position; the new position, the move record and, if the game ended, its
  result.
* terminal_outcome -- mate, stalemate, insufficient material, threefold repetition and the 50-move rule; draws
  by repetition and by 50 moves are awarded automatically, without a claim, but only when the position has already arisen on
  the board.
  Repetition cannot be checked from a single position, so restore_board replays the game from the PGN.
* flag_outcome -- time ran out: a loss, except when the opponent cannot deliver mate by any
  sequence of moves -- then a draw (FIDE rule 6.9).
* A starting position of a game with odds or from a custom position is checked for validity by the rules
  (board_from_start_fen); Fischer chess is stored in Shredder-FEN -- the record shows the variant (is_chess960_fen).
* normalize_pgn_text -- a game in canonical form so that extra blank lines do not break reading.
* normalize_result -- a result from a foreign PGN is mapped to one of GAME_RESULTS.

The module takes no data from the DB, Redis or settings: everything comes from arguments. Called by src/api/bots.py,
websockets.py and
analysis.py; the services game_state, matchmaker, analysis_service, library, game_import, mate_finder, move_check, odds,
personal_puzzles; the game and imported_game models (the GAME_RESULTS set of results) and src/db/seed.py.
"""

import io
import logging
import re

import chess
import chess.pgn

from src.core.errors import DomainValueError

logger = logging.getLogger(__name__)

# The ordinary initial setup; the empty value and a start_fen equal to it also return it.
STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class InvalidStartPositionError(DomainValueError):
    """The starting position cannot be parsed or is impossible by the rules."""


def board_from_start_fen(start_fen: str | None) -> chess.Board:
    """
    A board for a game or analysis from a given starting position (None -- the ordinary setup).

    Not only the FEN syntax is checked but the position itself: chess.Board also accepts impossible ones
    (no king, kings adjacent, the side that has just moved is in check) -- the engine may
    crash on such, and a "game" from them makes no sense.
    """
    if start_fen is None or not start_fen.strip() or start_fen.strip() == STARTING_FEN:
        return chess.Board()
    try:
        board = chess.Board(start_fen.strip())
    except ValueError:
        raise InvalidStartPositionError("invalid_fen") from None
    if not board.is_valid():
        raise InvalidStartPositionError("invalid_position")
    return board


# File letters in the castling field of the FEN -- a sign of Shredder-FEN, that is, a Fischer game.
_CHESS960_CASTLING = set("ABCDEFGHabcdefgh")
# The PGN header that marks a Fischer game.
CHESS960_HEADER = '[Variant "Chess960"]'


def is_chess960_fen(fen: str | None) -> bool:
    """
    A Fischer game position (21.3): castling rights are written with file letters (Shredder-FEN, "HAha"). Chess960 games
    store positions only this way -- ordinary chess never has such a record, so the FEN shows which rules
    the game follows.
    """
    parts = (fen or "").split()
    return len(parts) > 2 and any(c in _CHESS960_CASTLING for c in parts[2])


def game_variant(fen: str | None, pgn: str | None = "") -> str:
    """The variant of a running game for the client: "chess960" (by the PGN header or Shredder-FEN) or "standard"."""
    return "chess960" if CHESS960_HEADER in (pgn or "") or is_chess960_fen(fen) else "standard"


def board_from_fen(fen: str, chess960: bool = False) -> chess.Board:
    """A board from a game FEN: in 960 mode if so stated or if the FEN is written in the 960 way."""
    return chess.Board(fen, chess960=chess960 or is_chess960_fen(fen))


def fen_of(board: chess.Board) -> str:
    """The FEN for storage: for a 960 game -- Shredder-FEN (see is_chess960_fen)."""
    return board.fen(shredder=True) if board.chess960 else board.fen()


def validate_start_fen(start_fen: str | None) -> str:
    """
    Canonical record of a starting position: STARTING_FEN for the empty value, otherwise the FEN after
    validation. InvalidStartPositionError (a ValueError) -- for an unparsable or impossible position.
    """
    return board_from_start_fen(start_fen).fen()


def is_standard_start(board: chess.Board) -> bool:
    """A game started from the ordinary setup (the board has no moves and the position is the starting one)."""
    return board.root().fen() == STARTING_FEN


# Game results stored by the database (the CHECK on games, imported_games, library_games, arena_games): White wins,
# Black wins, a draw, "unfinished / unknown".
GAME_RESULTS = ("1-0", "0-1", "1/2-1/2", "*")
# Other ways a result is written in foreign PGNs -- mapped to the standard.
_RESULT_ALIASES = {"½-½": "1/2-1/2", "1/2": "1/2-1/2", "0.5-0.5": "1/2-1/2", "=": "1/2-1/2", "1:0": "1-0", "0:1": "0-1",
                   "1–0": "1-0", "0–1": "0-1"}


def normalize_result(tag: str | None) -> str:
    """
    A result from the Result header of a foreign PGN -- as one of GAME_RESULTS: known spellings (1/2-1/2, 1:0, a dash instead
    of
    a hyphen) are mapped to the standard, everything else (empty, "?", junk) -- "*". Used by the library import
    (library.py), the import from sites (game_import.py) and the archive loader (src/db/seed.py).
    """
    value = (tag or "").strip()
    if value in GAME_RESULTS:
        return value
    return _RESULT_ALIASES.get(value, "*")


# Any line break, including the doubled "\\r\\r\\n" from Windows text mode.
_LINE_BREAK_RE = re.compile(r"\r+\n|\r")


def normalize_pgn_text(pgn_text: str) -> str:
    """
    One game in canonical form: headers in a row, one blank line, moves without blank lines.

    By the PGN standard a blank line ends a game. Files saved on Windows in text mode
    on top of already Windows line breaks get "\\r\\r\\n" -- after parsing that is a blank line after
    each line, and python-chess sees a game of one header with no moves (analysis "at 100 %" of an empty
    game). The frontend (chess.js) tolerates such lines, so the game looked normal at that.
    """
    lines = [line.strip() for line in _LINE_BREAK_RE.sub("\n", pgn_text.lstrip("﻿")).split("\n")]
    headers: list[str] = []
    i = 0
    while i < len(lines) and (not lines[i] or lines[i].startswith("[")):
        if lines[i]:
            headers.append(lines[i])
        i += 1
    movetext = "\n".join(line for line in lines[i:] if line)
    if not headers:
        return movetext
    return "\n".join(headers) + "\n\n" + movetext + "\n"


def read_pgn_game(pgn_text: str) -> chess.pgn.Game | None:
    """chess.pgn.read_game for one saved game, resistant to extra blank lines."""
    return chess.pgn.read_game(io.StringIO(normalize_pgn_text(pgn_text)))


def start_fen_of(pgn_text: str | None) -> str | None:
    """
    The starting position of a game from the FEN header of its PGN (a game from a position: odds, Fischer); without the
    header -- None.
    """
    game = read_pgn_game(pgn_text or "")
    return game.headers.get("FEN") if game is not None else None


def _replay_pgn_document(pgn_text: str) -> chess.Board | None:
    """The board at the end of a PGN document with headers (including SetUp/FEN) -- with the move history."""
    game = read_pgn_game(pgn_text)
    if game is None or game.errors:
        return None
    return game.end().board()


def restore_board(fen: str, pgn_movetext: str = "", start_fen: str | None = None) -> chess.Board:
    """
    Restores the board together with the move history.

    The history is needed for the position repetition rules (threefold / fivefold), which
    cannot be checked from a single FEN. Moves are replayed from the PGN string of the game
    ("1. e4 e5 2. Nf3 ...") from the starting position: the ordinary setup or start_fen. A full
    PGN document with a FEN header is parsed whole -- the starting position is taken from it.
    If the PGN is empty, damaged or does not lead to the given FEN, the board from the FEN without history is used.
    """
    safe_fen = fen.strip() if fen and fen.strip() else STARTING_FEN
    movetext = (pgn_movetext or "").strip()

    chess960 = CHESS960_HEADER in movetext or is_chess960_fen(safe_fen)
    if movetext and "[FEN " in movetext:
        replayed = _replay_pgn_document(movetext)
        if replayed is not None and fen_of(replayed) == safe_fen:
            return replayed
        logger.warning("PGN document does not lead to the stored FEN, falling back to FEN-only board")
    elif movetext:
        try:
            board = board_from_start_fen(start_fen)
            for token in movetext.split():
                # Move numbers ("12.", "12...") and the result ("1-0") start with a digit, SAN never does.
                if token[0].isdigit() or token == "*":
                    continue
                board.push_san(token)
        except ValueError as exc:
            logger.warning("Cannot replay PGN history (%s), falling back to FEN-only board", exc)
        else:
            if board.fen() == safe_fen:
                return board
            logger.warning("Replayed PGN does not match stored FEN, falling back to FEN-only board")

    return board_from_fen(safe_fen, chess960)


def terminal_outcome(board: chess.Board) -> tuple[str, str] | None:
    """
    The game result by the position on the board (with move history) or None if the game continues.

    Draws by repetition and the 50-move rule are recorded automatically, but only by the position
    that has actually arisen. board.is_game_over(claim_draw=True) is unsuitable here: it awards
    a draw even when the repetition is merely reachable with the next move.
    """
    if not (board.is_game_over() or board.is_repetition(3) or board.is_fifty_moves()):
        return None
    if board.is_checkmate():
        return ("0-1" if board.turn == chess.WHITE else "1-0"), "checkmate"
    if board.is_stalemate():
        return "1/2-1/2", "stalemate"
    if board.is_insufficient_material():
        return "1/2-1/2", "insufficient_material"
    if board.is_fifty_moves():
        return "1/2-1/2", "50_move_rule"
    if board.is_repetition(3):
        return "1/2-1/2", "repetition"
    return "1/2-1/2", "draw"


def side_has_mating_material(board_fen: str | None, color: str) -> bool:
    """
    Whether color ("white" / "black") can in principle deliver mate by any sequence of legal moves
    (by material, taking bishop square colours into account). If the FEN cannot be parsed -- we assume it can.
    """
    try:
        board = chess.Board(board_fen or STARTING_FEN)
    except ValueError:
        return True
    return not board.has_insufficient_material(chess.WHITE if color == "white" else chess.BLACK)


# Termination reason for a draw on flag: the opponent has no mating material.
FLAG_DRAW_TERMINATION = "timeout_vs_insufficient_material"


def flag_outcome(board_fen: str | None, flagged_color: str) -> tuple[str, str]:
    """
    The game result when flagged_color has run out of time (FIDE rule 6.9).

    A loss, unless the opponent has material with which mate is impossible by any
    sequence of legal moves -- then a draw. has_insufficient_material considers
    only material (and bishop square colours) and is guaranteed not to declare a draw where mate
    is possible: for example, knight against rook is a win (a cooperative mate exists).
    Returns (result, termination).
    """
    winner = "black" if flagged_color == "white" else "white"
    if not side_has_mating_material(board_fen, winner):
        return "1/2-1/2", FLAG_DRAW_TERMINATION
    return ("0-1" if flagged_color == "white" else "1-0"), "timeout"


class GameEngine:
    """
    Validation and application of a move (process_move) is the only point through which a move of a game with a human gets
    into the
    position. It stores no state: the ready instance is `engine` at the end of the module.
    """
    @staticmethod
    def process_move(fen: str, move_str: str, current_pgn: str = "") -> tuple[bool, dict | None]:
        """
        Validates the move, applies it to the current position (FEN) and returns the new data.

        Returns: (is_valid, move_data)
        Where move_data contains:
        - new_fen: str (the new board state)
        - new_pgn: str (the updated PGN move string)
        - san: str (pretty notation, for example "Nf3")
        - uci: str (universal notation, for example "g1f3")
        - fullmove_number: int (the move number)
        - is_obvious: bool (flag of the only legal move, for the anti-cheat)
        - is_game_over: bool
        - result: str | None ("1-0", "0-1", "1/2-1/2")
        - termination: str | None ("checkmate", "stalemate", "repetition", etc.)
        """
        try:
            board = restore_board(fen, current_pgn)
        except ValueError:
            return False, None

        # 1. Try to parse the move (UCI or SAN)
        move = None
        try:
            candidate = chess.Move.from_uci(move_str)
            if candidate in board.legal_moves:
                move = candidate
        except ValueError:
            pass

        if move is None:
            try:
                candidate = board.parse_san(move_str)
                if candidate in board.legal_moves:
                    move = candidate
            except ValueError:
                return False, None

        if move is None or move not in board.legal_moves:
            return False, None

        # 2. Collect metadata BEFORE making the move
        legal_moves_count = board.legal_moves.count()
        is_obvious = legal_moves_count == 1
        is_white_turn = board.turn == chess.WHITE
        fullmove_number = board.fullmove_number

        san = board.san(move)
        uci = move.uci()

        # Build the PGN string in O(1) without rebuilding the whole tree
        pgn_base = (current_pgn or "").strip()
        if is_white_turn:
            move_token = f"{fullmove_number}. {san}"
        else:
            move_token = san if pgn_base else f"{fullmove_number}... {san}"
        # After the headers of a game from a position (SetUp/FEN) the moves start on a new line, as in a PGN document.
        separator = "\n\n" if pgn_base.endswith("]") else " "
        new_pgn = f"{pgn_base}{separator}{move_token}".strip()

        # 3. Apply the move on the board
        board.push(move)
        new_fen = fen_of(board)

        # 4. Check the game-end conditions
        outcome = terminal_outcome(board)
        is_game_over = outcome is not None
        result, termination = outcome if outcome else (None, None)

        return True, {
            "new_fen": new_fen,
            "new_pgn": new_pgn,
            "san": san,
            "uci": uci,
            "fullmove_number": fullmove_number,
            "is_obvious": is_obvious,
            "is_game_over": is_game_over,
            "result": result,
            "termination": termination
        }


engine = GameEngine()
