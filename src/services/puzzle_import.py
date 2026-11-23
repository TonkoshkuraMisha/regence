# --- FILE: src/services/puzzle_import.py ---
"""
Loading puzzles into the database (task 13.1): rows of the data/puzzles/lichess_subset.csv.gz sample -> the puzzles and
puzzle_themes tables. A puzzle's themes are registry codes: from the database tags (``themes_for_lichess_tags``) and from
the motifs that the first solution move creates on the board (``themes_for_motif``: the kind of fork by piece, battery,
interference, etc.). Puzzles already loaded from the same source are skipped - a repeated run is safe. Named mating
patterns, for which the database has no tags, are recognised from the final position of the solution
(src/services/mate_patterns.py).

The tagging is versioned (TAG_VERSION): when the registry, the detector or the mate classifier changes, the version grows and
the import re-tags the already loaded puzzles (``retag_outdated``) - without a repeated load.

The load is run by scripts/import_puzzles.py (on deployment - the migrate service): the main sample SUBSET, then,
if the file exists, the EXTRA supplement for themes without database tags and the own ENDGAME puzzles, then re-tagging. The
row columns are as in the lichess export: PuzzleId, FEN, Moves, Rating, RatingDeviation, Popularity, NbPlays, Themes. The
original database tags are kept in puzzles.source_tags (first 300 characters) - re-tagging works from them.

Own puzzles (source GENERATED_SOURCE) - endgame technique from endgame tablebases
(scripts/dev/build_endgame_puzzles.py, data/puzzles/endgame_generated.csv.gz): the open database has almost none. Their
theme is given by the tag "regence:<registry code>" (own_themes). Until 19.11.2026 the source and tags were called
"michess" - the migration d3a8f1c6e2b7 renamed them.
"""

import csv
import gzip
import pathlib
from collections.abc import Iterable, Iterator

import chess
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.puzzle import Puzzle, PuzzleTheme
from src.services import theme_detectors
from src.services.mate_patterns import patterns_for_solution
from src.services.mentor_service import analyze_move
from src.services.themes import THEMES_BY_CODE, themes_for_lichess_tags, themes_for_motif

SOURCE = "lichess"  # puzzles.source value; with puzzles.source_id (PuzzleId) it identifies already loaded puzzles
GENERATED_SOURCE = "regence"  # puzzles.source of own puzzles (was "michess" until 19.11.2026, see d3a8f1c6e2b7)
OWN_TAG = "regence:"  # prefix of the theme tag of an own puzzle "regence:<code>", as in endgame_generated.csv.gz
TAG_VERSION = 3  # 2: stage by the refined formula; 3: themes without database tags (theme_detectors.py)
SUBSET = pathlib.Path(__file__).resolve().parents[2] / "data" / "puzzles" / "lichess_subset.csv.gz"
EXTRA = SUBSET.with_name("lichess_themes_extra.csv.gz")  # built by scripts/dev/build_theme_extra.py
ENDGAME = SUBSET.with_name("endgame_generated.csv.gz")  # built by scripts/dev/build_endgame_puzzles.py
BATCH = 500  # puzzles per transaction during loading and re-tagging


def read_subset(path: pathlib.Path = SUBSET) -> Iterator[dict]:
    """Rows of the compressed sample CSV as dicts (keys are column headers); reads line by line, not in memory."""
    with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
        yield from csv.DictReader(source)


def stage_for(rating: int, moves: list[str]) -> int:
    """
    Puzzle stage (task 13.4): 1 - introduction (the technique in pure form), 2 - consolidation, 3 - in combination, 4 - master.
    By rating and solution length. The technique "in pure form" is a move and its natural continuation (a fork and the
    capture of a piece), i.e. up to two moves by the solver; length raises the stage from three moves. ``moves`` - as in
    the database: the first move is the opponent's, then alternation. The same formula is in migration c5e7a9b1d3f6.

    Thresholds (one condition is enough): stage 4 - rating from 2000 or from 10 plies (5 solver moves);
    3 - from 1600 or from 8 plies (4 moves); 2 - from 1200 or from 6 plies (3 moves); otherwise 1.
    """
    plies = len(moves)
    if rating >= 2000 or plies >= 10:
        return 4
    if rating >= 1600 or plies >= 8:
        return 3
    if rating >= 1200 or plies >= 6:
        return 2
    return 1


def solver_position(fen: str, moves: list[str]) -> chess.Board:
    """The position the solver sees: after the opponent's move moves[0]."""
    board = chess.Board(fen)
    board.push_uci(moves[0])
    return board


def detected_themes(fen: str, moves: list[str]) -> list[str]:
    """Themes that the detector sees in the first solution move (motifs created by this move in favour of the solver)."""
    board = solver_position(fen, moves)
    move = chess.Move.from_uci(moves[1])
    facts = analyze_move(board, move)
    result: list[str] = []
    for motif in facts.created:
        attacker = board.copy(stack=False)
        attacker.push(move)
        piece = attacker.piece_at(motif.square)
        for code in themes_for_motif(motif.code, piece.symbol().lower() if piece else None):
            if code not in result:
                result.append(code)
    return result


def own_themes(tags: list[str]) -> list[str]:
    """Themes of own puzzles: tags "regence:<code>" with a code from the registry (unknown ones are skipped)."""
    return [code for tag in tags if tag.startswith(OWN_TAG) and (code := tag[len(OWN_TAG):]) in THEMES_BY_CODE]


def themes_for_row(row: dict) -> list[str]:
    """
    All themes of a puzzle without repeats, from four sources in order: database tags (``themes_for_lichess_tags``), motifs
    of the first solution move (``detected_themes``), the mating pattern of the final position (``patterns_for_solution``) and
    detectors of themes without tags (``theme_detectors.detect``).
    """
    moves = row["Moves"].split()
    codes = own_themes(row["Themes"].split())
    for code in themes_for_lichess_tags(row["Themes"].split()):
        if code not in codes:
            codes.append(code)
    extra = theme_detectors.detect(row["FEN"], moves, row["Themes"].split())
    for code in [*detected_themes(row["FEN"], moves), *patterns_for_solution(row["FEN"], moves), *extra]:
        if code not in codes:
            codes.append(code)
    return codes


def validate_row(row: dict) -> bool:
    """Moves are legal from the position, a solution exists (an opponent move + at least one solver move)."""
    moves = row["Moves"].split()
    if len(moves) < 2:
        return False
    try:
        board = chess.Board(row["FEN"])
        for uci in moves:
            move = chess.Move.from_uci(uci)
            if move not in board.legal_moves:
                return False
            board.push(move)
    except ValueError:
        return False
    return True


async def retag_outdated(db: AsyncSession) -> int:
    """
    Re-tag puzzles whose tagging version is below TAG_VERSION (themes and stage). Returns the number of puzzles. Goes in
    batches of BATCH with a commit after each: an interrupted run continues from the remaining ones. At the end the cache
    of puzzle counts by stage is reset (puzzles.reset_stage_counts).
    """
    from sqlalchemy import delete

    from src.services.puzzles import reset_stage_counts

    count = 0
    while True:
        batch = (await db.execute(
            select(Puzzle).where(Puzzle.tag_version < TAG_VERSION).order_by(Puzzle.id).limit(BATCH)
        )).scalars().all()
        if not batch:
            break
        ids = [p.id for p in batch]
        await db.execute(delete(PuzzleTheme).where(PuzzleTheme.puzzle_id.in_(ids)))
        for puzzle in batch:
            row = {"FEN": puzzle.fen, "Moves": puzzle.moves, "Themes": puzzle.source_tags}
            db.add_all(PuzzleTheme(puzzle_id=puzzle.id, theme=code) for code in themes_for_row(row))
            puzzle.stage = stage_for(puzzle.rating, puzzle.moves.split())
            puzzle.tag_version = TAG_VERSION
        await db.commit()
        db.expire_all()
        count += len(batch)
    reset_stage_counts()
    return count


async def import_rows(db: AsyncSession, rows: Iterable[dict], source: str = SOURCE) -> tuple[int, int]:
    """
    Loads rows; returns (added, skipped - already present or invalid). "Already present" is by the pair
    puzzles.source (source: SOURCE or GENERATED_SOURCE) and puzzles.source_id; a repeated PuzzleId within one run
    is also skipped. Commit - every BATCH puzzles.
    """
    existing = set((await db.execute(select(Puzzle.source_id).where(Puzzle.source == source))).scalars())
    added = skipped = 0
    pending = 0
    for row in rows:
        if row["PuzzleId"] in existing or not validate_row(row):
            skipped += 1
            continue
        puzzle = Puzzle(
            source=source, source_id=row["PuzzleId"], fen=row["FEN"], moves=row["Moves"],
            rating=int(row["Rating"]), rating_deviation=int(row["RatingDeviation"]),
            popularity=int(row["Popularity"]), plays=int(row["NbPlays"]), source_tags=row["Themes"][:300],
            stage=stage_for(int(row["Rating"]), row["Moves"].split()), tag_version=TAG_VERSION,
        )
        puzzle.themes = [PuzzleTheme(theme=code) for code in themes_for_row(row)]
        db.add(puzzle)
        existing.add(row["PuzzleId"])
        added += 1
        pending += 1
        if pending >= BATCH:
            await db.commit()
            pending = 0
    await db.commit()
    from src.services.puzzles import reset_stage_counts

    reset_stage_counts()
    return added, skipped
