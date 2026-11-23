# --- FILE: src/services/drill_generator.py ---
"""
Generator exercises (task 13.7): positions are not from the database but set up by seed. The "kind x piece" matrix:

* capture -- capture an undefended opponent piece;
* fork -- a fork: a move to a safe square from which two targets are attacked (the king, an undefended or more valuable piece);
* check -- a check after which the checking piece cannot be captured;
* pin -- a pin: after the move an opponent piece is pinned (absolutely or to the queen);
* safe -- a piece under attack: the only square where it cannot be captured;
* escape -- the opponent threatens mate in 1 (with a piece of the given kind): the only move that saves;
* mate1 -- mate in 1 with the given piece;
* mate2 -- mate in 2: the only first move, after any reply -- mate.

Levels 1-3 -- how many pieces and distracting targets are on the board. The solution is checked by brute force: the generator
accepts a position
only if there is exactly one correct answer (``solutions``); an exercise is defined by (kind, piece, level, seed) -- the
server does not
store positions and can restore the exercise at any moment to check an answer. The solver's colour changes with the seed.

The module is pure: no database, no Redis, no engine -- only python-chess and a random number generator with a given seed.
The position is first built "for White", then by seed it may be mirrored. Serving, answer checking and runs
are handled by src/services/generated_drills.py; verified seeds are collected by scripts/dev/build_drill_seeds.py.
"""

import random
from dataclasses import dataclass

import chess

KINDS = ("capture", "fork", "check", "pin", "safe", "escape", "mate1", "mate2")
PIECES = ("q", "r", "b", "n", "x")  # x -- a random piece
LEVELS = (1, 2, 3)
PIECE_TYPES = {"q": chess.QUEEN, "r": chess.ROOK, "b": chess.BISHOP, "n": chess.KNIGHT}
# Long-range pieces: only they can pin.
SLIDERS = (chess.QUEEN, chess.ROOK, chess.BISHOP)
# Piece values for the comparison "the target is worth more than the attacker" (fork, pin).
VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}
# How many opponent pieces (besides the king) and pawns to place at a level: (from, to) inclusive.
LEVEL_ENEMIES = {1: (1, 2), 2: (2, 3), 3: (3, 5)}
LEVEL_PAWNS = {1: (0, 0), 2: (0, 2), 3: (1, 3)}
# How many neighbouring seeds in a row generate tries before giving up (DrillGenerationError).
MAX_ATTEMPTS = 4000


class DrillGenerationError(Exception):
    """Could not find a position with a single answer within the allotted number of attempts."""


@dataclass(frozen=True)
class Drill:
    """
    A generator exercise: kind, piece, level, seed, position and the correct move. key is "kind.piece.level.seed": the
    server uses it to restore the exercise when checking an answer.
    """
    kind: str
    piece: str      # as in the request: q/r/b/n or x (random); x is not replaced: it is part of the key and the seed
    level: int
    seed: int       # the seed on which the position was found (the exercise is restored from it)
    fen: str
    solutions: tuple[str, ...]  # the single correct move (mate2 -- the first move)

    @property
    def key(self) -> str:
        return f"{self.kind}.{self.piece}.{self.level}.{self.seed}"


def supported(kind: str, piece: str) -> bool:
    """A knight does not pin; everything else is in the matrix."""
    return kind in KINDS and piece in PIECES and not (kind == "pin" and piece == "n")


# --- criteria (for the side to move) -------------------------------------------------------------------------

def _at(board: chess.Board, square: chess.Square) -> chess.Piece:
    """A piece on a square where it is certainly present (the move square, the solver's piece square)."""
    piece = board.piece_at(square)
    assert piece is not None
    return piece


def _at_king(board: chess.Board) -> chess.Square:
    """The opponent's king square (in the setup the opponent is Black)."""
    king = board.king(chess.BLACK)
    assert king is not None
    return king


def _value(piece: chess.Piece) -> int:
    return VALUES[piece.piece_type]


def _safe_after(board: chess.Board, move: chess.Move) -> bool:
    """After the move the opponent cannot capture the piece on the destination square."""
    after = board.copy(stack=False)
    after.push(move)
    return not after.is_attacked_by(after.turn, move.to_square)


def _targets(board: chess.Board, square: chess.Square, us: chess.Color) -> int:
    """How many targets the piece on square attacks: the king, an undefended or more valuable opponent piece."""
    attacker = _at(board, square)
    count = 0
    for target in board.attacks(square):
        victim = board.piece_at(target)
        if victim is None or victim.color == us:
            continue
        if (victim.piece_type == chess.KING or not board.is_attacked_by(not us, target)
                or _value(victim) > _value(attacker)):
            count += 1
    return count


def _capture_moves(board: chess.Board) -> list[chess.Move]:
    """Captures of opponent pieces that nobody defends."""
    us = board.turn
    result = []
    for move in board.legal_moves:
        victim = board.piece_at(move.to_square)
        if victim is None or victim.color == us or victim.piece_type == chess.KING:
            continue
        if not board.is_attacked_by(not us, move.to_square):  # the opponent's piece is undefended
            result.append(move)
    return result


def _fork_moves(board: chess.Board) -> list[chess.Move]:
    """
    Forks: a move by a piece (not a king or pawn) to a square where it cannot be captured and from which it attacks at least
    two targets.
    """
    us = board.turn
    result = []
    for move in board.legal_moves:
        if _at(board, move.from_square).piece_type in (chess.KING, chess.PAWN) or not _safe_after(board, move):
            continue
        after = board.copy(stack=False)
        after.push(move)
        if _targets(after, move.to_square, us) >= 2:
            result.append(move)
    return result


def _check_moves(board: chess.Board) -> list[chess.Move]:
    return [m for m in board.legal_moves if board.gives_check(m) and _safe_after(board, m)]


def _pin_moves(board: chess.Board) -> list[chess.Move]:
    """
    Pins: a move by a long-range piece without check to a square where it cannot be captured, after which it pins a piece.
    """
    them = not board.turn
    result = []
    for move in board.legal_moves:
        mover = _at(board, move.from_square)
        if mover.piece_type not in SLIDERS or not _safe_after(board, move) or board.gives_check(move):
            continue
        after = board.copy(stack=False)
        after.push(move)
        if any(_pinned_by(after, sq, move.to_square, them) for sq in chess.SquareSet(after.occupied_co[them])):
            result.append(move)
    return result


def _pinned_by(board: chess.Board, square: chess.Square, pinner: chess.Square, color: chess.Color) -> bool:
    """The opponent piece on square is pinned by the piece on the square pinner: to the king or to the queen behind it."""
    piece = board.piece_at(square)
    if piece is None or piece.piece_type in (chess.KING, chess.QUEEN):
        return False
    if board.is_pinned(color, square) and pinner in board.pin(color, square):
        return True
    # Relative pin: behind the piece on the same line is the opponent's queen.
    between = chess.SquareSet.between(pinner, square)
    if between & board.occupied:
        return False
    if square not in board.attacks(pinner):
        return False
    ray = chess.SquareSet.ray(pinner, square)
    beyond = [sq for sq in ray if chess.square_distance(pinner, sq) > chess.square_distance(pinner, square)
              and not (chess.SquareSet.between(square, sq) & board.occupied)]
    for sq in beyond:
        behind = board.piece_at(sq)
        if behind is not None:
            return behind.color == color and behind.piece_type == chess.QUEEN and _value(piece) < 9
    return False


def _safe_moves(board: chess.Board, square: chess.Square) -> list[chess.Move]:
    return [m for m in board.legal_moves if m.from_square == square and _safe_after(board, m)]


def _has_mate_in_one(board: chess.Board) -> chess.Move | None:
    for move in board.legal_moves:
        board.push(move)
        mate = board.is_checkmate()
        board.pop()
        if mate:
            return move
    return None


def _mate_moves(board: chess.Board) -> list[chess.Move]:
    result = []
    for move in board.legal_moves:
        board.push(move)
        if board.is_checkmate():
            result.append(move)
        board.pop()
    return result


def _escape_moves(board: chess.Board) -> list[chess.Move]:
    """Moves after which the opponent has no mate in one move."""
    result = []
    for move in board.legal_moves:
        board.push(move)
        if _has_mate_in_one(board) is None:
            result.append(move)
        board.pop()
    return result


def _mate_in_two_moves(board: chess.Board) -> list[chess.Move]:
    """
    First moves of mate in two: the move neither mates by itself nor gives stalemate, and for every opponent reply there is a
    mate in one.
    Mate in one move is not included -- that is another exercise kind.
    """
    result = []
    for move in board.legal_moves:
        board.push(move)
        forced = not board.is_checkmate() and not board.is_stalemate() and board.legal_moves.count() > 0
        if forced:
            for reply in board.legal_moves:
                board.push(reply)
                ok = _has_mate_in_one(board) is not None
                board.pop()
                if not ok:
                    forced = False
                    break
        board.pop()
        if forced:
            result.append(move)
    return result


def mate_reply(board: chess.Board, first: chess.Move) -> chess.Move:
    """
    The opponent's reply after the first move in mate in 2: the most "stubborn" -- after which there are the fewest mates.
    """
    after = board.copy(stack=False)
    after.push(first)

    def mates_left(reply: chess.Move) -> tuple[int, str]:
        probe = after.copy(stack=False)
        probe.push(reply)
        return len(_mate_moves(probe)), reply.uci()

    return min(after.legal_moves, key=mates_left)


def solutions_for(kind: str, board: chess.Board, key_square: chess.Square | None = None) -> list[chess.Move]:
    """
    All replies that count by the kind's rule (an exercise is correct if there is one answer). key_square is needed
    only by the kind safe: it is the square of the piece that must be moved out of attack.
    """
    if kind == "capture":
        return _capture_moves(board)
    if kind == "fork":
        return _fork_moves(board)
    if kind == "check":
        return _check_moves(board)
    if kind == "pin":
        return _pin_moves(board)
    if kind == "safe":
        return _safe_moves(board, key_square) if key_square is not None else []
    if kind == "escape":
        return _escape_moves(board)
    if kind == "mate1":
        return _mate_moves(board)
    if kind == "mate2":
        return _mate_in_two_moves(board)
    raise ValueError(kind)


# --- placement ---------------------------------------------------------------------------------------------

def _random_square(rng: random.Random, board: chess.Board, *, ranks: range = range(8)) -> chess.Square:
    while True:
        square = chess.square(rng.randrange(8), rng.choice(list(ranks)))
        if board.piece_at(square) is None:
            return square


def _place_kings(rng: random.Random, board: chess.Board, *, edge_enemy: bool = False) -> tuple[chess.Square, chess.Square]:
    """
    Places the kings not next to each other and returns their squares (ours, the opponent's). edge_enemy -- the opponent's
    king on
    the edge of the board (the last rank or the edge file on its half): this is how mate exercises are built.
    """
    ours = _random_square(rng, board)
    board.set_piece_at(ours, chess.Piece(chess.KING, chess.WHITE))
    while True:
        if edge_enemy:
            file, rank = rng.choice([(rng.randrange(8), 7), (rng.choice((0, 7)), rng.randrange(4, 8))])
            theirs = chess.square(file, rank)
        else:
            theirs = _random_square(rng, board)
        if board.piece_at(theirs) is None and chess.square_distance(ours, theirs) > 1:
            board.set_piece_at(theirs, chess.Piece(chess.KING, chess.BLACK))
            return ours, theirs


def _place(rng: random.Random, board: chess.Board, piece: chess.Piece) -> chess.Square:
    ranks = range(1, 7) if piece.piece_type == chess.PAWN else range(8)
    square = _random_square(rng, board, ranks=ranks)
    board.set_piece_at(square, piece)
    return square


def _enemy_types(rng: random.Random, count: int) -> list[chess.PieceType]:
    return [rng.choice((chess.QUEEN, chess.ROOK, chess.ROOK, chess.BISHOP, chess.BISHOP, chess.KNIGHT, chess.KNIGHT))
            for _ in range(count)]


def _arrange(kind: str, piece_type: chess.PieceType, level: int, rng: random.Random) -> tuple[chess.Board, chess.Square]:
    """
    A random placement for a kind: our king and a piece piece_type, the opponent's king and pieces. White moves.
    Returns the board and the square of our piece piece_type (in escape the kind's piece belongs to the opponent, and the
    square is unused).
    Whether the placement is suitable as an exercise is decided by _accept.
    """
    board = chess.Board(None)
    board.turn = chess.WHITE
    enemies = rng.randint(*LEVEL_ENEMIES[level])
    pawns = rng.randint(*LEVEL_PAWNS[level])
    mating = kind in ("mate1", "mate2")
    _place_kings(rng, board, edge_enemy=mating)
    if kind == "escape":
        # Our king on the edge behind its own pawns (as in a game), the mate threat comes from the opponent's piece of kind
        # piece_type.
        board = chess.Board(None)
        board.turn = chess.WHITE
        file = rng.randrange(8)
        king = chess.square(file, 0)
        board.set_piece_at(king, chess.Piece(chess.KING, chess.WHITE))
        for df in (-1, 0, 1):
            if 0 <= file + df < 8 and rng.random() < 0.8:
                board.set_piece_at(chess.square(file + df, 1), chess.Piece(chess.PAWN, chess.WHITE))
        while True:
            theirs = _random_square(rng, board, ranks=range(4, 8))
            if chess.square_distance(king, theirs) > 1:
                board.set_piece_at(theirs, chess.Piece(chess.KING, chess.BLACK))
                break
        board.set_piece_at(_random_square(rng, board, ranks=range(2, 8)), chess.Piece(piece_type, chess.BLACK))
        if piece_type in (chess.BISHOP, chess.KNIGHT):
            enemies = max(enemies, 3)  # a light piece mates only with helpers
        for t in _enemy_types(rng, enemies - 1):
            _place(rng, board, chess.Piece(t, rng.choice((chess.WHITE, chess.BLACK))))
        for _ in range(pawns):
            _place(rng, board, chess.Piece(chess.PAWN, chess.BLACK))
        return board, chess.square(0, 0)
    key = _place(rng, board, chess.Piece(piece_type, chess.WHITE))
    if mating and piece_type in (chess.BISHOP, chess.KNIGHT):
        # Mate with a light piece -- only for a king hemmed in by its own pieces (like a smothered mate): we place them
        # adjacent.
        theirs = _at_king(board)
        around = [sq for sq in chess.SquareSet(chess.BB_KING_ATTACKS[theirs]) if board.piece_at(sq) is None]
        rng.shuffle(around)
        for sq in around[:rng.randint(2, 4)]:
            rank = chess.square_rank(sq)
            blocker = (chess.PAWN if 0 < rank < 7 and rng.random() < 0.6
                       else rng.choice((chess.ROOK, chess.BISHOP, chess.KNIGHT)))
            board.set_piece_at(sq, chess.Piece(blocker, chess.BLACK))
        _place(rng, board, chess.Piece(rng.choice((chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.QUEEN)), chess.WHITE))
        enemies = 0
    if mating:
        enemies = max(0, enemies - 1)
        if kind == "mate2" or level > 1:
            _place(rng, board, chess.Piece(rng.choice((chess.ROOK, chess.BISHOP, chess.KNIGHT)), chess.WHITE))
    for t in _enemy_types(rng, enemies):
        _place(rng, board, chess.Piece(t, chess.BLACK))
    for _ in range(pawns):
        _place(rng, board, chess.Piece(chess.PAWN, rng.choice((chess.WHITE, chess.BLACK))))
    return board, key


def _valid(board: chess.Board) -> bool:
    """The position is possible by the rules, the solver is not in check and the game is not over."""
    return board.is_valid() and not board.is_check() and not board.is_game_over()


def _accept(kind: str, board: chess.Board, key: chess.Square, piece_type: chess.PieceType) -> chess.Move | None:
    """
    The correct answer, if it is the only one and made by the required piece (for escape -- the threat is created by a piece
    of the kind).
    """
    if kind == "safe" and not board.is_attacked_by(not board.turn, key):
        return None
    if kind == "escape":
        threat = board.copy(stack=False)
        threat.push(chess.Move.null())
        mate = _has_mate_in_one(threat)
        if mate is None or _at(threat, mate.from_square).piece_type != piece_type:
            return None
    moves = solutions_for(kind, board, key)
    if len(moves) != 1:
        return None
    move = moves[0]
    if kind != "escape" and _at(board, move.from_square).piece_type != piece_type:
        return None
    return move


def generate(kind: str, piece: str, level: int, seed: int) -> Drill:
    """
    An exercise by seed: the first attempts from seed in order -- deterministic; the seed in the answer is the one found. It
    tries
    seed, seed + 1, ... (at most MAX_ATTEMPTS); if none gave a position with a single answer --
    DrillGenerationError. An unknown combination of kind, piece and level -- ValueError.
    """
    if not supported(kind, piece) or level not in LEVELS:
        raise ValueError(f"unsupported drill {kind}/{piece}/{level}")
    for attempt in range(MAX_ATTEMPTS):
        current = seed + attempt
        drill = build(kind, piece, level, current)
        if drill is not None:
            return drill
    raise DrillGenerationError(f"{kind}/{piece}/{level} from seed {seed}")


def build(kind: str, piece: str, level: int, seed: int) -> Drill | None:
    """
    One attempt: placement by seed and a check; None -- the position is unsuitable. The random number generator is seeded
    with the string "kind:piece:level:seed", so the same parameters always give the same position.
    """
    rng = random.Random(f"{kind}:{piece}:{level}:{seed}")
    actual = rng.choice("qrbn") if piece == "x" else piece
    if kind == "pin" and actual == "n":
        actual = rng.choice("qrb")
    board, key = _arrange(kind, PIECE_TYPES[actual], level, rng)
    if not _valid(board):
        return None
    move = _accept(kind, board, key, PIECE_TYPES[actual])
    if move is None:
        return None
    if rng.random() < 0.5:  # for Black -- mirrored
        board = board.mirror()
        move = chess.Move(chess.square_mirror(move.from_square), chess.square_mirror(move.to_square), move.promotion)
    return Drill(kind=kind, piece=piece, level=level, seed=seed, fen=board.fen(), solutions=(move.uci(),))


def restore(key: str) -> Drill:
    """
    An exercise by the key "kind.piece.level.seed" (the key is issued by the server -- the seed in it is already the one
    found).
    """
    try:
        kind, piece, level, seed = key.split(".")
        drill = build(kind, piece, int(level), int(seed))
    except (ValueError, KeyError):
        drill = None
    if drill is None:
        raise ValueError(f"invalid drill key {key}")
    return drill
