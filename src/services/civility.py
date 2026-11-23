# --- FILE: src/services/civility.py ---
"""
Respectful communication (task 30.3): an insult filter before sending, limits for newcomers and offenders, holding.

The filter: the text is normalised (case, "digits instead of letters", Latin lookalikes in a Cyrillic
word, repeated
letters) and checked against the dictionary civility_lexicon.txt. If it fires, the client receives text_flagged and offers to
rewrite;
if the player still sends (send_anyway), the text is saved as held (held): only the author sees it, and a
report kind="held" goes to the moderator queue. Automation only marks and holds — the moderator decides
(release — let it out, hide — remove).

Limits: a newcomer (account younger than NEWCOMER_DAYS) and an offender (within the last VIOLATOR_DAYS a moderator ruled
warn, chat_ban or hide on a complaint against them) send no more than QUOTAS[scope] per hour.

Data source: the dictionary and character replacement tables are the file civility_lexicon.txt next to the module (read once
per
process; the format is described at its start); penalties — the reports table; the count sent in an hour — direct_messages,
posts and post_comments. Callers: src/services/direct_messages.py and src/services/feed.py.
"""

import re
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainError
from src.models.moderation import Report
from src.models.social import DirectMessage, Post, PostComment
from src.models.user import User

LEXICON = Path(__file__).with_name("civility_lexicon.txt")
# An account younger than this many days is considered a newcomer — limits apply to it.
NEWCOMER_DAYS = 3
# For how many days after a moderator's penalty a player is considered an offender (limits apply).
VIOLATOR_DAYS = 30
# Newcomer and offender limits — sends per hour: direct messages, comments, feed posts.
QUOTAS = {"dm": 20, "comment": 10, "post": 3}
# Moderator decisions on a complaint (reports.action) after which the player is considered an offender.
PENALTIES = ("warn", "chat_ban", "hide")

# A word of text: letters, digits, underscore and the signs @ and $ (they are used to replace letters, the dictionary's leet
# table).
_TOKEN = re.compile(r"[\w@$]+")


def _is_cyrillic(token: str) -> bool:
    return any(0x0400 <= ord(ch) <= 0x04FF for ch in token)


def _collapse(word: str) -> str:
    return re.sub(r"(.)\1+", r"\1", word)


@cache
def _source() -> tuple[dict[str, dict[int, str]], list[str]]:
    """Normalisation tables (lines "@name a=b c=d") and dictionary entries — from civility_lexicon.txt: the alphabet letters
    live in the data, not in the server code (rule: src has no Cyrillic strings)."""
    tables: dict[str, dict[int, str]] = {}
    entries: list[str] = []
    for line in LEXICON.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry.startswith("@"):
            name, *pairs = entry[1:].split()
            tables[name] = str.maketrans({src: dst for src, _, dst in (pair.partition("=") for pair in pairs)})
        else:
            entries.append(entry)
    return tables, entries


def _norm_token(token: str) -> str:
    """
    A word in the form for checking against the dictionary: lower case, the optional fold table; in a word with Cyrillic —
    digit-letters
    (leet-cyr) and Latin lookalikes (lookalike), in the others — Latin digit-letters (leet); underscores are removed,
    repeats of one character in a row are collapsed into one.
    """
    tables = _source()[0]
    token = token.lower().translate(tables.get("fold", {}))
    if _is_cyrillic(token):
        token = token.translate(tables.get("leet-cyr", {})).translate(tables.get("lookalike", {}))
    else:
        token = token.translate(tables.get("leet", {}))
    return _collapse(token.replace("_", ""))


def normalize(text: str) -> list[str]:
    """Words of the text after normalisation (_norm_token), in order; punctuation and spaces are dropped."""
    return [t for t in (_norm_token(raw) for raw in _TOKEN.findall(text or "")) if t]


@cache
def _lexicon() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """
    The dictionary parsed by kinds of entries: word beginnings (an entry without a mark), whole words (=word), roots anywhere
    in
    a word (*root) and multi-word phrases. Entries are normalised the same way as the checked text.
    """
    prefixes: list[str] = []
    exact: list[str] = []
    roots: list[str] = []
    phrases: list[str] = []
    for entry in _source()[1]:
        mark = entry[0] if entry[0] in "=*" else ""
        words = normalize(entry.lstrip("=*"))
        if len(words) > 1:
            phrases.append(" ".join(words))
        elif words:
            {"=": exact, "*": roots, "": prefixes}[mark].append(words[0])
    return tuple(prefixes), tuple(exact), tuple(roots), tuple(phrases)

def offensive(text: str | None) -> bool:
    """
    Whether the text contains an insult: words after normalisation are checked against the dictionary — exact words, word
    beginnings, roots and
    phrases.
    """
    tokens = normalize(text or "")
    if not tokens:
        return False
    prefixes, exact, roots, phrases = _lexicon()
    for token in tokens:
        if token in exact or token.startswith(prefixes) or any(root in token for root in roots):
            return True
    joined = f" {' '.join(tokens)} "
    return any(f" {phrase} " in joined for phrase in phrases)


def screen(text: str | None, send_anyway: bool) -> bool:
    """True — hold. Without send_anyway an insulting text is not accepted: suggest rewriting."""
    if not offensive(text):
        return False
    if not send_anyway:
        raise DomainError("text_flagged")
    return True


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def restricted(db: AsyncSession, user: User) -> bool:
    """
    Whether limits apply to a player: the account is younger than NEWCOMER_DAYS or within the last VIOLATOR_DAYS a moderator
    ruled
    a penalty on a complaint against them.
    """
    now = datetime.now(UTC)
    created = _aware(user.created_at)
    if created is not None and created > now - timedelta(days=NEWCOMER_DAYS):
        return True
    penalty = await db.scalar(select(Report.id).where(
        Report.target_id == user.id, Report.status == "resolved", Report.action.in_(PENALTIES),
        Report.resolved_at > now - timedelta(days=VIOLATOR_DAYS)).limit(1))
    return penalty is not None


_SCOPES = {"dm": (DirectMessage.sender_id, DirectMessage.created_at), "post": (Post.author_id, Post.created_at),
           "comment": (PostComment.author_id, PostComment.created_at)}


async def check_quota(db: AsyncSession, user: User, scope: str) -> None:
    """
    Sending limit for a newcomer and an offender: if in the last hour in the section scope ("dm", "post", "comment")
    QUOTAS[scope] has already been sent — a refusal posting_limited. Other players are not affected by the limit.
    """
    if not await restricted(db, user):
        return
    author, created = _SCOPES[scope]
    since = datetime.now(UTC) - timedelta(hours=1)
    sent = await db.scalar(select(func.count()).where(author == user.id, created > since)) or 0
    if sent >= QUOTAS[scope]:
        raise DomainError("posting_limited", limit=QUOTAS[scope])


async def hold(db: AsyncSession, author_id: int, subject: str, text: str) -> None:
    """
    Report to the moderator about a held text (the commit is the caller's): a reports record of kind "held" without a
    complainant,
    stating where the text was written (subject), and its first 300 characters.
    """
    db.add(Report(kind="held", reporter_id=None, target_id=author_id, reason="auto", subject=subject,
                  message_text=(text or "")[:300] or None))
