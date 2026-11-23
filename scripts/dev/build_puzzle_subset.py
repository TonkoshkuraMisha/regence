# --- FILE: scripts/dev/build_puzzle_subset.py ---
"""
Selection of puzzles from the open lichess database (task 13.1) -> data/puzzles/lichess_subset.csv.gz.

The database: https://database.lichess.org/#puzzles (lichess_db_puzzle.csv.zst, licence CC0). The script reads it as a stream
and selects good-quality puzzles (stable rating, high popularity, many plays) so that:
* the rating 600-2600 is covered evenly - 20 buckets of 100 points, ``--per-bucket`` puzzles in each;
* every tag that the theme registry (src/services/themes.py) maps to its own theme has at least ``--per-tag-stage`` puzzles
  (as many as can be found) at every stage (task 13.4, ``stage_for``) - rare themes and easy stages are not
  drowned among the frequent ones.

Where there are not enough good-quality puzzles (a rare tag at an easy stage), the quota is topped up from puzzles with a soft
filter (``acceptable``): popularity >= 70, >= 100 plays, rating deviation <= 90.

The selection is deterministic (``--seed``): a re-run on the same database gives the same selection. The zstandard package
is needed (only for this script; the server does not use it). Not run in CI.

    python -m scripts.dev.build_puzzle_subset path/to/lichess_db_puzzle.csv.zst
"""

import argparse
import csv
import gzip
import io
import pathlib
import random
import sys

from src.services.puzzle_import import stage_for
from src.services.themes import LICHESS_TAG_TO_THEMES

OUTPUT = pathlib.Path(__file__).resolve().parents[2] / "data" / "puzzles" / "lichess_subset.csv.gz"
FIELDS = ("PuzzleId", "FEN", "Moves", "Rating", "RatingDeviation", "Popularity", "NbPlays", "Themes")
RATING_MIN, RATING_MAX, BUCKET = 600, 2600, 100


def acceptable(row: dict) -> bool:
    """Soft filter - only to top up rare themes and stages."""
    return (int(row["RatingDeviation"]) <= 90 and int(row["Popularity"]) >= 70 and int(row["NbPlays"]) >= 100
            and RATING_MIN <= int(row["Rating"]) < RATING_MAX)


def good(row: dict) -> bool:
    """Checks whether a puzzle passes the main quality and popularity filter."""
    return (int(row["RatingDeviation"]) <= 80 and int(row["Popularity"]) >= 85 and int(row["NbPlays"]) >= 300
            and RATING_MIN <= int(row["Rating"]) < RATING_MAX)


class Reservoir:
    """Uniform random sample of fixed size from a stream (algorithm R)."""

    def __init__(self, size: int, rng: random.Random):
        """Initialises the reservoir of a uniform random sample of fixed size."""
        self.size, self.rng, self.seen, self.items = size, rng, 0, []

    def offer(self, item: dict) -> None:
        """Adds an element to the reservoir with uniform replacement probability."""
        self.seen += 1
        if len(self.items) < self.size:
            self.items.append(item)
        else:
            index = self.rng.randrange(self.seen)
            if index < self.size:
                self.items[index] = item


def main() -> None:
    """Builds a balanced puzzle selection from the full lichess dump."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=pathlib.Path)
    parser.add_argument("--per-bucket", type=int, default=900)
    parser.add_argument("--per-tag-stage", type=int, default=45)
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()

    import zstandard  # only for building the selection

    rng = random.Random(args.seed)
    buckets = {low: Reservoir(args.per_bucket, rng) for low in range(RATING_MIN, RATING_MAX, BUCKET)}
    tags = {(tag, stage): Reservoir(args.per_tag_stage, rng) for tag in LICHESS_TAG_TO_THEMES for stage in (1, 2, 3, 4)}
    spare = {key: Reservoir(args.per_tag_stage, rng) for key in tags}
    total = kept = 0
    with args.source.open("rb") as raw:
        text = io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(raw), encoding="utf-8")
        for row in csv.DictReader(text):
            total += 1
            if not good(row):
                if acceptable(row):
                    item = {field: row[field] for field in FIELDS}
                    stage = stage_for(int(row["Rating"]), row["Moves"].split())
                    for tag in row["Themes"].split():
                        if (tag, stage) in spare:
                            spare[(tag, stage)].offer(item)
                continue
            kept += 1
            item = {field: row[field] for field in FIELDS}
            buckets[(int(row["Rating"]) - RATING_MIN) // BUCKET * BUCKET + RATING_MIN].offer(item)
            stage = stage_for(int(row["Rating"]), row["Moves"].split())
            for tag in row["Themes"].split():
                if (tag, stage) in tags:
                    tags[(tag, stage)].offer(item)

    # Incomplete quotas - topped up from the soft filter.
    for key, reservoir in tags.items():
        missing = args.per_tag_stage - len(reservoir.items)
        if missing > 0:
            reservoir.items.extend(spare[key].items[:missing])

    chosen: dict[str, dict] = {}
    for reservoir in [*tags.values(), *buckets.values()]:
        for item in reservoir.items:
            chosen.setdefault(item["PuzzleId"], item)
    rows = sorted(chosen.values(), key=lambda r: r["PuzzleId"])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Read {total}, pass quality {kept}, in the selection {len(rows)} -> {OUTPUT}", file=sys.stderr)
    thin = {f"{tag}/{stage}": len(r.items) for (tag, stage), r in tags.items() if len(r.items) < args.per_tag_stage}
    if thin:
        print(f"Incomplete quotas (tag/stage: found): {thin}", file=sys.stderr)


if __name__ == "__main__":
    main()
