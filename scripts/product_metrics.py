# --- FILE: scripts/product_metrics.py ---
"""
Owner's report on product metrics (task 23.5): registrations, activation and retention - from our own database,
without third-party trackers.

    python scripts/product_metrics.py            # cohorts for the last 30 days
    python scripts/product_metrics.py --days 90

Activation - the share of new players who played a first game within 5 minutes and within the first day after registration
(the beta target is above 60 % within 5 min). Retention D1/D7/D30 - the share of the cohort active exactly 1, 7, 30 days later
(the target is 35 % / 15 % / 7 %); for fresh cohorts whose day has not come yet, "…" is shown instead of a share.
"""

import argparse
import asyncio
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.services.product_metrics import RETENTION_DAYS, Report, build_report, utc_today  # noqa: E402


def _share(part: int, whole: int) -> str:
    """Formats a count and a share as a percentage of the total number of players."""
    return f"{100 * part / whole:5.1f}%" if whole else "    —"


def render(report: Report) -> str:
    """Builds the product metrics report: activation, retention and reach."""
    today = utc_today()
    header = f"{'cohort':<12}{'reg.':>6}{'≤5 min':>9}{'≤day':>9}" + "".join(f"{'D' + str(n):>8}" for n in RETENTION_DAYS)
    lines = [header, "-" * len(header)]
    totals = {"registered": 0, "fast": 0, "day": 0}
    retained_totals = {n: [0, 0] for n in RETENTION_DAYS}  # [returned, could have returned]
    for cohort in report.cohorts:
        if cohort.registered == 0:
            continue
        totals["registered"] += cohort.registered
        totals["fast"] += cohort.activated_fast
        totals["day"] += cohort.activated_day
        cells = []
        for n in RETENTION_DAYS:
            if cohort.day + timedelta(days=n) > today:
                cells.append(f"{'…':>8}")
                continue
            retained_totals[n][0] += cohort.retained[n]
            retained_totals[n][1] += cohort.registered
            cells.append(f"{_share(cohort.retained[n], cohort.registered):>8}")
        lines.append(
            f"{cohort.day.isoformat():<12}{cohort.registered:>6}"
            f"{_share(cohort.activated_fast, cohort.registered):>9}{_share(cohort.activated_day, cohort.registered):>9}"
            + "".join(cells)
        )
    lines.append("-" * len(header))
    lines.append(
        f"{'total':<12}{totals['registered']:>6}{_share(totals['fast'], totals['registered']):>9}"
        f"{_share(totals['day'], totals['registered']):>9}"
        + "".join(f"{_share(*retained_totals[n]):>8}" for n in RETENTION_DAYS)
    )
    lines.append("")
    lines.append(f"Players with events over all time: {report.total_users}. Reached the section:")
    names = {"game_finished": "game", "puzzle_attempt": "puzzle", "lesson_completed": "lesson",
             "tournament_created": "tournament"}
    for kind, count in report.reached.items():
        lines.append(f"  {names.get(kind, kind):<8} {count:>6}  {_share(count, report.total_users)}")
    return "\n".join(lines)


async def main(days: int) -> None:
    """Reads events from product_events and prints an analytical summary."""
    from src.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        report = await build_report(db, since=utc_today() - timedelta(days=days - 1))
    print(render(report))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=30, help="How many of the latest days of cohorts to show")
    asyncio.run(main(parser.parse_args().days))
