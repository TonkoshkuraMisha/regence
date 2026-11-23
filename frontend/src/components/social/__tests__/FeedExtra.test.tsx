// The feed and posts, extra paths: loading the next page, deleting one's own post, the filter warning on a
// post and on a comment ("rewrite" and "send for review"), deleting a comment, a feed
// loading error. The network is a fetch stub by address and method.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setToken} from '../../../services/authToken';
import {FeedPage, PostPage, ProfilePosts} from '../FeedPage';

type Call = { url: string; method: string; body: unknown };
type Handler = (call: Call) => unknown;

function stubFetch(handler: Handler) {
    const calls: Call[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
        const call = {url: String(url), method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : null};
        calls.push(call);
        const reply = handler(call);
        const failed = reply instanceof Error;
        return {
            ok: !failed, status: failed ? 422 : 200,
            json: async () => (failed ? {detail: {code: reply.message, params: {}, message: ''}} : reply),
        } as Response;
    }));
    return calls;
}

const post = (id: number, extra: Record<string, unknown> = {}) => ({
    id, author: 'magnus', avatar: null, body: `Post ${id}`, attachment: null, created_at: '2026-11-17T10:00:00Z',
    likes: 0, liked: false, comments: 0, mine: false, hidden: false, ...extra,
});
const comment = (id: number, extra: Record<string, unknown> = {}) =>
    ({id, author: 'bob', body: `Comment ${id}`, created_at: '2026-11-17T10:00:00Z', mine: false, can_delete: false, held: false, ...extra});

function at(path: string) {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route path="/feed" element={<FeedPage/>}/>
                <Route path="/feed/post/:postId" element={<PostPage/>}/>
                <Route path="/profile/:name" element={<ProfilePosts username="magnus"/>}/>
            </Routes>
        </MemoryRouter>,
    );
}

beforeEach(() => setToken('jwt'));
afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe('feed: list', () => {
    it('a full page — "More" loads earlier posts', async () => {
        const first = Array.from({length: 20}, (_, i) => post(100 - i));
        const calls = stubFetch((c) => (c.url.includes('before_id=81') ? {posts: [post(70)], page: 20} : {posts: first, page: 20}));
        at('/feed');
        fireEvent.click(await screen.findByTestId('feed-more'));
        expect(await screen.findByText('Post 70')).toBeInTheDocument();
        expect(calls.some((c) => c.url.includes('before_id=81'))).toBe(true);
        // An incomplete second page — the button is gone.
        expect(screen.queryByTestId('feed-more')).toBeNull();
    });

    it('the server is unavailable — the feed is empty, it does not crash', async () => {
        stubFetch(() => new Error('internal_error'));
        at('/feed');
        expect(await screen.findByTestId('feed-empty')).toBeInTheDocument();
    });

    it('one\'s own post is deleted after confirmation; refusing the confirmation does nothing', async () => {
        const calls = stubFetch((c) => {
            if (c.method === 'DELETE') return {deleted: true};
            return {posts: [post(5, {mine: true})], page: 20};
        });
        const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
        at('/feed');
        fireEvent.click(await screen.findByTestId('feed-delete'));
        expect(calls.some((c) => c.method === 'DELETE')).toBe(false);
        await act(async () => fireEvent.click(screen.getByTestId('feed-delete')));
        expect(confirm).toHaveBeenCalledTimes(2);
        await waitFor(() => expect(screen.queryByTestId('feed-post')).toBeNull());
    });

    it('a player\'s posts in the profile: an empty list — a label', async () => {
        stubFetch(() => ({posts: [], page: 20}));
        at('/profile/magnus');
        expect(await screen.findByTestId('feed-empty')).toBeInTheDocument();
    });
});

describe('feed: filter warning', () => {
    it('a post: "rewrite" closes the warning, "send for review" sends send_anyway', async () => {
        const sent: boolean[] = [];
        stubFetch((c) => {
            if (c.method === 'POST') {
                const anyway = (c.body as { send_anyway: boolean }).send_anyway;
                sent.push(anyway);
                return anyway ? post(9, {body: 'harsh text', held: true, mine: true}) : new Error('text_flagged');
            }
            return {posts: [], page: 20};
        });
        at('/feed');
        fireEvent.change(await screen.findByTestId('feed-input'), {target: {value: 'harsh text'}});
        await act(async () => fireEvent.submit(screen.getByTestId('feed-composer')));
        fireEvent.click(await screen.findByTestId('flagged-rephrase'));
        expect(screen.queryByTestId('flagged-notice')).toBeNull();

        await act(async () => fireEvent.submit(screen.getByTestId('feed-composer')));
        await act(async () => fireEvent.click(await screen.findByTestId('flagged-send-anyway')));
        expect(sent).toEqual([false, false, true]);
        expect(await screen.findByTestId('held-note')).toBeInTheDocument();
    });
});

describe('post page', () => {
    function postHandler(extra: Handler = () => undefined): Handler {
        return (c) => {
            const own = extra(c);
            if (own !== undefined) return own;
            if (c.url.endsWith('/posts/3')) return {post: post(3), comments: [comment(1, {can_delete: true})]};
            return {};
        };
    }

    it('a comment is deleted, the counter decreases', async () => {
        const calls = stubFetch(postHandler((c) => (c.method === 'DELETE' ? {deleted: true} : undefined)));
        at('/feed/post/3');
        await screen.findByTestId('post-comment');
        await act(async () => fireEvent.click(screen.getByRole('button', {name: 'Delete'})));
        expect(calls.some((c) => c.method === 'DELETE' && c.url.endsWith('/comments/1'))).toBe(true);
        await waitFor(() => expect(screen.queryByTestId('post-comment')).toBeNull());
    });

    it('a comment with a filter warning: "rewrite" and "send for review" (held, not counted)', async () => {
        const sent: boolean[] = [];
        stubFetch(postHandler((c) => {
            if (c.method === 'POST' && c.url.endsWith('/posts/3/comments')) {
                const anyway = (c.body as { send_anyway: boolean }).send_anyway;
                sent.push(anyway);
                return anyway ? comment(2, {mine: true, held: true, body: 'harsh'}) : new Error('text_flagged');
            }
            return undefined;
        }));
        at('/feed/post/3');
        fireEvent.change(await screen.findByTestId('comment-input'), {target: {value: 'harsh'}});
        await act(async () => fireEvent.click(screen.getByTestId('comment-send')));
        fireEvent.click(await screen.findByTestId('flagged-rephrase'));
        expect(screen.queryByTestId('flagged-notice')).toBeNull();
        await act(async () => fireEvent.click(screen.getByTestId('comment-send')));
        await act(async () => fireEvent.click(await screen.findByTestId('flagged-send-anyway')));
        expect(sent).toEqual([false, false, true]);
        expect(await screen.findByTestId('held-note')).toBeInTheDocument();
    });

    it('another error sending a comment — a catalog message', async () => {
        stubFetch(postHandler((c) => (c.method === 'POST' ? new Error('internal_error') : undefined)));
        at('/feed/post/3');
        fireEvent.change(await screen.findByTestId('comment-input'), {target: {value: 'hello'}});
        await act(async () => fireEvent.click(screen.getByTestId('comment-send')));
        expect(await screen.findByRole('alert')).toBeInTheDocument();
    });
});
