// --- FILE: frontend/src/services/feed.ts ---
// Feed and posts (task 30.2): the subscription feed, a player's posts, a single post with comments, «like».
// All requests go to /api/v1/feed (routes in src/api/feed.py, rules — src/services/feed.py). A player's feed
// (/feed/user/{name}) is visible to a guest too; the rest requires login.

import type {Attachment, AttachmentKind} from './messages';
import {apiRequest} from './http';

/** Post as the server returns it. */
export interface Post {
    id: number;
    author: string | null;
    avatar: string | null;
    body: string;
    /** Attachment card (game, position, puzzle…): a data snapshot saved by the server at publication. */
    attachment: Attachment | null;
    created_at: string | null;
    likes: number;
    /** Whether the viewer liked the post. */
    liked: boolean;
    comments: number;
    mine: boolean;
    /** Hidden by a moderator: the server returns such a post only to its author. */
    hidden: boolean;
    /** Held by the civility filter (30.3): awaiting a moderator's decision. */
    held?: boolean;
}

/** Comment on a post. */
export interface PostComment {
    id: number;
    author: string | null;
    body: string;
    created_at: string | null;
    mine: boolean;
    /** The right to delete is decided by the server (src/services/feed.py). */
    can_delete: boolean;
    held?: boolean;
}

/** Feed page. page — the server page size (feed.PAGE): fewer arrived — there are no more posts. */
export interface FeedPage {
    posts: Post[];
    page: number;
}

/** Request to /api/v1/feed through the shared http.ts wrapper (token, JSON, errors). */
const call = <T>(path: string, init: RequestInit = {}) => apiRequest<T>(`/feed${path}`, init);

/** Load-more parameter: posts older than the one whose id is passed (the feed scrolls back by id). */
const before = (id?: number) => (id ? `?before_id=${id}` : '');

/**
 * Feed endpoints. sendAnyway (send_anyway): the civility filter rejected the text (code text_flagged), the player
 * insists — the text goes to moderator review and stays held (held) until the decision.
 */
export const feedApi = {
    following: (beforeId?: number) => call<FeedPage>(before(beforeId)),
    ofUser: (name: string, beforeId?: number) => call<FeedPage>(`/user/${encodeURIComponent(name)}${before(beforeId)}`),
    create: (body: string, attachment?: { kind: AttachmentKind; ref: string } | null, sendAnyway = false) =>
        call<Post>('', {method: 'POST', body: JSON.stringify({body, attachment: attachment ?? null, send_anyway: sendAnyway})}),
    get: (id: number) => call<{ post: Post; comments: PostComment[] }>(`/posts/${id}`),
    remove: (id: number) => call<{ deleted: boolean }>(`/posts/${id}`, {method: 'DELETE'}),
    like: (id: number, liked: boolean) => call<Post>(`/posts/${id}/like`, {method: liked ? 'POST' : 'DELETE'}),
    comment: (id: number, body: string, sendAnyway = false) =>
        call<PostComment>(`/posts/${id}/comments`, {method: 'POST', body: JSON.stringify({body, send_anyway: sendAnyway})}),
    removeComment: (id: number) => call<{ deleted: boolean }>(`/comments/${id}`, {method: 'DELETE'}),
};
