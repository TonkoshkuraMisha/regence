# --- FILE: scripts/build_classics.py ---
"""
Master games with explanations (task 14.7): selecting games from the archive and engine markup.

Candidates are archive games where the "Guess the master's move" selection (the guess_positions table,
scripts/build_guess_positions.py) found moments for the winner: decisive games, 20-70 moves, different pairs of opponents,
at most --per-player games of one winner. For every game the engine evaluates each position; for moves with a mistake
or a tactical idea the mentor (src/services/coach.py) writes an explanation with codes from the coach.* catalog;
the selected moments become "what would you play?" stops (with stored engine lines - the answer is graded without a server).

Chosen games (Big course, task 27.6): --library takes games of the game library by their moves_hash (a full hash or
a prefix of at least HASH_PREFIX_MIN characters - the hash is computed from the moves, so it is the same on every machine),
--pgn takes every game of a PGN file. Their stops are found by the same selection as "Guess the master's move"
(scripts/build_guess_positions.analyse_game): positions with one clearly best move, of the winner's side (both sides in
a draw); a game with fewer than MIN_STOPS such positions is skipped. The JSON keeps where the game came from (source).

The result is frontend/src/content/classics/<id>.json: moves, evaluations, comments, stops and blank places for
the intro and summary texts (written by the course author in en and uk; the texts are kept on re-run).

    python scripts/build_classics.py --count 30 --workers 8
    python scripts/build_classics.py --library 3f9a1c2b7d4e 81c0d2e9a7f1
    python scripts/build_classics.py --pgn games/open-file.pgn
"""

import argparse
import asyncio
import io
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import chess
import chess.engine
import chess.pgn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "content" / "classics"
ARCHIVE_PASSWORD = "!historical_archive_no_login!"
MATE = 100000
MIN_MOVES, MAX_MOVES = 20, 70
LANGUAGES = ("en", "uk")  # the authored intro and summary texts (CLAUDE.md, language policy)
# Chosen games: the least number of stops that makes a "game with stops" step, and the shortest accepted hash prefix.
MIN_STOPS = 2
HASH_PREFIX_MIN = 12
# Not for the teaching selection: a game around which there was a public dispute about fair play.
EXCLUDED = ("carlsen-niemann-2022",)
# Classics - games with a classical time control: rapid, online, handicap and exhibition events are not taken.
NOT_CLASSICAL = re.compile(
    r"blitz|rapid|bullet|speed|online|chess\.com|chess24|titled|tuesday|\d-0|handicap|simul|armageddon|"
    r"meltwater|tour final|chessable|goldmoney|aimchess|airthings|champions chess|banter|lichess|blind|basque|"
    r"fischer ?random|chess960|exhibition|veterans|clutch|\bko\b|\d+'",
    re.IGNORECASE,
)


def _slug(white: str, black: str, year: str) -> str:
    """Builds a string identifier of a classical game from the players and the year."""
    def last(name: str) -> str:
        """Extracts a chess player's lower-case surname from the PGN header."""
        return re.sub(r"[^a-z0-9]+", "-", name.split(",")[0].strip().lower()).strip("-")
    return f"{last(white)}-{last(black)}-{year}"


async def _candidates(count: int, per_player: int, exclude: set[str]) -> list[dict]:
    """Selects decisive classical games of champions from the archive."""
    from sqlalchemy import func, select

    from scripts.build_guess_positions import _sessions
    from src.models.game import Game
    from src.models.guess import GuessPosition

    engine, sessions = _sessions()
    async with sessions() as db:
        rows = (await db.execute(
            select(Game.id, Game.pgn, func.array_agg(GuessPosition.ply), func.array_agg(GuessPosition.id))
            .join(GuessPosition, GuessPosition.game_id == Game.id).group_by(Game.id, Game.pgn)
        )).all()
        stops = {}
        for row in (await db.execute(select(GuessPosition))).scalars():
            stops.setdefault(row.game_id, []).append(
                {"ply": row.ply, "move": row.move_uci, "best_cp": row.best_cp, "gap_cp": row.gap_cp, "lines": row.lines})
    await engine.dispose()

    scored = []
    for game_id, pgn, _plies, _ids in rows:
        game = chess.pgn.read_game(io.StringIO(pgn))
        if game is None:
            continue
        if NOT_CLASSICAL.search(game.headers.get("Event", "")):
            continue
        result = game.headers.get("Result")
        moves = list(game.mainline_moves())
        if result not in ("1-0", "0-1") or not MIN_MOVES * 2 <= len(moves) <= MAX_MOVES * 2:
            continue
        winner_parity = 0 if result == "1-0" else 1
        own = [s for s in stops[game_id] if s["ply"] % 2 == winner_parity]
        if len(own) < 2:
            continue
        winner = game.headers["White" if result == "1-0" else "Black"]
        scored.append((len(own), game_id, game, winner, sorted(own, key=lambda s: s["ply"])))
    scored.sort(key=lambda item: (-item[0], item[1]))

    chosen: list[dict] = []
    per_winner: dict[str, int] = {}
    pairs: set[frozenset[str]] = set()
    for _, game_id, game, winner, own in scored:
        year = (game.headers.get("Date") or "????")[:4]
        if _slug(game.headers["White"], game.headers["Black"], year) in exclude:
            continue
        pair = frozenset((game.headers["White"], game.headers["Black"]))
        if pair in pairs or per_winner.get(winner, 0) >= per_player:
            continue
        pairs.add(pair)
        per_winner[winner] = per_winner.get(winner, 0) + 1
        chosen.append({"game_id": game_id, "pgn": str(game), "stops": own})
        if len(chosen) >= count:
            break
    return chosen


async def _library_items(prefixes: list[str]) -> list[dict]:
    """Library games by moves_hash (or its unique prefix), in the given order; an unknown or ambiguous one stops the run."""
    from sqlalchemy import select

    from scripts.build_guess_positions import _sessions
    from src.models.library import LibraryGame
    from src.services.library import to_pgn

    short = [p for p in prefixes if len(p) < HASH_PREFIX_MIN]
    if short:
        raise SystemExit(f"Hash prefixes shorter than {HASH_PREFIX_MIN} characters: {', '.join(short)}")
    engine, sessions = _sessions()
    items: list[dict] = []
    problems: list[str] = []
    async with sessions() as db:
        for prefix in prefixes:
            rows = (await db.execute(
                select(LibraryGame).where(LibraryGame.moves_hash.startswith(prefix.lower())).limit(2))).scalars().all()
            if len(rows) != 1:
                problems.append(f"{prefix}: {'not in the library' if not rows else 'ambiguous prefix'}")
                continue
            items.append({"pgn": to_pgn(rows[0]), "source": {"library": rows[0].moves_hash}})
    await engine.dispose()
    if problems:
        raise SystemExit("; ".join(problems))
    return items


def _pgn_items(path: Path) -> list[dict]:
    """Every game of a PGN file (UTF-8 or cp1251, as the library import reads it)."""
    from src.services.library import open_pgn, read_games

    with open_pgn(str(path)) as handle:
        return [{"pgn": str(game), "source": {"pgn": path.name}} for game in read_games(handle)]


def chosen_stops(positions: list[dict], result: str | None) -> list[dict]:
    """
    Stops of a chosen game from the "Guess the move" selection: the winner's positions (both sides in a draw), in ply
    order, with only the fields the client grades by (ClassicStop).
    """
    parity = {"1-0": 0, "0-1": 1}.get(result or "")
    own = [p for p in positions if parity is None or p["ply"] % 2 == parity]
    fields = ("ply", "move", "best_cp", "gap_cp", "lines")
    return [{key: p[key] for key in fields} for p in sorted(own, key=lambda p: p["ply"])]


def analyse_chosen(item: dict, depth: int, shallow_depth: int, deep_time: float) -> dict | None:
    """A chosen game: stops by the "Guess the move" selection, then the markup of an archive game; None - too few stops."""
    from scripts.build_guess_positions import analyse_game

    game = chess.pgn.read_game(io.StringIO(item["pgn"]))
    if game is None:
        return None
    _, positions = analyse_game(0, item["pgn"], shallow_depth, deep_time)
    stops = chosen_stops(positions, game.headers.get("Result"))
    if len(stops) < MIN_STOPS:
        return None
    return {**analyse({**item, "stops": stops}, depth), "source": item["source"]}


def _cp(score: chess.engine.PovScore, color: chess.Color) -> int:
    """Converts the engine evaluation of a position to centipawns from the side to move's point of view."""
    return score.pov(color).score(mate_score=MATE) or 0


def analyse(item: dict, depth: int) -> dict:
    """Analyses a game with the engine, producing evaluations, comments and stops."""
    from src.services.analysis_service import classify_move_by_cp_loss
    from src.services.bots.base import resolve_stockfish_path
    from src.services.coach import comment_for_move

    game = chess.pgn.read_game(io.StringIO(item["pgn"]))
    assert game is not None
    moves = list(game.mainline_moves())
    engine = chess.engine.SimpleEngine.popen_uci(resolve_stockfish_path())
    try:
        engine.configure({"Threads": 1, "Hash": 32})
        board = game.board()
        infos = []
        for move in [*moves, None]:
            if board.is_game_over():
                infos.append(None)
            else:
                info = engine.analyse(board, chess.engine.Limit(depth=depth))
                infos.append({"best": info["pv"][0].uci() if info.get("pv") else None, "score": info["score"]})
            if move is not None:
                board.push(move)
    finally:
        engine.quit()

    board = game.board()
    evals: list[int] = []
    comments: dict[str, dict] = {}
    for ply, move in enumerate(moves):
        before, after = infos[ply], infos[ply + 1]
        mover = board.turn
        best_cp = _cp(before["score"], mover) if before else 0
        if after is None:
            board_after = board.copy()
            board_after.push(move)
            played_cp = MATE if board_after.is_checkmate() else 0
        else:
            played_cp = _cp(after["score"], mover)
        loss = max(0, best_cp - played_cp) if abs(best_cp) < MATE // 2 else 0
        classification, _ = classify_move_by_cp_loss(loss, is_best_move=before is not None and before["best"] == move.uci())
        reply = after["best"] if after else None
        comment = comment_for_move(board, move, before["best"] if before else None, reply, classification)
        if comment:
            comments[str(ply)] = comment
        board.push(move)
        evals.append(played_cp if mover == chess.WHITE else -played_cp)

    headers = game.headers
    year = (headers.get("Date") or "????")[:4]
    return {
        "id": _slug(headers.get("White", "?"), headers.get("Black", "?"), year),
        "white": headers.get("White", "?"), "black": headers.get("Black", "?"),
        "event": headers.get("Event") if headers.get("Event", "?") != "?" else None,
        "year": year if year.isdigit() else None, "result": headers.get("Result"),
        "moves": [m.uci() for m in moves], "evals": evals, "comments": comments, "stops": item["stops"],
    }


def _write(data: dict) -> Path:
    """Writes the annotated classical games into the client's JSON catalog."""
    path = OUT / f"{data['id']}.json"
    texts = {"intro": {lang: "" for lang in LANGUAGES}, "summary": {lang: "" for lang in LANGUAGES}}
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        texts = {key: old.get(key, texts[key]) for key in texts}
    path.write_text(json.dumps({**data, **texts}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def _build_chosen(items: list[dict], args: argparse.Namespace) -> None:
    """Marks up chosen games in parallel and writes those that have enough stops."""
    print(f"Chosen {len(items)} games", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(analyse_chosen, item, args.depth, args.shallow_depth, args.deep_time): item for item in items}
        for done, future in enumerate(as_completed(futures), 1):
            data = future.result()
            if data is None:
                print(f"[{done}/{len(items)}] skipped {futures[future]['source']}: fewer than {MIN_STOPS} stops", flush=True)
                continue
            path = _write(data)
            print(f"[{done}/{len(items)}] {path.name}: {len(data['comments'])} comments, {len(data['stops'])} stops",
                  flush=True)


def main() -> None:
    """Entry point of the script selecting and annotating classical master games."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--per-player", type=int, default=2)
    parser.add_argument("--depth", type=int, default=14)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--exclude", nargs="*", default=list(EXCLUDED), help="ids of games not to take")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--library", nargs="+", metavar="HASH", help="library games by moves_hash (or its prefix)")
    source.add_argument("--pgn", type=Path, help="every game of a PGN file")
    parser.add_argument("--shallow-depth", type=int, default=10, help="chosen games: the fast pass of the stop selection")
    parser.add_argument("--deep-time", type=float, default=1.0, help="chosen games: seconds per position of the deep pass")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.library or args.pgn:
        _build_chosen(asyncio.run(_library_items(args.library)) if args.library else _pgn_items(args.pgn), args)
        return
    chosen = asyncio.run(_candidates(args.count, args.per_player, set(args.exclude)))
    print(f"Selected {len(chosen)} games", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(analyse, item, args.depth) for item in chosen]
        for done, future in enumerate(as_completed(futures), 1):
            data = future.result()
            path = _write(data)
            print(f"[{done}/{len(chosen)}] {path.name}: {len(data['comments'])} comments, "
                  f"{len(data['stops'])} stops", flush=True)


if __name__ == "__main__":
    main()
