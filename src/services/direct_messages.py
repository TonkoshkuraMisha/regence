# --- FILE: src/services/direct_messages.py ---
"""
Direct messages (task 30.1): a conversation between two players, card attachments, the "who can message me" setting and a
block list. The message text is player input; the server stores no interface strings: an attachment card is a kind code (kind),
a reference (ref) and a snapshot of the data at send time (player names, result, puzzle rating); captions are assembled by
the client.

Delivery to open tabs is the WebSocket event "direct_message" after the write and commit (the WebSocket rule: network --
after releasing the database; this is HTTP, but the order is the same: the message is already in the database, delivery is
best effort). send
only writes the message; deliver is called after it by the route (src/api/messages.py).

Tables: direct_messages (messages; pair_key is the conversation key of two players), blocks (block list),
hidden_conversations (hidden conversations), follows (for the setting "only those I follow may write to me");
the recipient's setting is users.dm_policy. The abuse filter and quotas are in src/services/civility.py, the chat ban is in
src/services/moderation.py.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainError
from src.models.social import Block, DirectMessage, Follow, HiddenConversation
from src.models.user import User
from src.services import civility, moderation
from src.services.attachments import build_attachment, clean_text

logger = logging.getLogger(__name__)

# Values of the "who can message me" setting (users.dm_policy): everyone, only those I follow, nobody.
POLICIES = ("all", "following", "nobody")
# Maximum message text length in characters (the excess is truncated).
BODY_MAX = 1000
# How many messages of a conversation are returned per request and how many correspondents are in the conversation list.
PAGE = 50
CONVERSATIONS = 50


def pair_key(a: int, b: int) -> str:
    """The conversation key of two players, the same in both directions: "smaller id:larger id"."""
    low, high = sorted((a, b))
    return f"{low}:{high}"


def clean_body(text: str | None) -> str:
    return clean_text(text, BODY_MAX)


async def is_blocked(db: AsyncSession, blocker_id: int, blocked_id: int) -> bool:
    found = await db.scalar(select(Block.id).where(Block.blocker_id == blocker_id, Block.blocked_id == blocked_id))
    return found is not None


async def check_write(db: AsyncSession, sender: User, recipient: User) -> None:
    """Whether sender may write to recipient; if not -- a DomainError with the reason code. The recipient's block list
    answers with the same dm_closed as a closed setting: a blocked user does not learn that they were blocked.
    Other codes: cannot_message_self; dm_chat_banned -- the sender has a chat ban from a moderator; dm_you_blocked --
    the sender blocked the recipient themselves. The following setting lets through only those the recipient follows."""
    if sender.id == recipient.id:
        raise DomainError("cannot_message_self")
    if moderation.chat_banned(sender):
        raise DomainError("dm_chat_banned")
    if await is_blocked(db, sender.id, recipient.id):
        raise DomainError("dm_you_blocked")
    policy = recipient.dm_policy or "all"
    closed = policy == "nobody" or await is_blocked(db, recipient.id, sender.id)
    if not closed and policy == "following":
        closed = await db.scalar(select(Follow.id).where(Follow.follower_id == recipient.id,
                                                         Follow.followee_id == sender.id)) is None
    if closed:
        raise DomainError("dm_closed")


async def write_refusal(db: AsyncSession, sender: User, recipient: User) -> str | None:
    """None -- may write; otherwise the reason code."""
    try:
        await check_write(db, sender, recipient)
    except DomainError as exc:
        return exc.code
    return None


def view(message: DirectMessage, me_id: int) -> dict:
    """
    A message for the client through the eyes of player me_id: own or foreign, text, card, whether read, whether held back.
    """
    created = message.created_at.isoformat() if message.created_at else None
    return {"id": message.id, "mine": message.sender_id == me_id, "body": message.body,
            "attachment": message.attachment, "created_at": created, "read": message.read_at is not None,
            "held": message.held}


def _seen_by(me_id: int):
    """A message held back by the filter is seen only by the sender (task 30.3)."""
    return or_(DirectMessage.held.is_(False), DirectMessage.sender_id == me_id)


async def send(db: AsyncSession, sender: User, recipient: User, body: str | None,
               attachment: tuple[str, str] | None, send_anyway: bool = False) -> DirectMessage:
    """
    Sending a direct message: the right to write (the recipient's setting, block list), text and/or a card attachment,
    quota, abuse filter (if triggered -- without send_anyway the refusal text_flagged, with it the message is held back and
    goes
    to a moderator for review), writing to the database. An empty message without a card -- dm_empty. Delivery to open tabs
    is done by the separate deliver call.
    """
    await check_write(db, sender, recipient)
    text = clean_body(body)
    card = await build_attachment(db, *attachment, author=sender) if attachment else None
    if not text and card is None:
        raise DomainError("dm_empty")
    await civility.check_quota(db, sender, "dm")
    held = civility.screen(text, send_anyway)
    message = DirectMessage(pair_key=pair_key(sender.id, recipient.id), sender_id=sender.id,
                            recipient_id=recipient.id, body=text, attachment=card, held=held)
    db.add(message)
    await db.flush()
    if held:
        await civility.hold(db, sender.id, f"dm:{message.id}", text)
    await db.commit()
    await db.refresh(message)
    return message


async def deliver(message: DirectMessage, sender_name: str) -> None:
    """The recipient's open tabs; a held-back message is not delivered."""
    if message.held:
        return
    try:
        from src.services.connection_manager import manager

        payload = view(message, message.recipient_id)
        await manager.send_personal_message({"event": "direct_message", "from": sender_name, "message": payload},
                                            message.recipient_id)
    except Exception as exc:  # the message is already written -- a delivery failure is not critical
        logger.warning("Direct message delivery failed for user %s: %s", message.recipient_id, exc)


async def thread(db: AsyncSession, me: User, other: User, before_id: int | None = None) -> list[dict]:
    """The last PAGE messages of a conversation (older first); before_id -- an earlier page."""
    query = select(DirectMessage).where(DirectMessage.pair_key == pair_key(me.id, other.id), _seen_by(me.id))
    if before_id:
        query = query.where(DirectMessage.id < before_id)
    rows = (await db.execute(query.order_by(DirectMessage.id.desc()).limit(PAGE))).scalars().all()
    return [view(m, me.id) for m in reversed(rows)]


async def mark_read(db: AsyncSession, me: User, other: User) -> None:
    """Marks as read all messages from the correspondent other addressed to me (except held-back ones); with commit."""
    await db.execute(update(DirectMessage).where(
        DirectMessage.pair_key == pair_key(me.id, other.id), DirectMessage.recipient_id == me.id,
        DirectMessage.held.is_(False), DirectMessage.read_at.is_(None)).values(read_at=datetime.now(UTC)))
    await db.commit()


def _unread_for(me_id: int):
    return (DirectMessage.recipient_id == me_id, DirectMessage.read_at.is_(None), DirectMessage.held.is_(False))


async def unread_total(db: AsyncSession, me_id: int) -> int:
    """The number of a player's unread messages; held-back messages and messages from hidden conversations do not count."""
    hidden = select(HiddenConversation.other_id).where(HiddenConversation.user_id == me_id,
                                                       HiddenConversation.up_to_id >= DirectMessage.id,
                                                       HiddenConversation.other_id == DirectMessage.sender_id)
    return await db.scalar(select(func.count()).select_from(DirectMessage).where(
        *_unread_for(me_id), ~hidden.exists())) or 0


async def conversations(db: AsyncSession, me: User) -> list[dict]:
    """Correspondents: last message, how many unread; freshest first. Conversations I hid
    are not shown until the correspondent writes again. The CONVERSATIONS freshest conversations are taken; correspondents
    with a
    deleted account are skipped; blocked -- whether I blocked the correspondent."""
    mine = or_(DirectMessage.sender_id == me.id, DirectMessage.recipient_id == me.id)
    last_ids = (await db.execute(
        select(func.max(DirectMessage.id)).where(mine, _seen_by(me.id)).group_by(DirectMessage.pair_key)
        .order_by(func.max(DirectMessage.id).desc()).limit(CONVERSATIONS)
    )).scalars().all()
    if not last_ids:
        return []
    lasts = (await db.execute(select(DirectMessage).where(DirectMessage.id.in_(last_ids))
                              .order_by(DirectMessage.id.desc()))).scalars().all()
    unread: dict[int, int] = {sender: count for sender, count in (await db.execute(
        select(DirectMessage.sender_id, func.count()).where(*_unread_for(me.id)).group_by(DirectMessage.sender_id)
    )).all()}
    others = {m.recipient_id if m.sender_id == me.id else m.sender_id for m in lasts}
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(others)))).scalars().all()}
    blocked = set((await db.execute(select(Block.blocked_id).where(
        Block.blocker_id == me.id, Block.blocked_id.in_(others)))).scalars().all())
    hidden: dict[int, int] = {other: up_to for other, up_to in (await db.execute(
        select(HiddenConversation.other_id, HiddenConversation.up_to_id).where(HiddenConversation.user_id == me.id)
    )).all()}
    out = []
    for m in lasts:
        other_id = m.recipient_id if m.sender_id == me.id else m.sender_id
        other = users.get(other_id)
        if other is None or other.deleted_at is not None or m.id <= hidden.get(other_id, 0):
            continue
        out.append({"username": other.username, "avatar": other.avatar, "last": view(m, me.id),
                    "unread": unread.get(other_id, 0), "blocked": other_id in blocked})
    return out


async def hide_conversation(db: AsyncSession, me: User, other: User) -> None:
    """
    Hide a conversation until the correspondent's next message; unread messages in it count as read. In
    hidden_conversations the number of the last message is remembered: the conversation is hidden while there are no newer
    messages.
    """
    last = await db.scalar(select(func.max(DirectMessage.id)).where(DirectMessage.pair_key == pair_key(me.id, other.id)))
    if last is None:
        return
    row = await db.scalar(select(HiddenConversation).where(HiddenConversation.user_id == me.id,
                                                           HiddenConversation.other_id == other.id))
    if row is None:
        db.add(HiddenConversation(user_id=me.id, other_id=other.id, up_to_id=last))
    else:
        row.up_to_id = last
    await db.flush()
    await mark_read(db, me, other)

async def block(db: AsyncSession, me: User, other: User) -> None:
    """Adds other to my block list (a repeat call changes nothing); myself -- refusal cannot_block_self."""
    if me.id == other.id:
        raise DomainError("cannot_block_self")
    if not await is_blocked(db, me.id, other.id):
        db.add(Block(blocker_id=me.id, blocked_id=other.id))
        await db.commit()


async def unblock(db: AsyncSession, me: User, other: User) -> None:
    await db.execute(delete(Block).where(Block.blocker_id == me.id, Block.blocked_id == other.id))
    await db.commit()


async def blocked_list(db: AsyncSession, me: User) -> list[str]:
    rows = await db.execute(select(User.username).join(Block, Block.blocked_id == User.id)
                            .where(Block.blocker_id == me.id).order_by(User.username))
    return list(rows.scalars().all())
