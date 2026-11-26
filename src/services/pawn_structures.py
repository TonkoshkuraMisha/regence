"""
Pawn structures (task 27.5): detection by pawn placement - for library game tags, search for "games with
this structure" and future Supercourse modules (C3-C4, `docs/research/supercourse.md`).

The rules are from White's point of view; each rule is also checked on the mirrored position, so a structure is recognised for
either side (isolated, hanging, stonewall, Carlsbad and others). The order of checking matters: more specific
structures come before general ones (hedgehog is a special case of Maroczy, wedge of the King's Indian chain). The
structure of a game is the longest of those met between the 12th and 80th plies (at least 8 plies; plies are all counted,
not necessarily consecutive).

The rules look only at pawns and only at named squares: this is a tag for search, not a position evaluation.
Who calls it: game import into the library (src/services/library.py) and re-tagging scripts/tag_library.py - the structure
code is stored in library_games.structure; "Name the Structure" (src/services/structure_quiz.py) takes it from there.

The type of the centre (Big course module S2.5, center_type) is a separate, coarser rule on the d- and e-files only:
* closed - on both files a pawn of one side stands right in front of a pawn of the other (blocked chains: King's Indian,
  French); neither side can open the centre with these pawns;
* mobile - one side has pawns on d4 and e4 (d5 and e5 for Black), nothing stands in front of them and the opponent has no
  d-pawn: the pair can advance (Gruenfeld, Queen's Gambit Accepted lines);
* open - there are no pawns at all on the d- and e-files: the pieces fight along open lines.
Anything else (one blocked file, tension, a lone central pawn) has no type. scripts/dev/theme_games.py picks master games
for S2.5 with it.
"""

from collections import Counter
from collections.abc import Callable, Iterable

import chess

STRUCTURES = ("hedgehog", "maroczy", "wedge", "kid_chain", "modern_benoni", "stonewall", "saw", "french_chain",
              "french_exchange", "carlsbad", "hanging_pawns", "isolated_pawn", "spanish", "symmetry")
# The game window in which the structure is searched: before the 12th ply it has not formed yet, after the 80th it is
# already an endgame. MIN_PLIES - how many plies the structure must stand to become a game tag.
FIRST_PLY, LAST_PLY, MIN_PLIES = 12, 80, 8


class Pawns:
    """
    Pawns of the sides as sets of squares - for short structure checks: "own pawns on ...", "opponent pawns on ...", "on
    the file there are no own pawns".
    """
    def __init__(self, board: chess.Board, color: chess.Color):
        self.ours = {chess.square_name(s) for s in board.pieces(chess.PAWN, color)}
        self.theirs = {chess.square_name(s) for s in board.pieces(chess.PAWN, not color)}

    def has(self, *squares: str) -> bool:
        return all(s in self.ours for s in squares)

    def they(self, *squares: str) -> bool:
        return all(s in self.theirs for s in squares)

    def none_on(self, file: str) -> bool:
        return not any(s[0] == file for s in self.ours)

    def they_none_on(self, file: str) -> bool:
        return not any(s[0] == file for s in self.theirs)


def _hedgehog(p: Pawns) -> bool:
    """Hedgehog: c4 + e4 without a d-pawn against b6 + d6 + e6 and a6 (or a7), the opponent has no c-pawn."""
    return (p.has("c4", "e4") and p.none_on("d") and p.they("b6", "d6", "e6") and p.they_none_on("c")
            and (p.they("a6") or p.they("a7")))


def _maroczy(p: Pawns) -> bool:
    """Maroczy system: c4 + e4 without a d-pawn against d6 (or d7), the opponent has no c-pawn."""
    return p.has("c4", "e4") and p.none_on("d") and (p.they("d6") or p.they("d7")) and p.they_none_on("c")


def _kid_chain(p: Pawns) -> bool:
    """King's Indian chain: d5 + e4 against d6 + e5."""
    return p.has("d5", "e4") and p.they("d6", "e5")


def _wedge(p: Pawns) -> bool:
    """Wedge in the centre: d5 + e4 against c5 + d6 + e5 (a closed centre with locked pawn flanks)."""
    return p.has("d5", "e4") and p.they("c5", "d6", "e5")


def _modern_benoni(p: Pawns) -> bool:
    """Modern Benoni: d5 against c5 + d6, the opponent has no e-pawn."""
    return p.has("d5") and p.they("c5", "d6") and p.they_none_on("e")


def _saw(p: Pawns) -> bool:
    """Sawtooth: d4 against c6 (c7) + e6, Black has no d-pawn, White has no e-pawn."""
    return (p.has("d4") and p.none_on("e") and p.they("e6") and (p.they("c6") or p.they("c7"))
            and p.they_none_on("d"))


def _french_chain(p: Pawns) -> bool:
    """French chain: d4 + e5 against d5 + e6."""
    return p.has("d4", "e5") and p.they("d5", "e6")


def _french_exchange(p: Pawns) -> bool:
    """Exchange structure: d4 against d5, neither side has an e-pawn."""
    return p.has("d4") and p.they("d5") and p.none_on("e") and p.they_none_on("e")


def _carlsbad(p: Pawns) -> bool:
    """Carlsbad: d4 without a c-pawn against c6 + d5, the opponent has no e-pawn."""
    return p.has("d4") and p.none_on("c") and p.they("c6", "d5") and p.they_none_on("e")


def _hanging(p: Pawns) -> bool:
    """Hanging pawns: c4 + d4 without own b- and e-pawns (the opponent's pawns are not checked)."""
    return p.has("c4", "d4") and p.none_on("b") and p.none_on("e")


def _isolated(p: Pawns) -> bool:
    """Isolated d-pawn: no own c- and e-pawns, the opponent has no d-pawn (otherwise it is a Benoni or hanging pawns)."""
    return (any(p.has(f"d{rank}") for rank in (3, 4, 5)) and p.none_on("c") and p.none_on("e")
            and p.they_none_on("d"))


def _stonewall(p: Pawns) -> bool:
    """Stonewall: own pawns d4 + e3 + f4 (the opponent's pawns are not checked)."""
    return p.has("d4", "e3", "f4")


def _spanish(p: Pawns) -> bool:
    """Code spanish: e4 without a d-pawn against d6, the opponent has no e-pawn (the d-pawn was exchanged for the e-pawn)."""
    return p.has("e4") and p.none_on("d") and p.they("d6") and p.they_none_on("e")


def _symmetry(p: Pawns) -> bool:
    """Symmetry in the centre: e4 against e5, the d-pawns are exchanged."""
    return p.has("e4") and p.they("e5") and p.none_on("d") and p.they_none_on("d")


RULES: tuple[tuple[str, Callable[[Pawns], bool]], ...] = (
    ("hedgehog", _hedgehog), ("maroczy", _maroczy), ("wedge", _wedge), ("kid_chain", _kid_chain),
    ("modern_benoni", _modern_benoni), ("stonewall", _stonewall), ("saw", _saw), ("french_chain", _french_chain),
    ("french_exchange", _french_exchange), ("carlsbad", _carlsbad), ("hanging_pawns", _hanging),
    ("isolated_pawn", _isolated), ("spanish", _spanish), ("symmetry", _symmetry),
)  # the order is the order of checking: the first rule that fires wins


def detect(board: chess.Board) -> str | None:
    """Structure of a position: the rule for White, then for the mirrored position (the same structure for Black)."""
    sides = (Pawns(board, chess.WHITE), Pawns(board.mirror(), chess.WHITE))
    for code, rule in RULES:
        if any(rule(side) for side in sides):
            return code
    return None


CENTRE_TYPES = ("closed", "mobile", "open")  # center_type codes, in the order they are checked
CENTRE_FILES = ("d", "e")


def _blocked(p: Pawns, file: str) -> bool:
    """On the file an own pawn stands right in front of an opponent pawn (White's point of view: ours below, theirs above)."""
    return any(f"{file}{rank}" in p.ours and f"{file}{rank + 1}" in p.theirs for rank in range(2, 8))


def _mobile(p: Pawns) -> bool:
    """Own pawns on d4 and e4 with nothing in front of them, and the opponent has no d-pawn."""
    in_front = p.ours | p.theirs
    return p.has("d4", "e4") and "d5" not in in_front and "e5" not in in_front and p.they_none_on("d")


def center_type(board: chess.Board) -> str | None:
    """Type of the centre: closed, mobile (of either side, by the mirrored position) or open; None - none of them."""
    white = Pawns(board, chess.WHITE)
    if all(_blocked(white, file) for file in CENTRE_FILES):
        return "closed"
    if _mobile(white) or _mobile(Pawns(board.mirror(), chess.WHITE)):
        return "mobile"
    if all(white.none_on(file) and white.they_none_on(file) for file in CENTRE_FILES):
        return "open"
    return None


def game_structure(moves: Iterable[chess.Move], start: chess.Board | None = None) -> str | None:
    """
    The longest structure of a game between FIRST_PLY and LAST_PLY (at least MIN_PLIES plies). "Longest" - by the number of
    window positions in which it was detected (not necessarily consecutive). start - the starting position, if not the
    ordinary one.
    """
    board = (start or chess.Board()).copy()
    seen: Counter[str] = Counter()
    for ply, move in enumerate(moves, start=1):
        board.push(move)
        if ply > LAST_PLY:
            break
        if ply >= FIRST_PLY and (code := detect(board)) is not None:
            seen[code] += 1
    if not seen:
        return None
    code, count = seen.most_common(1)[0]
    return code if count >= MIN_PLIES else None
