"""
Endgame technique puzzles from endgame tablebases (task 27.8) -> data/puzzles/endgame_generated.csv.gz.

The open puzzle database has almost no pure technique (key squares, opposition, outflanking, the rule of the square,
the "wrong" bishop), so the positions are generated: a random setup of an ending type -> tablebases (settings.TABLEBASE_URL)
-> a puzzle is taken only if exactly one move is correct (a win or, in defence, the only draw) and it fits the
theme. A legal opponent move is put before the position (a retreat of his king), as in the lichess format: FEN is before the
opponent's move, the first move in Moves is his. Rating - by the depth of the result (DTZ). Themes - tags "regence:<code>"
(a data identifier, not a brand).
Deterministic (--seed); needs network; not run in CI. Loading into the database - scripts/import_puzzles.py (source
"regence", the theme comes from the tag).

Stalemate defence (task 27.9, "Save the game"): a queen against a bishop or rook pawn on its seventh rank, the queen
watching the promotion square and the white king far away, the weaker side to move. By the theory of this ending a queen
beats every other pawn on the seventh, and against a/c/f/h pawns the defence holds only thanks to stalemate (...Ka1, and
Qxc2 is stalemate; the king in front of the rook pawn). So a puzzle is taken when the tablebases give exactly one drawing
move and it is a king move (a drawing promotion is not this theme). Theme save_by_stalemate.

Re-running with --themes keeps the rows of the other themes already in the output file (only the requested themes are
rebuilt), so one theme can be added without regenerating the whole file.

Lucena and Philidor are left out deliberately: in these rook positions there are almost always several correct moves
(measured 16.11.2026: of 70 Lucena and 50 Philidor positions - none with a single move), while a puzzle accepts one.
These techniques are practised in the endgame trainer (frontend/src/content/endgames.json: lucena, philidor), where any
move that is correct per the tablebases is accepted.

Politeness to the tablebase server: a pause between requests, on a 429 response - a minute of waiting (as lichess asks).

    python -m scripts.dev.build_endgame_puzzles [--per-theme 90] [--output path]
"""

import argparse
import csv
import gzip
import json
import pathlib
import random
import time
import urllib.error
import urllib.parse
import urllib.request

import chess

from src.core.config import settings
from src.services.puzzle_import import validate_row
from src.services.themes import THEMES_BY_CODE

OUTPUT = pathlib.Path(__file__).resolve().parents[2] / "data" / "puzzles" / "endgame_generated.csv.gz"
FIELDS = ("PuzzleId", "FEN", "Moves", "Rating", "RatingDeviation", "Popularity", "NbPlays", "Themes")


def probe(fen: str) -> dict:
    """Tablebase answer for a position (settings.TABLEBASE_URL); 429 - wait a minute, otherwise up to five attempts."""
    url = settings.TABLEBASE_URL + "?" + urllib.parse.urlencode({"fen": fen})
    request = urllib.request.Request(url, headers={"User-Agent": "regence-endgame-puzzles"})
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(request, timeout=15))
        except urllib.error.HTTPError as exc:
            time.sleep(61 if exc.code == 429 else 2 + attempt * 3)
        except Exception:
            time.sleep(2 + attempt * 3)
    raise RuntimeError("tablebase unavailable")


def place(pieces: dict[chess.Square, chess.Piece], turn: chess.Color) -> chess.Board | None:
    """A board from a setup and the side to move; an impossible position or a check against the mover - None."""
    board = chess.Board(None)
    for square, piece in pieces.items():
        board.set_piece_at(square, piece)
    board.turn = turn
    board.castling_rights = 0
    return board if board.is_valid() and not board.is_check() else None


K, P, B, R, N, Q = chess.KING, chess.PAWN, chess.BISHOP, chess.ROOK, chess.KNIGHT, chess.QUEEN
W, BL = chess.WHITE, chess.BLACK


def sq(file: int, rank: int) -> chess.Square | None:
    """A square by file and rank (0-7); off the board - None."""
    return chess.square(file, rank) if 0 <= file <= 7 and 0 <= rank <= 7 else None


def gen_kpk(rng: random.Random) -> chess.Board | None:
    """King and pawn against king, White to move: kings near the pawn - opposition, key squares, outflanking."""
    pawn = sq(rng.randint(1, 6), rng.randint(1, 4))
    pf, pr = chess.square_file(pawn), chess.square_rank(pawn)
    wk = sq(pf + rng.randint(-2, 2), pr + rng.randint(-1, 2))
    bk = sq(pf + rng.randint(-2, 2), pr + rng.randint(2, 4))
    if None in (wk, bk) or len({pawn, wk, bk}) < 3:
        return None
    return place({pawn: chess.Piece(P, W), wk: chess.Piece(K, W), bk: chess.Piece(K, BL)}, W)


def gen_square(rng: random.Random) -> chess.Board | None:
    """The rule of the square, White to move: the black king 3-4 files from the pawn, the white king far behind."""
    pawn = sq(rng.randint(0, 7), rng.randint(1, 4))
    pf, pr = chess.square_file(pawn), chess.square_rank(pawn)
    wk = sq(rng.randint(0, 7), rng.randint(0, 2))
    bk = sq(pf + rng.choice([-4, -3, 3, 4]), pr + rng.randint(0, 3))
    if None in (wk, bk) or len({pawn, wk, bk}) < 3:
        return None
    return place({pawn: chess.Piece(P, W), wk: chess.Piece(K, W), bk: chess.Piece(K, BL)}, W)


def gen_wrong_bishop(rng: random.Random) -> chess.Board | None:
    """Defence: the black king against a bishop and a rook pawn, Black to move."""
    pf = rng.choice([0, 7])
    pawn = sq(pf, rng.randint(3, 5))
    corner = sq(pf, 7)
    dark_corner = not bool(chess.BB_SQUARES[corner] & chess.BB_LIGHT_SQUARES)
    bishops = [s for s in chess.SQUARES if bool(chess.BB_SQUARES[s] & chess.BB_LIGHT_SQUARES) == dark_corner]
    bishop = rng.choice(bishops)
    wk = sq(rng.randint(2, 5), rng.randint(2, 5))
    bk = sq(pf + (1 if pf == 0 else -1) * rng.randint(1, 3), rng.randint(5, 7))
    if None in (pawn, wk, bk) or len({pawn, wk, bk, bishop}) < 4:
        return None
    return place({pawn: chess.Piece(P, W), wk: chess.Piece(K, W), bk: chess.Piece(K, BL), bishop: chess.Piece(B, W)}, BL)


def gen_opposite_bishops(rng: random.Random) -> chess.Board | None:
    """Defence: White has a bishop and a pawn, Black has a bishop of the other colour; Black to move."""
    pawn = sq(rng.randint(0, 7), rng.randint(3, 5))
    wk, bk, wb, bb = (sq(rng.randint(0, 7), rng.randint(0, 7)) for _ in range(4))
    if None in (pawn, wk, bk, wb, bb) or len({pawn, wk, bk, wb, bb}) < 5:
        return None
    same_colour = (chess.square_file(wb) + chess.square_rank(wb)) % 2 == (chess.square_file(bb) + chess.square_rank(bb)) % 2
    if chess.square_distance(wk, bk) < 2 or same_colour:  # the bishops must be of different colours
        return None
    return place({pawn: chess.Piece(P, W), wk: chess.Piece(K, W), bk: chess.Piece(K, BL), wb: chess.Piece(B, W),
                  bb: chess.Piece(B, BL)}, BL)


# Files of the pawns that a lone king can hold against a queen by stalemate: rook (a, h) and bishop (c, f) pawns.
STALEMATE_PAWN_FILES = (0, 2, 5, 7)


# The white king this far (in king moves) from the pawn or farther: it cannot help the queen in time - the classic setup.
FAR_KING = 4


def gen_q_vs_pawn(rng: random.Random) -> chess.Board | None:
    """
    Defence: a black pawn of file a/c/f/h on its seventh rank with the king next to it; White has a queen that controls the
    promotion square and a king FAR_KING or more away; Black to move. (A queen that does not watch the square lets the pawn
    promote, and the only draw is the promotion itself - not a stalemate puzzle.)
    """
    pf = rng.choice(STALEMATE_PAWN_FILES)
    pawn, promotion = sq(pf, 1), sq(pf, 0)
    bk = sq(pf + rng.randint(-1, 1), rng.randint(0, 2))
    wq, wk = sq(rng.randint(0, 7), rng.randint(0, 7)), sq(rng.randint(0, 7), rng.randint(3, 7))
    if None in (pawn, bk, wq, wk) or len({pawn, bk, wq, wk}) < 4 or chess.square_distance(wk, pawn) < FAR_KING:
        return None
    board = place({pawn: chess.Piece(P, BL), bk: chess.Piece(K, BL), wq: chess.Piece(Q, W), wk: chess.Piece(K, W)}, BL)
    return board if board is not None and board.is_attacked_by(W, promotion) else None


def key_squares(pawn: chess.Square) -> set[chess.Square]:
    """Key squares of a pawn: two ranks ahead (from the fifth rank - one and two), three files."""
    f, r = chess.square_file(pawn), chess.square_rank(pawn)
    ranks = [r + 2] if r <= 3 else [r + 1, r + 2]
    return {s for rank in ranks for file in (f - 1, f, f + 1) if (s := sq(file, rank)) is not None}


def gen_rook_vs_minor(rng: random.Random) -> chess.Board | None:
    """Defence: White has a rook, Black has a bishop or a knight (both without pawns); Black to move."""
    wk, wr, bk, minor = (rng.randrange(64) for _ in range(4))
    if len({wk, wr, bk, minor}) < 4 or chess.square_distance(wk, bk) < 2:
        return None
    return place({wk: chess.Piece(K, W), wr: chess.Piece(R, W), bk: chess.Piece(K, BL),
                  minor: chess.Piece(rng.choice([B, N]), BL)}, BL)


def classify(board: chess.Board, move: chess.Move, kind: str) -> str | None:
    """The puzzle theme from the ending kind and the only move."""
    after = board.copy(stack=False)
    after.push(move)
    piece = board.piece_type_at(move.from_square)
    if kind == "kpk":
        pawn = next(iter(board.pieces(P, W)))
        if piece != K:
            return None
        own, other = after.king(W), after.king(BL)
        df = abs(chess.square_file(own) - chess.square_file(other))
        dr = abs(chess.square_rank(own) - chess.square_rank(other))
        if (df, dr) in ((0, 2), (2, 0)):
            return "opposition"
        if own in key_squares(pawn):
            return "key_squares"
        before = abs(chess.square_file(board.king(W)) - chess.square_file(other))
        if df > before:
            return "outflanking"
        return None
    if kind == "square":
        return "square_rule" if piece == P else None
    if kind == "wrong_bishop":
        return "wrong_bishop" if piece == K else None
    if kind == "opposite_bishops":
        return "opposite_bishops" if piece in (B, K) else None
    if kind == "rook_vs_minor":  # capturing the rook is a gift, not technique: a single "capture" is not counted as a puzzle
        return None if board.is_capture(move) else "rook_vs_minor"
    if kind == "q_vs_pawn":  # the king holds the pawn and waits for stalemate; a promotion that draws is another story
        return "save_by_stalemate" if piece == K else None
    return None


def retreat(board: chess.Board, rng: random.Random) -> tuple[chess.Board, chess.Move] | None:
    """The position before the opponent's move: his king arrives at its square from a neighbouring one (legal, no check)."""
    side = not board.turn
    king = board.king(side)
    options = []
    for origin in chess.SquareSet(chess.BB_KING_ATTACKS[king]):
        if board.piece_at(origin) is not None:
            continue
        before = board.copy(stack=False)
        before.remove_piece_at(king)
        before.set_piece_at(origin, chess.Piece(K, side))
        before.turn = side
        move = chess.Move(origin, king)
        if before.is_valid() and not before.is_check() and move in before.legal_moves:
            options.append((before, move))
    return rng.choice(options) if options else None


MAX_SOLVER_MOVES = 5


def extend(board: chess.Board, move: chess.Move, reply: str, limit: int) -> tuple[list[str], int]:
    """
    Solution line: the first only move, then the opponent's best reply per the tablebases and again the solver's move - while
    it is the only one (otherwise the puzzle can be "guessed"). Returns the moves (UCI) and the number of tablebase requests.
    """
    line = [move.uci()]
    probes = 0
    current = board.copy(stack=False)
    current.push(move)
    for _ in range(limit - 1):
        if current.is_game_over() or any(p.piece_type == chess.QUEEN for p in current.piece_map().values()):
            break
        answer = probe(current.fen())
        probes += 1
        time.sleep(0.25)
        if not answer.get("moves"):
            break
        best = chess.Move.from_uci(answer["moves"][0]["uci"])  # the opponent's best reply is the first in the list
        current.push(best)
        if current.is_game_over():
            current.pop()
            break
        options = probe(current.fen())
        probes += 1
        time.sleep(0.25)
        good = [m for m in options.get("moves", []) if m["category"] == reply]
        if len(good) != 1:
            current.pop()
            break
        nxt = chess.Move.from_uci(good[0]["uci"])
        line += [best.uci(), nxt.uci()]
        current.push(nxt)
    return line, probes


GENERATORS = {"kpk": (gen_kpk, "win"), "square": (gen_square, "win"), "wrong_bishop": (gen_wrong_bishop, "draw"),
              "opposite_bishops": (gen_opposite_bishops, "draw"), "rook_vs_minor": (gen_rook_vs_minor, "draw"),
              "q_vs_pawn": (gen_q_vs_pawn, "draw")}
THEMES = {"opposition": "kpk", "key_squares": "kpk", "outflanking": "kpk", "square_rule": "square",
          "wrong_bishop": "wrong_bishop", "opposite_bishops": "opposite_bishops", "rook_vs_minor": "rook_vs_minor",
          "save_by_stalemate": "q_vs_pawn"}
TAGS = {"kpk": "endgame pawnEndgame", "square": "endgame pawnEndgame", "wrong_bishop": "endgame equality",
        "opposite_bishops": "endgame equality", "rook_vs_minor": "endgame equality",
        "q_vs_pawn": "endgame equality queenEndgame"}


def kept_rows(path: pathlib.Path, rebuilt: set[str]) -> list[dict]:
    """Rows of the output file whose theme is not being rebuilt in this run (they are written back unchanged)."""
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
        return [row for row in csv.DictReader(source)
                if not any(tag == f"regence:{theme}" for theme in rebuilt for tag in row["Themes"].split())]


def save(path: pathlib.Path, found: dict[str, list[dict]], kept: list[dict] | None = None) -> int:
    """
    Writes the kept rows of other themes and the found puzzles to a compressed CSV (lichess database format); returns the
    number of rows written.
    """
    rows = [*(kept or []), *(row for rows in found.values() for row in rows)]
    with gzip.open(path, "wt", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    """Generates puzzles up to --per-theme per theme or up to --max-probes tablebase requests; saves as it goes."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--per-theme", type=int, default=90)
    parser.add_argument("--seed", type=int, default=8)
    parser.add_argument("--max-probes", type=int, default=6000)
    parser.add_argument("--output", type=pathlib.Path, default=OUTPUT)
    parser.add_argument("--themes", default="", help="only these themes, comma-separated (default - all)")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    wanted = [t for t in args.themes.split(",") if t] or list(THEMES)
    found: dict[str, list[dict]] = {theme: [] for theme in wanted}
    kept = kept_rows(args.output, set(wanted))
    seen: set[str] = set()
    # Starting positions of accepted puzzles: a retreat from different verified positions may lead to the same one -
    # such a puzzle would differ only by the opponent's first move, which is a repeat for the player.
    starts: set[str] = set()
    probes = 0
    while probes < args.max_probes and any(len(v) < args.per_theme for v in found.values()):
        kinds = sorted({THEMES[t] for t, v in found.items() if len(v) < args.per_theme})
        kind = rng.choice(kinds)
        make, goal = GENERATORS[kind]
        board = make(rng)
        if board is None or board.fen() in seen:
            continue
        seen.add(board.fen())
        data = probe(board.fen())
        probes += 1
        time.sleep(0.25)
        if data.get("category") != goal:
            continue
        reply = "loss" if goal == "win" else "draw"
        good = [m for m in data["moves"] if m["category"] == reply]
        if len(good) != 1 or (goal == "draw" and all(m["category"] == "draw" for m in data["moves"])):
            continue
        move = chess.Move.from_uci(good[0]["uci"])
        theme = classify(board, move, kind)
        if theme not in found or len(found[theme]) >= args.per_theme:
            continue
        before = retreat(board, rng)
        if before is None:
            continue
        start, first = before
        if start.fen() in starts:
            continue
        line, extra = extend(board, move, reply, MAX_SOLVER_MOVES)
        probes += extra
        depth = abs(good[0].get("dtz") or data.get("dtz") or 10)
        solver_moves = (len(line) + 1) // 2
        rating = max(800, min(2400, 850 + depth * 10 + 180 * (solver_moves - 1) + (250 if goal == "draw" else 0)))
        row = {
            "PuzzleId": f"tb{len(seen):05d}{kind[:2]}", "FEN": start.fen(), "Moves": " ".join([first.uci(), *line]),
            "Rating": str(rating), "RatingDeviation": "80", "Popularity": "90", "NbPlays": "0",
            "Themes": f"{TAGS[kind]} regence:{theme}",
        }
        if theme not in THEMES_BY_CODE or not validate_row(row):
            continue
        found[theme].append(row)
        starts.add(start.fen())
        total = sum(len(v) for v in found.values())
        if total % 10 == 0:  # the run is long (a tablebase request takes ~1 s): what is found is not lost on interruption
            save(args.output, found, kept)
            print(probes, {t: len(v) for t, v in found.items()}, flush=True)
    total = save(args.output, found, kept)
    print(f"probes {probes}, puzzles {total} -> {args.output}")
    print({t: len(v) for t, v in found.items()})


if __name__ == "__main__":
    main()
