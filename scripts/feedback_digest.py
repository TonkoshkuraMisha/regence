# --- FILE: scripts/feedback_digest.py ---
"""
Weekly review of beta feedback (task 24.4): a summary of "Report a problem" messages in a form ready for ToDo.md.

    python scripts/feedback_digest.py                       # the last 7 days, to the console
    python scripts/feedback_digest.py --days 14
    python scripts/feedback_digest.py --until 2026-11-16    # the week before this date (not including it)
    python scripts/feedback_digest.py --output digest.md    # to a file (UTF-8)

The block is pasted into ToDo.md as is: unreviewed messages as "- [ ]" items, from which plan changes come;
those closed in the period as "- [x]". Message statuses are changed by a moderator on the /moderation page.
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.services.beta import OPEN_STATUSES, Digest, DigestItem  # noqa: E402

STATUS_NAMES = {"new": "new", "in_progress": "in progress", "done": "done", "rejected": "rejected"}
MESSAGE_WIDTH = 240


def _line(item: DigestItem) -> str:
    """Formats one feedback entry as a Markdown list line."""
    text = " / ".join(part.strip() for part in item.message.splitlines() if part.strip())
    if len(text) > MESSAGE_WIDTH:
        text = text[:MESSAGE_WIDTH - 1].rstrip() + "…"
    details = [item.author or "guest", item.language, item.screen, f"v{item.app_version}" if item.app_version else None]
    meta = ", ".join(part for part in details if part)
    if item.status == "in_progress":
        meta += "; in progress"
    elif item.status == "rejected":
        meta += "; rejected"
    mark = " " if item.status in OPEN_STATUSES else "x"
    page = f" `{item.page}`" if item.page else ""
    return f"- [{mark}] #{item.id}{page} — {text} ({meta})"


def render(digest: Digest) -> str:
    """Builds a text summary of beta feedback by status and section."""
    last_day = (digest.until - timedelta(microseconds=1)).date()
    lines = [f"### Beta feedback: {digest.since.date():%d.%m} – {last_day:%d.%m.%Y}", ""]
    if digest.items:
        counts = ", ".join(f"{name} {digest.by_status.get(status, 0)}" for status, name in STATUS_NAMES.items())
        lines.append(f"* Received {len(digest.items)}: {counts}. Unreviewed in total: {digest.backlog}.")
        pages = ", ".join(f"{'no page' if page == '?' else f'`{page}`'} — {count}" for page, count in digest.by_page)
        lines.append(f"* By section: {pages}.")
    else:
        lines.append(f"* No messages this week. Unreviewed in total: {digest.backlog}.")
    lines.append(f"* Invitations: {digest.invited} arrived by codes, {digest.active_invites} active codes.")
    for title, wanted in (("To review:", True), ("Closed in the period:", False)):
        chosen = [item for item in digest.items if (item.status in OPEN_STATUSES) is wanted]
        if chosen:
            lines += ["", title, *(_line(item) for item in chosen)]
    return "\n".join(lines) + "\n"


async def main(days: int, until: datetime) -> str:
    """Loads feedback from the DB and prints a digest for the work plan."""
    from src.db.session import AsyncSessionLocal
    from src.services.beta import build_digest

    async with AsyncSessionLocal() as db:
        return render(await build_digest(db, until - timedelta(days=days), until))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=7, help="Period length in days")
    parser.add_argument("--until", type=lambda value: datetime.fromisoformat(value).replace(tzinfo=UTC), default=None,
                        help="End of the period (YYYY-MM-DD, not including this day); default - now")
    parser.add_argument("--output", type=Path, default=None, help="Write to a file instead of the console")
    args = parser.parse_args()
    digest_text = asyncio.run(main(args.days, args.until or datetime.now(UTC)))
    if args.output is None:
        print(digest_text, end="")
    else:
        args.output.write_text(digest_text, encoding="utf-8", newline="\n")
        print(f"Summary written to {args.output}")
