# --- FILE: src/services/coach.py ---
"""
The coach in words (task 11.2): from the facts of the motif detector (src/services/mentor_service.py) and the engine line
an explanation of a move is built — what is wrong with the move, what is now threatened, what the idea of the best move is —
together with arrows for
the board.

The server writes no text: the explanation is a list of sentences ``{"key", "params"}``, the keys are templates of the
``coach`` catalog on the client (three languages). Each template has several wordings (``.v1``, ``.v2``); which one to take is
decided by the position, not by chance, so the same analysis always reads the same way.

Pieces and squares in parameters use figurine notation ("♘f7", "♕d8"), as in chess literature: it reads the same
in any language and does not require declining piece names.

The detector's main principle stands: a false explanation is worse than silence. A motif is named as the cause of a mistake
only if the opponent's best reply by the engine confirms it (a fork — by capturing one of the targets, a hanging
piece — by capturing it; a mate found by the detector needs no confirmation). If there is no confirmation, the coach says
only what it is sure of: the evaluation of the move and the best move.

Callers: game analysis (analysis_service.attach_coach_comments → comment_for_move) and the in-game coach
(src/services/move_check.py → advice_for_position, hint_for_position). The best move and the opponent's reply come from
the engine outside; the module itself does not call the engine and does not touch the database.
"""

import zlib
from collections.abc import Iterable

import chess

from src.services.mentor_service import PIECE_VALUE, Motif, analyze_move, detect_motifs
from src.services.positional import move_idea, positional_features

# Wordings per template: keys "coach.<group>.<code>.v1" … ".vN".
VARIANTS = 2

# Piece signs for sentence parameters: by piece colour and kind.
FIGURINES = {
    chess.WHITE: {chess.KING: "♔", chess.QUEEN: "♕", chess.ROOK: "♖", chess.BISHOP: "♗", chess.KNIGHT: "♘", chess.PAWN: "♙"},
    chess.BLACK: {chess.KING: "♚", chess.QUEEN: "♛", chess.ROOK: "♜", chess.BISHOP: "♝", chess.KNIGHT: "♞", chess.PAWN: "♟"},
}

# Templates and their parameters: (group, code) → parameter names. The client catalogs must have exactly these keys
# with exactly these parameters (tests/test_coach.py).
TEMPLATES: dict[tuple[str, str], tuple[str, ...]] = {
    # Evaluation of the move made — the first sentence of a comment on an inaccuracy, mistake, blunder.
    ("verdict", "inaccuracy"): ("move",),
    ("verdict", "mistake"): ("move",),
    ("verdict", "blunder"): ("move",),
    # Threat: one side's tactic against the other. In a move comment — what the erroneous move allowed the opponent
    # (threatens the side that moved); in advice — what the opponent threatens the player who is on move now.
    ("threat", "mate_in"): ("n", "move"),
    ("threat", "mate_threat"): ("piece", "square"),
    ("threat", "hanging"): ("piece",),
    ("threat", "fork"): ("attacker", "target1", "target2"),
    ("threat", "skewer"): ("attacker", "front", "behind"),
    ("threat", "pin_absolute"): ("attacker", "front", "behind"),
    ("threat", "pin_relative"): ("attacker", "front", "behind"),
    ("threat", "trapped"): ("piece",),
    ("threat", "overloaded"): ("defender", "target1", "target2"),
    ("threat", "back_rank"): ("king", "square"),
    # Missed opportunity: it existed before the move and is gone.
    ("missed", "mate_in"): ("n", "move"),
    ("missed", "hanging"): ("piece",),
    # The idea of the best move.
    ("best", "mate"): ("move",),
    ("best", "fork"): ("move", "attacker", "target1", "target2"),
    ("best", "skewer"): ("move", "attacker", "front", "behind"),
    ("best", "pin_absolute"): ("move", "attacker", "front", "behind"),
    ("best", "pin_relative"): ("move", "attacker", "front", "behind"),
    ("best", "discovered_attack"): ("move", "attacker", "target"),
    ("best", "discovered_check"): ("move", "attacker"),
    ("best", "double_check"): ("move",),
    ("best", "mate_threat"): ("move", "piece", "square"),
    ("best", "trapped"): ("move", "piece"),
    ("best", "capture"): ("move", "piece"),
    ("best", "generic"): ("move",),
    # Positional idea of the best move when there is no tactic (task B.4, src/services/positional.py).
    ("best", "pos_castle"): ("move",),
    ("best", "pos_open_file"): ("move", "file"),
    ("best", "pos_outpost"): ("move", "square"),
    ("best", "pos_king_active"): ("move",),
    ("best", "pos_passed_push"): ("move",),
    # A good move with a tactic.
    ("good", "checkmate"): ("move",),
    ("good", "fork"): ("attacker", "target1", "target2"),
    ("good", "skewer"): ("attacker", "front", "behind"),
    ("good", "pin_absolute"): ("attacker", "front", "behind"),
    ("good", "pin_relative"): ("attacker", "front", "behind"),
    ("good", "discovered_attack"): ("attacker", "target"),
    ("good", "discovered_check"): ("attacker",),
    ("good", "double_check"): ("move",),
    ("good", "mate_threat"): ("piece", "square"),
    ("good", "trapped"): ("piece",),
    # Advice on a position (POST /analysis/advice).
    ("advice", "chance_mate"): ("n", "move"),
    ("advice", "chance_capture"): ("piece",),
    ("advice", "quiet"): (),
    # Positional features when there are no threats (task B.4).
    ("advice", "pos_king_center"): (),
    ("advice", "pos_king_holes"): ("square",),
    ("advice", "pos_passed_enemy"): ("square",),
    ("advice", "pos_passed_own"): ("square",),
    ("advice", "pos_king_active"): (),
    ("advice", "pos_open_file"): ("file",),
    ("advice", "pos_outpost"): ("square",),
    ("advice", "pos_isolated_enemy"): ("square",),
    ("advice", "pos_backward_enemy"): ("square",),
    ("advice", "pos_bad_bishop"): ("square",),
    ("advice", "pos_doubled_own"): ("file",),
    # Tiered hint (task 11.4). Step 1 — a nudge without squares and pieces, step 2 — which piece to move.
    ("hint", "mate"): ("n",),
    ("hint", "fork"): (),
    ("hint", "skewer"): (),
    ("hint", "pin_absolute"): (),
    ("hint", "pin_relative"): (),
    ("hint", "discovered_attack"): (),
    ("hint", "discovered_check"): (),
    ("hint", "double_check"): (),
    ("hint", "mate_threat"): (),
    ("hint", "trapped"): (),
    ("hint", "capture"): (),
    ("hint", "defend"): (),
    ("hint", "quiet"): (),
    # Step 1 in a quiet position — a positional idea without squares and pieces (task B.4).
    ("hint", "pos_castle"): (),
    ("hint", "pos_open_file"): (),
    ("hint", "pos_outpost"): (),
    ("hint", "pos_king_active"): (),
    ("hint", "pos_passed_push"): (),
    ("hint", "piece"): ("piece",),
}

# Move classes from the analysis (analysis_service.classify_move_by_cp_loss): bad ones — with an evaluation template code, good
# ones —
# are commented only if the move created a tactic.
BAD_CLASSIFICATIONS = {"Inaccuracy": "inaccuracy", "Mistake": "mistake", "Blunder": "blunder"}
GOOD_CLASSIFICATIONS = {"Best", "Good"}

# Which threat to name first if the move allowed several: from the most dangerous.
THREAT_PRIORITY = (
    "mate_in", "mate_threat", "fork", "skewer", "trapped", "hanging", "pin_absolute", "overloaded",
    "back_rank", "pin_relative",
)
# Idea of the best / a good move: from the strongest.
IDEA_PRIORITY = (
    "double_check", "discovered_check", "fork", "skewer", "mate_threat", "trapped", "discovered_attack",
    "pin_absolute", "pin_relative",
)


def all_message_keys() -> dict[str, tuple[str, ...]]:
    """All catalog keys the coach can emit, with their parameters."""
    return {
        f"coach.{group}.{code}.v{variant}": params
        for (group, code), params in TEMPLATES.items()
        for variant in range(1, VARIANTS + 1)
    }


def _sentence(group: str, code: str, seed: str, **params: str | int) -> dict:
    """
    One sentence of the explanation: a template key with a wording number and parameters. The wording is chosen by a checksum
    of seed (the position FEN) and the template code — for one position it is always the same. Parameters that do not match
    those declared in TEMPLATES raise KeyError: this is a bug in the code, not in the data.
    """
    expected = TEMPLATES[(group, code)]
    if set(params) != set(expected):
        raise KeyError(f"coach.{group}.{code}: params {sorted(params)} != {sorted(expected)}")
    variant = zlib.crc32(f"{seed}|{group}.{code}".encode()) % VARIANTS + 1
    return {"key": f"coach.{group}.{code}.v{variant}", "params": params}


def _arrow(from_square: chess.Square, to_square: chess.Square, kind: str) -> dict:
    """An arrow for the client board; kind is "best" (best move), "threat" (threat) or "idea" (move idea)."""
    return {"from": chess.square_name(from_square), "to": chess.square_name(to_square), "kind": kind}


def piece_label(board: chess.Board, square: chess.Square) -> str:
    """'♘f7' — a piece on a square in figurine notation (an empty square is just the square name)."""
    piece = board.piece_at(square)
    name = chess.square_name(square)
    return f"{FIGURINES[piece.color][piece.piece_type]}{name}" if piece else name


def figurine_san(board: chess.Board, move: chess.Move) -> str:
    """SAN of a move with figurines instead of letters (Nf3 → ♘f3, e8=Q → e8=♕)."""
    san = board.san(move)
    figurines = FIGURINES[board.turn]
    letters = {"K": chess.KING, "Q": chess.QUEEN, "R": chess.ROOK, "B": chess.BISHOP, "N": chess.KNIGHT}
    if san[0] in letters:
        san = figurines[letters[san[0]]] + san[1:]
    if "=" in san:
        head, tail = san.split("=", 1)
        san = f"{head}={figurines[letters[tail[0]]]}{tail[1:]}"
    return san


def _move_from_motif(board: chess.Board, motif: Motif) -> chess.Move | None:
    """The move from a mate motif (the from square and the to square), if it is legal in this position."""
    if not motif.targets:
        return None
    for move in board.legal_moves:
        if move.from_square == motif.square and move.to_square == motif.targets[0]:
            return move
    return None


def _caused_by(motif: Motif, move: chess.Move, board_after: chess.Board) -> bool:
    """
    The motif was created by this very move: it is led by the piece that moved, or the move opened a line for a long-range
    piece (moved away
    from the line between it and the target), or it is a discovered attack by definition. A motif that arose in the position
    "by itself" (the king
    moved away, and a pin formed somewhere on the board) is not considered the move's idea.
    """
    if motif.code in ("discovered_attack", "discovered_check", "double_check"):
        return True
    if motif.code == "trapped":
        return motif.square in board_after.attacks(move.to_square)
    if motif.square == move.to_square:
        return True
    target = motif.targets[0] if motif.targets else None
    return target is not None and move.from_square in chess.SquareSet(chess.between(motif.square, target))


def _material_lost(motif: Motif, played: chess.Move, board_before: chess.Board) -> bool:
    """
    An unprotected piece is a real loss, not a trade: if the move itself captured a piece on this square, the opponent
    wins it back not at a gain as long as what was taken is not less than what he wins by the capture.
    """
    if motif.square != played.to_square or not board_before.is_capture(played):
        return True
    captured = board_before.piece_at(played.to_square)
    captured_value = PIECE_VALUE[captured.piece_type] if captured else PIECE_VALUE[chess.PAWN]  # en passant
    return (motif.value or 0) > captured_value


def _first(motifs: Iterable[Motif], priority: tuple[str, ...]) -> list[Motif]:
    """Motifs whose codes are in the priority list, in the order of this list; the others are discarded."""
    ranked = [m for m in motifs if m.code in priority]
    return sorted(ranked, key=lambda m: priority.index(m.code))


# --- description of motifs ------------------------------------------------------------------------------------

def _tactic_params(board: chess.Board, motif: Motif) -> dict[str, str]:
    """Parameters of the templates for a fork, pin, skewer, overload, discovered attack (for the position ``board``)."""
    code = motif.code
    if code == "fork":
        return {
            "attacker": piece_label(board, motif.square),
            "target1": piece_label(board, motif.targets[0]),
            "target2": piece_label(board, motif.targets[1]),
        }
    if code in ("skewer", "pin_absolute", "pin_relative"):
        return {
            "attacker": piece_label(board, motif.square),
            "front": piece_label(board, motif.targets[0]),
            "behind": piece_label(board, motif.targets[1]),
        }
    if code == "overloaded":
        return {
            "defender": piece_label(board, motif.square),
            "target1": piece_label(board, motif.targets[0]),
            "target2": piece_label(board, motif.targets[1]),
        }
    if code == "discovered_attack":
        return {"attacker": piece_label(board, motif.square), "target": piece_label(board, motif.targets[0])}
    if code == "discovered_check":
        return {"attacker": piece_label(board, motif.square)}
    if code == "mate_threat":
        return {"piece": piece_label(board, motif.square), "square": chess.square_name(motif.targets[0])}
    if code == "trapped":
        return {"piece": piece_label(board, motif.square)}
    return {}


def _tactic_arrows(motif: Motif, kind: str) -> tuple[list[dict], list[dict]]:
    """Arrows "who attacks → what" and highlighting of targets."""
    arrows: list[dict] = []
    highlights: list[dict] = []
    code = motif.code
    if code in ("fork", "discovered_attack"):
        arrows = [_arrow(motif.square, target, kind) for target in motif.targets[:2]]
        highlights = [{"square": chess.square_name(t), "kind": "target"} for t in motif.targets[:2]]
    elif code in ("skewer", "pin_absolute", "pin_relative"):
        arrows = [_arrow(motif.square, motif.targets[1], kind)]
        highlights = [{"square": chess.square_name(t), "kind": "target"} for t in motif.targets[:2]]
    elif code == "overloaded":
        highlights = [{"square": chess.square_name(motif.square), "kind": "target"}]
        highlights += [{"square": chess.square_name(t), "kind": "target"} for t in motif.targets[:2]]
    elif code in ("mate_threat", "mate_in"):
        arrows = [_arrow(motif.square, motif.targets[0], kind)]
    elif code == "discovered_check":
        if motif.targets:
            arrows = [_arrow(motif.square, motif.targets[0], kind)]
    elif code == "trapped":
        highlights = [{"square": chess.square_name(motif.square), "kind": "target"}]
    return arrows, highlights


# --- what is threatened --------------------------------------------------------------------------------------------

def _confirmed_by_reply(motif: Motif, reply: chess.Move | None) -> bool:
    """
    Whether the opponent's best reply confirms that the motif is the real cause: the reply uses exactly it.
    Without an engine reply (no evaluation) there is no confirmation — only mate, which needs none.
    """
    if motif.code == "mate_in":
        return True
    if reply is None:
        return False
    to = reply.to_square
    if motif.code == "hanging":
        return to == motif.square
    if motif.code in ("fork", "overloaded", "skewer"):
        return to in motif.targets
    if motif.code in ("pin_absolute", "pin_relative"):
        return to == motif.targets[0]
    if motif.code == "trapped":
        return to == motif.square
    if motif.code == "back_rank":
        return to in motif.targets
    return False


def _threat_sentence(board: chess.Board, motif: Motif, seed: str) -> tuple[dict, list[dict], list[dict]]:
    """
    The "what is threatened" sentence, its arrows and highlighting: a motif in favour of ``motif.color`` against the other
    side. In a
    move comment ``motif.color`` is the side that is on move in ``board`` (the position after the move); in advice — the side
    that is not on move (mate does not get here in advice).
    """
    code = motif.code
    if code == "mate_in":
        move = _move_from_motif(board, motif)
        sentence = _sentence("threat", "mate_in", seed, n=int(motif.value or 1),
                             move=figurine_san(board, move) if move else chess.square_name(motif.targets[0]))
        return sentence, [_arrow(motif.square, motif.targets[0], "threat")], []
    if code == "hanging":
        arrows = [_arrow(attacker, motif.square, "threat") for attacker in motif.targets[:1]]
        return (_sentence("threat", "hanging", seed, piece=piece_label(board, motif.square)), arrows,
                [{"square": chess.square_name(motif.square), "kind": "target"}])
    if code == "back_rank":
        king = motif.square
        return (_sentence("threat", "back_rank", seed, king=piece_label(board, king),
                          square=chess.square_name(motif.targets[0])), [],
                [{"square": chess.square_name(motif.targets[0]), "kind": "target"}])
    arrows, highlights = _tactic_arrows(motif, "threat")
    return _sentence("threat", code, seed, **_tactic_params(board, motif)), arrows, highlights


# --- comment on a game move --------------------------------------------------------------------------------

def _idea_of(board_before: chess.Board, move: chess.Move, before_motifs: list[Motif]) -> Motif | None:
    """The strongest tactic created by the move itself (one that did not exist before it)."""
    board_after = board_before.copy(stack=False)
    board_after.push(move)
    facts = analyze_move(board_before, move, before_motifs=before_motifs)
    ideas = [m for m in _first(facts.created, IDEA_PRIORITY) if _caused_by(m, move, board_after)]
    return ideas[0] if ideas else None


def _best_idea(board_before: chess.Board, best: chess.Move, seed: str,
               before_motifs: list[Motif]) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Sentences about what was missed and about the best move, arrows and highlighting. Selection order: the best move mates; a
    missed
    mate or an unprotected piece that the best move captures; a tactic created by the best move; otherwise — a capture,
    a positional idea (positional.move_idea) or a general phrase.
    """
    mover = board_before.turn
    sentences: list[dict] = []
    arrows = [_arrow(best.from_square, best.to_square, "best")]
    highlights: list[dict] = []
    move = figurine_san(board_before, best)

    board_after = board_before.copy(stack=False)
    board_after.push(best)
    if board_after.is_checkmate():
        return [_sentence("best", "mate", seed, move=move)], arrows, highlights

    # Missed: a mate or an unprotected piece that the best move uses.
    for motif in before_motifs:
        if motif.color != mover:
            continue
        if motif.code == "mate_in" and best.from_square == motif.square:
            return [_sentence("missed", "mate_in", seed, n=int(motif.value or 1), move=move)], arrows, highlights
        if motif.code == "hanging" and best.to_square == motif.square:
            sentences.append(_sentence("missed", "hanging", seed, piece=piece_label(board_before, motif.square)))
            highlights.append({"square": chess.square_name(motif.square), "kind": "target"})
            break

    idea = _idea_of(board_before, best, before_motifs)
    if idea is not None:
        params = _tactic_params(board_after, idea)
        if idea.code == "double_check":
            params = {}
        sentences.append(_sentence("best", idea.code, seed, move=move, **params))
        idea_arrows, idea_highlights = _tactic_arrows(idea, "idea")
        arrows += idea_arrows
        highlights += idea_highlights
    elif not sentences:
        if board_before.is_capture(best):
            captured = board_before.piece_at(best.to_square)
            label = piece_label(board_before, best.to_square) if captured else chess.square_name(best.to_square)
            sentences.append(_sentence("best", "capture", seed, move=move, piece=label))
        else:
            positional = move_idea(board_before, best)
            if positional is not None:
                sentences.append(_sentence("best", f"pos_{positional.code}", seed, move=move, **positional.params))
            else:
                sentences.append(_sentence("best", "generic", seed, move=move))
    return sentences, arrows, highlights


def comment_for_move(
        board_before: chess.Board,
        played: chess.Move,
        best_uci: str | None,
        reply_uci: str | None,
        classification: str,
) -> dict | None:
    """
    Coach comment on a game move: ``{"comment": [...], "arrows": [...], "highlights": [...]}`` or
    None if there is nothing to say (an ordinary well-played move). ``best_uci`` is the engine's best move in the position
    before the move,
    ``reply_uci`` — the opponent's best reply after the move made (the causes of the mistake are checked against it);
    ``classification`` — the move class from the analysis. A good move is commented only if it mates or creates
    a tactic; a bad one — with an evaluation, one confirmed threat and the idea of the best move.
    """
    if played not in board_before.legal_moves:
        return None
    seed = board_before.fen()
    move_label = figurine_san(board_before, played)
    before_motifs = detect_motifs(board_before)
    board_after = board_before.copy(stack=False)
    board_after.push(played)

    if classification in GOOD_CLASSIFICATIONS:
        if board_after.is_checkmate():
            return {"comment": [_sentence("good", "checkmate", seed, move=move_label)], "arrows": [], "highlights": []}
        facts = analyze_move(board_before, played, before_motifs=before_motifs)
        ideas = [m for m in _first(facts.created, IDEA_PRIORITY) if _caused_by(m, played, board_after)]
        if not ideas:
            return None
        idea = ideas[0]
        params = {"move": move_label} if idea.code == "double_check" else _tactic_params(board_after, idea)
        good_arrows, good_highlights = _tactic_arrows(idea, "idea")
        return {"comment": [_sentence("good", idea.code, seed, **params)],
                "arrows": good_arrows, "highlights": good_highlights}

    verdict = BAD_CLASSIFICATIONS.get(classification)
    if verdict is None:
        return None
    sentences = [_sentence("verdict", verdict, seed, move=move_label)]
    arrows: list[dict] = []
    highlights: list[dict] = []

    # What is threatened after the move — only what is confirmed by the engine's reply.
    reply = _legal(board_after, reply_uci)
    facts = analyze_move(board_before, played, before_motifs=before_motifs)
    for motif in _first(facts.allowed, THREAT_PRIORITY):
        if motif.code == "hanging" and not _material_lost(motif, played, board_before):
            continue
        if _confirmed_by_reply(motif, reply):
            sentence, threat_arrows, threat_highlights = _threat_sentence(board_after, motif, seed)
            sentences.append(sentence)
            arrows += threat_arrows
            highlights += threat_highlights
            break

    best = _legal(board_before, best_uci)
    if best is not None and best != played:
        idea_sentences, idea_arrows, idea_highlights = _best_idea(board_before, best, seed, before_motifs)
        sentences += idea_sentences
        arrows += idea_arrows
        highlights += idea_highlights
    return {"comment": sentences, "arrows": arrows, "highlights": highlights}


def _legal(board: chess.Board, uci: str | None) -> chess.Move | None:
    """The move from a UCI string if it is legal in the position; an empty, unreadable string or an illegal move — None."""
    if not uci:
        return None
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return None
    return move if move in board.legal_moves else None


# --- advice on a position ------------------------------------------------------------------------------------------

def advice_for_position(board: chess.Board, best_uci: str | None) -> dict:
    """
    Advice for the side to move: what threatens it (the opponent's tactic), what it has itself (mate, an unprotected
    opponent piece) and what the idea of the best move is. Without an engine — only the detector's facts.
    """
    seed = board.fen()
    mover = board.turn
    motifs = detect_motifs(board)
    sentences: list[dict] = []
    arrows: list[dict] = []
    highlights: list[dict] = []

    own = [m for m in motifs if m.color == mover]
    # There is a mate — nothing else needs to be said.
    mate = next((m for m in own if m.code == "mate_in"), None)
    if mate is not None:
        move = _move_from_motif(board, mate)
        if move is not None:
            return {
                "comment": [_sentence("advice", "chance_mate", seed, n=int(mate.value or 1),
                                      move=figurine_san(board, move))],
                "arrows": [_arrow(move.from_square, move.to_square, "best")],
                "highlights": [],
            }

    # What threatens the player: a tactic in the opponent's favour (if he were on move).
    threats = [m for m in motifs if m.color != mover and m.code != "mate_in"]
    for motif in _first(threats, THREAT_PRIORITY):
        sentence, threat_arrows, threat_highlights = _threat_sentence(board, motif, seed)
        sentences.append(sentence)
        arrows += threat_arrows
        highlights += threat_highlights
        break

    best = _legal(board, best_uci)

    if best is not None:
        idea_sentences, idea_arrows, idea_highlights = _best_idea(board, best, seed, motifs)
        sentences += idea_sentences
        arrows += idea_arrows
        highlights += idea_highlights
    else:
        loose = next((m for m in own if m.code == "hanging"), None)
        if loose is not None:
            sentences.append(_sentence("advice", "chance_capture", seed, piece=piece_label(board, loose.square)))
            highlights.append({"square": chess.square_name(loose.square), "kind": "target"})

    # No threats — one word about the position: what matters most in the structure (task B.4).
    if not any(m.color != mover and m.code != "mate_in" for m in motifs):
        features = positional_features(board, mover)
        if features:
            feature = features[0]
            sentences.append(_sentence("advice", f"pos_{feature.code}", seed, **feature.params))
            highlights += [{"square": chess.square_name(sq), "kind": "target"} for sq in feature.squares]

    if not sentences:
        sentences.append(_sentence("advice", "quiet", seed))
    return {"comment": sentences, "arrows": arrows, "highlights": highlights}


# Number of hint steps; a step number outside 1…HINT_STEPS is brought to the nearest bound.
HINT_STEPS = 3


def _nudge(board: chess.Board, best: chess.Move | None, motifs: list[Motif], seed: str) -> dict:
    """Step 1: the essence of the position, without naming squares and pieces."""
    mover = board.turn
    own = [m for m in motifs if m.color == mover]
    mate = next((m for m in own if m.code == "mate_in"), None)
    if best is not None:
        after = board.copy(stack=False)
        after.push(best)
        if after.is_checkmate():
            return _sentence("hint", "mate", seed, n=1)
        if mate is not None and best.from_square == mate.square:
            return _sentence("hint", "mate", seed, n=int(mate.value or 1))
        idea = _idea_of(board, best, motifs)
        if idea is not None:
            return _sentence("hint", idea.code, seed)
        if any(m.code == "hanging" and m.square == best.to_square for m in own):
            return _sentence("hint", "capture", seed)
    elif mate is not None:
        return _sentence("hint", "mate", seed, n=int(mate.value or 1))
    elif any(m.code == "hanging" for m in own):
        return _sentence("hint", "capture", seed)
    if any(m.color != mover and m.code != "mate_in" for m in motifs):
        return _sentence("hint", "defend", seed)
    positional = _positional_nudge(board, best)
    if positional is not None:
        return _sentence("hint", f"pos_{positional}", seed)
    return _sentence("hint", "quiet", seed)


# Position feature → the move idea for a nudge without an engine: what to think about if the best move is unknown.
_FEATURE_NUDGES = {
    "king_center": "castle", "open_file": "open_file", "outpost": "outpost", "king_active": "king_active",
    "passed_own": "passed_push",
}


def _positional_nudge(board: chess.Board, best: chess.Move | None) -> str | None:
    """
    Positional idea for step 1: with a best move — its idea (move_idea), without an engine — the main feature of the position,
    which has a move idea. Squares and pieces are not named.
    """
    if best is not None:
        idea = move_idea(board, best)
        return idea.code if idea is not None else None
    for feature in positional_features(board, board.turn):
        if feature.code in _FEATURE_NUDGES:
            return _FEATURE_NUDGES[feature.code]
    return None


def hint_for_position(board: chess.Board, best_uci: str | None, step: int) -> dict:
    """
    Tiered hint: 1 — a nudge in words (a theme), 2 — which piece to move (the square is highlighted), 3 — full advice with
    an arrow of the best move. Steps before the third do not reveal the move. Without a best move (no engine) the second step
    is impossible — straight to the full advice from the detector's facts.
    """
    step = max(1, min(HINT_STEPS, step))
    seed = board.fen()
    best = _legal(board, best_uci)
    if step == 1:
        return {"comment": [_nudge(board, best, detect_motifs(board), seed)], "arrows": [], "highlights": []}
    if step == 2 and best is not None:
        return {
            "comment": [_sentence("hint", "piece", seed, piece=piece_label(board, best.from_square))],
            "arrows": [],
            "highlights": [{"square": chess.square_name(best.from_square), "kind": "piece"}],
        }
    return advice_for_position(board, best_uci)
