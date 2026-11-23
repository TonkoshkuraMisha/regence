# --- FILE: src/services/feed.py ---
"""
Feed and posts (task 30.2): a player shares a game, a position (their own analysis -- text attached), a puzzle, a lesson,
a tournament, a library game or an achievement; the subscription feed (own posts and those of followed players), the
player's feed in the profile, comments and "like" marks.

Rules: a chat ban by a moderator also closes posts and comments; one cannot comment on a player who put
you on their block list (refusal comment_closed without mentioning the block -- like dm_closed for direct messages: the block
is not revealed); posts of players I blocked are not shown in my feed; a post hidden by a moderator or held back by the
filter is visible only to its author; posts and comments of deleted accounts are not shown. A new
comment on a post is a notification to the author (except own and held-back comments).

Tables: posts, post_comments, post_likes; subscriptions -- follows, block list -- blocks. Attachment cards --
src/services/attachments.py, filter and quotas -- src/services/civility.py, chat ban -- src/services/moderation.py.
"""

from collections.abc import Sequence

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.errors import DomainError
from src.models.social import Block, Follow, Post, PostComment, PostLike
from src.models.user import User
from src.services import civility, moderation, notifications
from src.services.attachments import POST_KINDS, build_attachment, clean_text

# Maximum length of a post and comment text in characters (the excess is truncated).
BODY_MAX = 2000
COMMENT_MAX = 500
# How many posts one feed page returns and how many comments are shown on a post.
PAGE = 20
COMMENTS_PAGE = 100


def _iso(value) -> str | None:
    return value.isoformat() if value else None


async def _views(db: AsyncSession, posts: Sequence[Post], viewer: User | None) -> list[dict]:
    """
    Posts for the client: author, text, card, the number of "likes" and comments (without held-back ones),
    whether the viewer themselves liked it, whether it is their own post, whether it is hidden or held back.
    """
    if not posts:
        return []
    ids = [p.id for p in posts]
    likes = dict((await db.execute(
        select(PostLike.post_id, func.count()).where(PostLike.post_id.in_(ids)).group_by(PostLike.post_id))).tuples().all())
    comments = dict((await db.execute(
        select(PostComment.post_id, func.count()).where(PostComment.post_id.in_(ids), PostComment.held.is_(False))
        .group_by(PostComment.post_id))).tuples().all())
    liked: set[int] = set()
    if viewer is not None:
        liked = set((await db.execute(select(PostLike.post_id).where(
            PostLike.post_id.in_(ids), PostLike.user_id == viewer.id))).scalars().all())
    authors = {u.id: u for u in (await db.execute(
        select(User).where(User.id.in_({p.author_id for p in posts})))).scalars().all()}
    out = []
    for p in posts:
        author = authors.get(p.author_id)
        out.append({"id": p.id, "author": author.username if author else None,
                    "avatar": author.avatar if author else None, "body": p.body, "attachment": p.attachment,
                    "created_at": _iso(p.created_at), "likes": likes.get(p.id, 0), "liked": p.id in liked,
                    "comments": comments.get(p.id, 0), "mine": viewer is not None and p.author_id == viewer.id,
                    "hidden": p.hidden_at is not None, "held": p.held})
    return out


def _visible(viewer: User | None):
    """Posts hidden by a moderator and held back by the filter -- only to the author."""
    public = and_(Post.hidden_at.is_(None), Post.held.is_(False))
    if viewer is None:
        return public
    return or_(public, Post.author_id == viewer.id)


def _not_deleted_author():
    return select(User.id).where(User.deleted_at.is_(None))


async def create(db: AsyncSession, author: User, body: str | None, attachment: tuple[str, str] | None,
                 send_anyway: bool = False) -> dict:
    """
    A new post: text and/or a card attachment. Forbidden when chat is disabled; the quota and the abuse filter
    apply (if triggered -- without send_anyway the refusal text_flagged, with it the post is held back until the
    moderator decides). Refusals: posting_banned, post_empty, posting_limited.
    """
    if moderation.chat_banned(author):
        raise DomainError("posting_banned")
    text = clean_text(body, BODY_MAX)
    card = await build_attachment(db, *attachment, author=author, kinds=POST_KINDS) if attachment else None
    if not text and card is None:
        raise DomainError("post_empty")
    await civility.check_quota(db, author, "post")
    held = civility.screen(text, send_anyway)
    post = Post(author_id=author.id, body=text, attachment=card, held=held)
    db.add(post)
    await db.flush()
    if held:
        await civility.hold(db, author.id, f"post:{post.id}", text)
    await db.commit()
    await db.refresh(post)
    return (await _views(db, [post], author))[0]


async def _page(db: AsyncSession, query, viewer: User | None, before_id: int | None) -> list[dict]:
    """A feed page: PAGE posts visible to the viewer, newest first; before_id -- posts older than this."""
    if before_id:
        query = query.where(Post.id < before_id)
    rows = (await db.execute(query.where(_visible(viewer), Post.author_id.in_(_not_deleted_author()))
                             .order_by(Post.id.desc()).limit(PAGE))).scalars().all()
    return await _views(db, rows, viewer)


async def following_feed(db: AsyncSession, viewer: User, before_id: int | None = None) -> list[dict]:
    """The subscription feed: own posts and posts of those the viewer follows, except those blocked by them."""
    followed = select(Follow.followee_id).where(Follow.follower_id == viewer.id)
    blocked = select(Block.blocked_id).where(Block.blocker_id == viewer.id)
    query = select(Post).where(or_(Post.author_id == viewer.id, Post.author_id.in_(followed)),
                               Post.author_id.not_in(blocked))
    return await _page(db, query, viewer, before_id)


async def user_feed(db: AsyncSession, author: User, viewer: User | None, before_id: int | None = None) -> list[dict]:
    """One player's feed -- for their profile; the viewer may be a guest (viewer=None)."""
    return await _page(db, select(Post).where(Post.author_id == author.id), viewer, before_id)


async def _post(db: AsyncSession, post_id: int, viewer: User | None) -> Post:
    """The post if the viewer may see it; otherwise post_not_found -- as if it did not exist."""
    post = await db.scalar(select(Post).where(Post.id == post_id, _visible(viewer),
                                              Post.author_id.in_(_not_deleted_author())))
    if post is None:
        raise DomainError("post_not_found")
    return post


async def get(db: AsyncSession, post_id: int, viewer: User | None) -> dict:
    return (await _views(db, [await _post(db, post_id, viewer)], viewer))[0]


async def remove(db: AsyncSession, post_id: int, viewer: User) -> None:
    """Deleting a post by its author or a moderator; for everyone else -- the same refusal post_not_found."""
    post = await _post(db, post_id, viewer)
    if post.author_id != viewer.id and not viewer.is_moderator:
        raise DomainError("post_not_found")
    await db.delete(post)
    await db.commit()


async def set_like(db: AsyncSession, post_id: int, viewer: User, liked: bool) -> dict:
    """Set or remove a "like"; a repeat changes nothing. Returns the post with the new counter."""
    post = await _post(db, post_id, viewer)
    exists = await db.scalar(select(PostLike.id).where(PostLike.post_id == post.id, PostLike.user_id == viewer.id))
    if liked and exists is None:
        db.add(PostLike(post_id=post.id, user_id=viewer.id))
        await db.commit()
    elif not liked and exists is not None:
        await db.execute(delete(PostLike).where(PostLike.id == exists))
        await db.commit()
    return (await _views(db, [post], viewer))[0]


def _comment_view(c: PostComment, author: User | None, viewer: User | None, post: Post) -> dict:
    can_delete = viewer is not None and (c.author_id == viewer.id or post.author_id == viewer.id or viewer.is_moderator)
    return {"id": c.id, "author": author.username if author else None, "body": c.body,
            "created_at": _iso(c.created_at), "mine": viewer is not None and c.author_id == viewer.id,
            "can_delete": can_delete, "held": c.held}


async def comments(db: AsyncSession, post_id: int, viewer: User | None) -> list[dict]:
    """
    Comments on a post from oldest to newest, no more than COMMENTS_PAGE. A comment held back by the filter is visible only to
    its author; comments of deleted accounts are not shown.
    """
    post = await _post(db, post_id, viewer)
    rows = (await db.execute(select(PostComment, User).join(User, User.id == PostComment.author_id)
                             .where(PostComment.post_id == post.id, User.deleted_at.is_(None),
                                    or_(PostComment.held.is_(False), PostComment.author_id == (viewer.id if viewer else 0)))
                             .order_by(PostComment.id).limit(COMMENTS_PAGE))).all()
    return [_comment_view(c, u, viewer, post) for c, u in rows]


async def add_comment(db: AsyncSession, post_id: int, viewer: User, body: str | None,
                      send_anyway: bool = False) -> tuple[dict, tuple[int, dict] | None]:
    """
    The comment and (if the writer is not the author) (the author, the recorded notification) -- delivery is done by the API
    after the commit.
    A comment held back by the filter gives no notification. Refusals: posting_banned (chat ban), comment_closed
    (the post's author blocked the writer), comment_empty, posting_limited (quota), text_flagged (filter).
    """
    post = await _post(db, post_id, viewer)
    if moderation.chat_banned(viewer):
        raise DomainError("posting_banned")
    blocked = await db.scalar(select(Block.id).where(Block.blocker_id == post.author_id, Block.blocked_id == viewer.id))
    if blocked is not None:
        raise DomainError("comment_closed")
    text = clean_text(body, COMMENT_MAX)
    if not text:
        raise DomainError("comment_empty")
    await civility.check_quota(db, viewer, "comment")
    held = civility.screen(text, send_anyway)
    comment = PostComment(post_id=post.id, author_id=viewer.id, body=text, held=held)
    db.add(comment)
    await db.flush()
    note = None
    if held:
        await civility.hold(db, viewer.id, f"comment:{comment.id}", text)
    elif post.author_id != viewer.id:
        note = (post.author_id, await notifications.record(db, post.author_id, "post_comment",
                                                           {"from": viewer.username, "post_id": post.id}, commit=False))
    await db.commit()
    await db.refresh(comment)
    return _comment_view(comment, viewer, viewer, post), note


async def remove_comment(db: AsyncSession, comment_id: int, viewer: User) -> None:
    """Deleting a comment -- by its author, the post's author or a moderator."""
    row = (await db.execute(select(PostComment, Post).join(Post, Post.id == PostComment.post_id)
                            .where(PostComment.id == comment_id))).first()
    if row is None:
        raise DomainError("comment_not_found")
    comment, post = row
    if viewer.id not in (comment.author_id, post.author_id) and not viewer.is_moderator:
        raise DomainError("comment_not_found")
    await db.delete(comment)
    await db.commit()
