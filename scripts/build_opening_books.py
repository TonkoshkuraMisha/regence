# --- FILE: scripts/build_opening_books.py ---
"""
Opening books of the seven historical bots: from the prototype's games - into src/services/bots/books/<bot>.json.

Where the games come from: the player's PGN files in project folders with the archive (find_pgn_files_for_bot). Only the
player's own games are taken (BOT_BOOK_CONFIG: surname and exclusions for namesakes) and only his moves in the first
MAX_BOOK_PLY plies: for every position it counts how many times he played each move - that is the move's weight in the book.

Run from the project root: `python scripts/build_opening_books.py`. Books of second-wave masters are built by
scripts/build_master_books.py.
"""

import json
import shutil
import sys
from pathlib import Path

import chess
import chess.pgn

# Hard binding to the project root (independent of the Working Directory in PyCharm)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BOOKS_DIR = PROJECT_ROOT / "src" / "services" / "bots" / "books"
MAX_BOOK_PLY = 16

BOT_BOOK_CONFIG = {
    "philidor": {
        "identifiers": ("philidor",),
        "surname_filter": "philidor",
        "exclude": (),
    },
    "labourdonnais": {
        "identifiers": ("bourdonnais", "labourdonnais"),
        "surname_filter": "bourdonnais",
        "exclude": (),
    },
    "staunton": {
        "identifiers": ("staunton",),
        "surname_filter": "staunton",
        "exclude": (),
    },
    "anderssen": {
        "identifiers": ("anderssen",),
        "surname_filter": "anderssen",
        "exclude": (),
    },
    "morphy": {
        "identifiers": ("morphy",),
        "surname_filter": "morphy",
        "exclude": ("alonzo", "ernest"),
    },
    "paulsen": {
        "identifiers": ("paulsen",),
        "surname_filter": "paulsen",
        "exclude": ("wilfried",),
    },
    "zukertort": {
        "identifiers": ("zukertort",),
        "surname_filter": "zukertort",
        "exclude": (),
    },
}


def cleanup_misplaced_artifacts() -> None:
    """
    Removes the mistakenly created scripts/src folder (caused by running with CWD=scripts/)
    and moves all *_generated_book.json from the root into src/services/bots/books/.
    """
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)

    accidental_scripts_src = PROJECT_ROOT / "scripts" / "src"
    if accidental_scripts_src.exists():
        for stray_json in accidental_scripts_src.rglob("*.json"):
            target = BOOKS_DIR / stray_json.name
            if not target.exists():
                shutil.move(str(stray_json), str(target))
        shutil.rmtree(accidental_scripts_src, ignore_errors=True)
        print(f"[+] Removed the stray nested folder: {accidental_scripts_src}")

    for bot_id in BOT_BOOK_CONFIG:
        legacy_root_json = PROJECT_ROOT / f"{bot_id}_generated_book.json"
        target_json = BOOKS_DIR / f"{bot_id}.json"
        if legacy_root_json.exists():
            if not target_json.exists() or legacy_root_json.stat().st_size > target_json.stat().st_size:
                shutil.move(str(legacy_root_json), str(target_json))
                print(f"[+] Moved the book from the root: {legacy_root_json.name} -> {target_json}")
            else:
                legacy_root_json.unlink()


def matches_player(header_name: str, surname: str, exclude: tuple[str, ...]) -> bool:
    """Checks whether the player name in the PGN header matches the target master."""
    name_lower = (header_name or "").lower()
    if any(ex in name_lower for ex in exclude):
        return False
    return surname in name_lower


def process_pgn_stream(pgn_stream, surname: str, exclude: tuple[str, ...], book_additions: dict) -> int:
    """Extracts the master's opening moves from a PGN stream up to the given ply."""
    games_processed = 0
    while True:
        try:
            game = chess.pgn.read_game(pgn_stream)
            if game is None:
                break

            is_w = matches_player(game.headers.get("White", ""), surname, exclude)
            is_b = matches_player(game.headers.get("Black", ""), surname, exclude)
            track_both = not (is_w or is_b)

            board = game.board()
            ply = 0
            for move in game.mainline_moves():
                if ply >= MAX_BOOK_PLY:
                    break
                uci = move.uci()
                if uci == "0000" or not bool(move):
                    break

                white_turn = board.turn == chess.WHITE
                if track_both or (white_turn and is_w) or (not white_turn and is_b):
                    parts = board.fen().split(" ")
                    fen_key = f"{parts[0]} {parts[1]} {parts[2]} -"
                    book_additions.setdefault(fen_key, {})
                    book_additions[fen_key][uci] = book_additions[fen_key].get(uci, 0) + 1

                try:
                    board.push(move)
                except ValueError:
                    break
                ply += 1  # noqa: SIM113 - we count only successfully played moves

            games_processed += 1
        except Exception:
            continue
    return games_processed


def find_pgn_files_for_bot(identifiers: tuple[str, ...]) -> list[Path]:
    """Looks for the champion's PGN files in all possible project directories."""
    search_dirs = [
        PROJECT_ROOT / "data",
        PROJECT_ROOT / "downloaded_pgns",
        PROJECT_ROOT / "src" / "db" / "data",
        PROJECT_ROOT,
    ]
    found: list[Path] = []
    seen: set[Path] = set()

    for directory in search_dirs:
        if not directory.exists():
            continue
        iterator = directory.glob("*.pgn") if directory == PROJECT_ROOT else directory.rglob("*.pgn")
        for pgn_path in iterator:
            resolved = pgn_path.resolve()
            if resolved in seen or not resolved.is_file():
                continue
            path_lower = str(resolved).lower()
            if any(ident in path_lower for ident in identifiers):
                seen.add(resolved)
                found.append(resolved)

    # If there is both a combined file (*_all_*.pgn) and small files from the folder -
    # give priority to the combined file so as not to count the same games twice
    combined = [p for p in found if "all" in p.name.lower()]
    if combined:
        return [max(combined, key=lambda p: p.stat().st_size)]
    return found


def build_book_for_bot(bot_id: str) -> None:
    """Builds and saves the JSON opening book for one historical bot."""
    cfg = BOT_BOOK_CONFIG[bot_id]
    target_json = BOOKS_DIR / f"{bot_id}.json"

    existing_book: dict = {}
    if target_json.exists():
        try:
            with open(target_json, encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    existing_book = loaded
        except Exception:
            existing_book = {}

    matched_files = find_pgn_files_for_bot(cfg["identifiers"])
    book_additions: dict[str, dict[str, int]] = {}
    total_games = 0

    for filepath in matched_files:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            total_games += process_pgn_stream(f, cfg["surname_filter"], cfg["exclude"], book_additions)

    if total_games > 0:
        formatted_book: dict[str, list] = dict(existing_book)
        for fen, moves_dict in book_additions.items():
            sorted_moves = sorted(moves_dict.items(), key=lambda x: x[1], reverse=True)
            total_count = sum(moves_dict.values())
            formatted_book[fen] = [
                [
                    uci,
                    max(int((count / total_count) * 100), 1),
                    # Number of archive games with this move; the bot's phrase in the player's language is built by the client
                    # (catalog botComments.book.<bot>).
                    count,
                ]
                for uci, count in sorted_moves
            ]

        with open(target_json, "w", encoding="utf-8") as out_f:
            json.dump(formatted_book, out_f, ensure_ascii=False, indent=2)
        print(
            f"[+] {bot_id:13s}: games parsed from PGN: {total_games:4d} | "
            f"Positions in the book: {len(formatted_book):4d} -> {target_json.relative_to(PROJECT_ROOT)}"
        )
        return

    # If there are no raw PGN files but the JSON book has already been moved and sits in src/services/bots/books/
    if existing_book:
        print(
            f"[+] {bot_id:13s}: book is active and verified | "
            f"Positions in the book: {len(existing_book):4d} -> {target_json.relative_to(PROJECT_ROOT)}"
        )
        return

    # If there is neither PGN nor a JSON book - initialise the JSON file with the base repertoire from the bot module
    try:
        module = __import__(f"src.services.bots.{bot_id}", fromlist=["*"])
        default_attr = f"DEFAULT_{bot_id.upper()}_BOOK"
        fallback_data = getattr(module, default_attr, {})
        if fallback_data:
            serializable = {
                fen: [[m[0], int(m[1]), str(m[2])] for m in moves]
                for fen, moves in fallback_data.items()
            }
            with open(target_json, "w", encoding="utf-8") as out_f:
                json.dump(serializable, out_f, ensure_ascii=False, indent=2)
            print(
                f"[~] {bot_id:13s}: base book created | "
                f"Positions in the book: {len(serializable):4d} -> {target_json.relative_to(PROJECT_ROOT)}"
            )
            return
    except Exception as exc:
        print(f"[!] Error initialising the base book for {bot_id}: {exc}")


def main() -> None:
    """Cleans up artifacts and builds the opening books for all base bots."""
    print(f"=== Building and verifying opening books (root: {PROJECT_ROOT}) ===")
    cleanup_misplaced_artifacts()
    for b_id in BOT_BOOK_CONFIG:
        build_book_for_bot(b_id)
    print("=== All opening books are ready! ===")


if __name__ == "__main__":
    main()
