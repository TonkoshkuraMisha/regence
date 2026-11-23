"""
Calibration of bot strength by matches against real Stockfish (task 10.4). Not for CI: it is slow and needs the engine.

Each bot (7 historical ones and 10 workshop archetypes) plays:
* against "anchors" - Stockfish with UCI_LimitStrength and a fixed UCI_Elo (the closest to the declared rating);
* against neighbours by declared strength - so that weak bots with nobody to compare against among the anchors (Stockfish
  does not play below 1320) get a rating through the chain.
Each pair plays the opening position with both colours. Ratings are fitted over all games at once
(Elo maximum likelihood, anchors fixed - as in Ordo/BayesElo) with a light prior of
"one drawn result" against the declared rating, so that 0 out of N does not give minus infinity.

The scale is the Stockfish UCI_Elo scale at our time control, not FIDE: bots can be compared with it
among themselves and with the anchors. Result: src/services/bots/calibration.json (rating, games, ±95 %).

    python scripts/calibrate_bots.py --rounds 1 --workers 3
    python scripts/calibrate_bots.py --only morphy --rounds 2
"""

import argparse
import json
import math
import os
import random
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import chess
import chess.engine
import chess.pgn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ANCHOR_ELOS = (1350, 1600, 1850, 2100, 2400)
# UCI_Elo in Stockfish is calibrated at a 60 s + 0.6 s control (≈2 s per move). At 0.1 s per move an anchor plays
# noticeably weaker than its nominal, and the whole scale drifts upward (the first run on 12.11 - by 250-650 points).
ANCHOR_MOVETIME_S = 1.0
MAX_PLIES = 180
ADJUDICATE_CP = 400
# Short balanced openings - so that games of one pair do not repeat move for move.
OPENINGS = (
    "e4 e5 Nf3 Nc6",
    "d4 d5 c4 e6",
    "e4 c5 Nf3 d6",
    "d4 Nf6 c4 g6",
    "e4 e6 d4 d5",
    "c4 e5 Nc3 Nf6",
    "e4 c6 d4 d5",
    "Nf3 d5 g3 Nf6",
)
OUT = ROOT / "src" / "services" / "bots" / "calibration.json"


@dataclass(frozen=True)
class Spec:
    white: str
    black: str
    opening: int
    anchor_movetime: float = ANCHOR_MOVETIME_S


def declared_ratings() -> dict[str, int]:
    """Returns a dict of declared ratings of the historical bots and archetypes."""
    from src.api.bots import AVAILABLE_BOTS
    from src.services.bots.archetypes import ARCHETYPES

    ratings = {b["id"]: int(b["rating"]) for b in AVAILABLE_BOTS}
    ratings.update({a.key: a.config.target_elo for a in ARCHETYPES})
    return ratings


# --- Players (created in the worker process) ---------------------------------------------------

_ENGINES: dict[str, chess.engine.SimpleEngine] = {}


def _engine(name: str, options: dict) -> chess.engine.SimpleEngine:
    """Returns or starts a Stockfish instance in the worker with the required options."""
    from src.services.bots.base import resolve_stockfish_path

    if name not in _ENGINES:
        path = resolve_stockfish_path()
        if not path:
            raise SystemExit("Stockfish not found: python scripts/setup_stockfish.py")
        engine = chess.engine.SimpleEngine.popen_uci(path)
        engine.configure({"Threads": 1, "Hash": 16, **options})
        _ENGINES[name] = engine
    return _ENGINES[name]


def _bot(key: str):
    """Returns an instance of a historical bot or archetype by its key."""
    from src.services.bots import BOT_INSTANCES
    from src.services.bots.archetypes import ARCHETYPES_BY_KEY
    from src.services.bots.personality import PersonalityBot

    if key.startswith("archetype:"):
        return PersonalityBot(ARCHETYPES_BY_KEY[key].config)
    return BOT_INSTANCES[key]


def _move(player: str, board: chess.Board, anchor_movetime: float = ANCHOR_MOVETIME_S) -> chess.Move:
    """Chooses a move in a calibration game for a bot or a Stockfish anchor."""
    if player.startswith("anchor:"):
        elo = int(player.split(":")[1])
        engine = _engine(player, {"UCI_LimitStrength": True, "UCI_Elo": elo})
        return engine.play(board, chess.engine.Limit(time=anchor_movetime)).move
    return chess.Move.from_uci(_bot(player).choose_move(board.fen())["uci"])


def _adjudicate(board: chess.Board) -> str:
    """A game unfinished by MAX_PLIES: full Stockfish decides (an advantage of more than 4 pawns), otherwise a draw."""
    judge = _engine("judge", {})
    score = judge.analyse(board, chess.engine.Limit(time=0.2))["score"].white().score(mate_score=100000)
    if score is not None and score > ADJUDICATE_CP:
        return "1-0"
    if score is not None and score < -ADJUDICATE_CP:
        return "0-1"
    return "1/2-1/2"


def game_pgn(spec: Spec, board: chess.Board, result: str) -> str:
    """A calibration game in PGN - for style metrics (scripts/style_metrics.py)."""
    game = chess.pgn.Game.from_board(board)
    game.headers.update({
        "Event": "regence calibration", "White": spec.white, "Black": spec.black, "Result": result,
        "Opening": OPENINGS[spec.opening % len(OPENINGS)],
    })
    for tag in ("Site", "Date", "Round"):
        game.headers.pop(tag, None)
    return str(game)


def play_game(spec: Spec) -> tuple[Spec, str, int, str]:
    """Plays one calibration game between two participants."""
    board = chess.Board()
    for san in OPENINGS[spec.opening % len(OPENINGS)].split():
        board.push_san(san)
    while not board.is_game_over(claim_draw=True) and board.ply() < MAX_PLIES:
        player = spec.white if board.turn == chess.WHITE else spec.black
        board.push(_move(player, board, spec.anchor_movetime))
    result = board.result(claim_draw=True) if board.is_game_over(claim_draw=True) else _adjudicate(board)
    return spec, result, board.ply(), game_pgn(spec, board, result)


# --- Schedule and rating fitting ------------------------------------------------------------

def schedule(
        declared: dict[str, int], rounds: int, only: set[str] | None,
        anchors_only: bool = False, anchor_movetime: float = ANCHOR_MOVETIME_S,
) -> list[Spec]:
    """Builds the schedule of bot matches against Stockfish anchors and neighbours by strength."""
    bots = sorted(declared, key=lambda k: declared[k])
    specs: list[Spec] = []
    pairs: set[tuple[str, str]] = set()
    for i, bot in enumerate(bots):
        if only and bot not in only:
            continue
        anchors = sorted(ANCHOR_ELOS, key=lambda e: abs(e - declared[bot]))[:3]
        opponents = [f"anchor:{e}" for e in anchors]
        if not anchors_only:
            opponents += [b for b in bots[max(0, i - 2):i + 3] if b != bot]  # neighbours by declared strength
        for opp in opponents:
            pair = tuple(sorted((bot, opp)))
            if pair in pairs:
                continue
            pairs.add(pair)
            for r in range(rounds):
                opening = random.randrange(len(OPENINGS)) if r else hash(pair) % len(OPENINGS)
                specs += [Spec(bot, opp, opening, anchor_movetime), Spec(opp, bot, opening, anchor_movetime)]
    return specs


SCORES = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}
_LOG_LINE = re.compile(r"^\[\d+/\d+\] (\S+) — (\S+): (1-0|0-1|1/2-1/2) ")


def games_from_log(path: Path, without_anchors: bool = False) -> list[tuple[str, str, float]]:
    """
    Games from the output of a previous run: "[n/N] white — black: result (… plies)".
    without_anchors - only bot-vs-bot games: they do not depend on the anchors' time.
    """
    games = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _LOG_LINE.match(line)
        if not match:
            continue
        white, black = match.group(1), match.group(2)
        if without_anchors and (white.startswith("anchor:") or black.startswith("anchor:")):
            continue
        games.append((white, black, SCORES[match.group(3)]))
    return games


def expected(ra: float, rb: float) -> float:
    """Computes the expected score share in a game by the classical Elo formula."""
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def fit(games: list[tuple[str, str, float]], declared: dict[str, int]) -> dict[str, dict]:
    """Ratings of the bots over all games; anchors are fixed. games: (white, black, white's score)."""
    fixed = {f"anchor:{e}": float(e) for e in ANCHOR_ELOS}
    players = {p for w, b, _ in games for p in (w, b) if p not in fixed}
    rating = {p: float(declared.get(p, 1500)) for p in players}
    rating.update(fixed)

    for step in range(4000):
        lr = 40.0 if step < 1000 else 10.0 if step < 3000 else 2.0
        grad = {p: 0.0 for p in players}
        for w, b, s in games:
            e = expected(rating[w], rating[b])
            if w in grad:
                grad[w] += s - e
            if b in grad:
                grad[b] += (1 - s) - (1 - e)
        for p in players:
            # Prior: one "draw" against the declared rating.
            grad[p] += 0.5 - expected(rating[p], declared.get(p, 1500))
            rating[p] += lr * grad[p] / max(1, sum(1 for w, b, _ in games if p in (w, b)))

    result = {}
    scale = 400 / math.log(10)
    for p in players:
        own = [(w, b, s) for w, b, s in games if p in (w, b)]
        info = sum(expected(rating[w], rating[b]) * (1 - expected(rating[w], rating[b])) for w, b, _ in own)
        score = sum(s if w == p else 1 - s for w, b, s in own)
        result[p] = {
            "rating": round(rating[p]),
            "games": len(own),
            "score": score,
            "ci95": round(1.96 * scale / math.sqrt(info)) if info > 0 else None,
            "declared": declared.get(p),
        }
    return result


def main() -> None:
    """Runs the bot strength calibration and saves the result to calibration.json."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rounds", type=int, default=1, help="Games of each pair per colour")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--only", nargs="*", help="Calibrate only these (id or archetype:<id>)")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--from-log", type=Path, help="Recompute ratings from the log of a previous run, without games")
    parser.add_argument("--anchors-only", action="store_true", help="Play only games against anchors")
    parser.add_argument("--reuse-log", type=Path,
                        help="Add bot-vs-bot games from the log of a previous run (without its anchors)")
    parser.add_argument("--anchor-movetime", type=float, default=ANCHOR_MOVETIME_S, help="Seconds per anchor move")
    parser.add_argument("--pgn", type=Path,
                        help="Append games to this PGN (style metrics: scripts/style_metrics.py)")
    args = parser.parse_args()

    random.seed(20261112)
    declared = declared_ratings()

    started = time.monotonic()
    pool = None
    if args.from_log:
        games = games_from_log(args.from_log)
        print(f"{len(games)} games from {args.from_log}", flush=True)
    else:
        specs = schedule(
            declared, args.rounds, set(args.only) if args.only else None,
            anchors_only=args.anchors_only, anchor_movetime=args.anchor_movetime,
        )
        print(f"{len(specs)} games, {args.workers} processes", flush=True)
        games = []
        pool = ProcessPoolExecutor(max_workers=args.workers)
        futures = [pool.submit(play_game, spec) for spec in specs]
        for done, future in enumerate(as_completed(futures), 1):
            spec, result, plies, pgn = future.result()
            games.append((spec.white, spec.black, SCORES[result]))
            print(f"[{done}/{len(specs)}] {spec.white} — {spec.black}: {result} ({plies} plies)", flush=True)
            if args.pgn:
                with args.pgn.open("a", encoding="utf-8") as handle:
                    handle.write(pgn + "\n\n")

    if args.reuse_log:
        reused = games_from_log(args.reuse_log, without_anchors=True)
        print(f"+ {len(reused)} bot-vs-bot games from {args.reuse_log}", flush=True)
        games += reused

    fitted = fit(games, declared)
    if args.only:
        # Neighbours by strength played only a few games with the selected ones - their earlier estimate is more accurate.
        fitted = {key: entry for key, entry in fitted.items() if key in set(args.only)}
    previous = {}
    if args.out.exists():
        previous = json.loads(args.out.read_text(encoding="utf-8")).get("players", {})
    payload = {
        "meta": {
            "date": datetime.now(UTC).strftime("%Y-%m-%d"),
            "games": len(games),
            "anchors": list(ANCHOR_ELOS),
            "anchor_movetime_s": args.anchor_movetime,
            "minutes": round((time.monotonic() - started) / 60, 1),
            "scale": "Stockfish UCI_Elo anchors at our time control (not FIDE)",
        },
        "players": {**previous, **fitted},
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for key, entry in sorted(fitted.items(), key=lambda kv: kv[1]["rating"]):
        print(f"{key:28} {entry['rating']:5} ±{entry['ci95']}  (declared {entry['declared']}, "
              f"{entry['score']}/{entry['games']})", flush=True)

    if pool is not None:
        # Workers hold open Stockfish processes (and their threads) - a regular pool shutdown would wait
        # for them forever. The result is already written, so we simply terminate the workers.
        for process in list(getattr(pool, "_processes", {}).values()):
            process.terminate()
        pool.shutdown(wait=False, cancel_futures=True)
        os._exit(0)


if __name__ == "__main__":
    main()
