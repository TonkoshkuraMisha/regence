// Respectful communication (task 30.3): the filter warning and "send for review", the "awaiting a moderator" mark,
// a one-step report on a text, hiding a conversation, the rules page.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setToken} from '../../../services/authToken';
import {CommunityRulesPage, TextReportButton} from '../Civility';
import {FeedPage} from '../FeedPage';
import {MessagesPage} from '../MessagesPage';

type Handler = (url: string, init?: RequestInit) => unknown;

function stubFetch(handler: Handler) {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
        const body = handler(String(url), init);
        const failed = body instanceof Error;
        return {
            ok: !failed, status: failed ? 409 : 200,
            json: async () => (failed ? {detail: {code: body.message, params: {}, message: ''}} : body),
        } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

const posted = (mock: ReturnType<typeof stubFetch>, part: string) => mock.mock.calls
    .filter(([u, i]) => String(u).includes(part) && i?.method === 'POST')
    .map(([, i]) => JSON.parse(String(i?.body)));

beforeEach(() => setToken('jwt'));
afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
});

describe('insult filter', () => {
    it('message: a warning, "send for review" and the "awaiting a moderator" mark', async () => {
        const fetchMock = stubFetch((url, init) => {
            if (url.endsWith('/settings')) return {dm_policy: 'all', blocked: []};
            if (url.includes('/with/magnus') && init?.method === 'POST') {
                const sent = JSON.parse(String(init.body));
                if (!sent.send_anyway) return new Error('text_flagged');
                return {id: 5, mine: true, body: sent.body, attachment: null, created_at: null, read: false, held: true};
            }
            if (url.includes('/with/magnus')) return {username: 'magnus', avatar: null, can_write: true, reason: null, blocked: false, messages: []};
            return {unread: 0, conversations: []};
        });
        render(<MemoryRouter initialEntries={['/messages/magnus']}><Routes>
            <Route path="/messages/:username" element={<MessagesPage/>}/>
        </Routes></MemoryRouter>);
        await screen.findByTestId('dm-composer');
        fireEvent.change(screen.getByTestId('dm-input'), {target: {value: 'bad words'}});
        await act(async () => fireEvent.click(screen.getByTestId('dm-send')));
        expect(await screen.findByTestId('flagged-notice')).toHaveTextContent('This looks offensive');
        expect(screen.getByTestId('dm-input')).toHaveValue('bad words');      // the text is not lost - it can be rewritten
        await act(async () => fireEvent.click(screen.getByTestId('flagged-send-anyway')));
        expect(posted(fetchMock, '/with/magnus').map((b) => b.send_anyway)).toEqual([false, true]);
        expect(screen.queryByTestId('flagged-notice')).toBeNull();
        expect(await screen.findByTestId('held-note')).toHaveTextContent('Awaiting a moderator');
    });

    it('post: "Rephrase" closes the warning without sending', async () => {
        const fetchMock = stubFetch((_url, init) => (init?.method === 'POST' ? new Error('text_flagged') : {posts: [], page: 20}));
        render(<MemoryRouter initialEntries={['/feed']}><Routes><Route path="/feed" element={<FeedPage/>}/></Routes></MemoryRouter>);
        await screen.findByTestId('feed-empty');
        fireEvent.change(screen.getByTestId('feed-input'), {target: {value: 'bad words'}});
        await act(async () => fireEvent.click(screen.getByTestId('feed-publish')));
        await screen.findByTestId('flagged-notice');
        fireEvent.click(screen.getByTestId('flagged-rephrase'));
        expect(screen.queryByTestId('flagged-notice')).toBeNull();
        expect(posted(fetchMock, '/api/v1/feed')).toHaveLength(1);
    });
});

describe('report and hide', () => {
    it('report on a text: the reason in one click', async () => {
        const fetchMock = stubFetch(() => ({id: 1}));
        render(<MemoryRouter><TextReportButton subject="post:7"/></MemoryRouter>);
        fireEvent.click(screen.getByTestId('text-report'));
        await act(async () => fireEvent.click(screen.getByTestId('text-report-spam')));
        expect(posted(fetchMock, '/reports/text')).toEqual([{subject: 'post:7', reason: 'spam'}]);
        expect(screen.getByTestId('text-report-sent')).toHaveTextContent('Report received');
    });

    it('hide a conversation: the request and the return to the list', async () => {
        const fetchMock = stubFetch((url) => {
            if (url.endsWith('/settings')) return {dm_policy: 'all', blocked: []};
            if (url.endsWith('/hide')) return {unread: 0};
            if (url.includes('/with/magnus')) return {username: 'magnus', avatar: null, can_write: true, reason: null, blocked: false, messages: []};
            return {unread: 0, conversations: []};
        });
        render(<MemoryRouter initialEntries={['/messages/magnus']}><Routes>
            <Route path="/messages" element={<MessagesPage/>}/>
            <Route path="/messages/:username" element={<MessagesPage/>}/>
        </Routes></MemoryRouter>);
        await screen.findByTestId('dm-composer');
        await act(async () => fireEvent.click(screen.getByTestId('dm-hide')));
        expect(fetchMock.mock.calls.some(([u, i]) => String(u).endsWith('/with/magnus/hide') && i?.method === 'POST')).toBe(true);
        expect(await screen.findByText('Choose a conversation on the left.')).toBeInTheDocument();
    });

    it('the rules page', () => {
        render(<MemoryRouter><CommunityRulesPage/></MemoryRouter>);
        const page = screen.getByTestId('rules-page');
        expect(page).toHaveTextContent('Rules of conversation');
        // The liberal wording (owner decision of 17.11.2026): the bans protect a person, not the tone.
        expect(page).toHaveTextContent('People speak freely here.');
        expect(page).toHaveTextContent('We do not police taste or tone.');
        expect(page).toHaveTextContent('Do not go after a person');
        expect(screen.getAllByRole('listitem')).toHaveLength(6);
    });
});
