// The beta programme (task 24.4): "Report a problem" with the page context, a link to the community from the server settings,
// invitations and the message queue for the moderator, registration by an invitation code.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import AuthModal from '../../AuthModal';
import {setToken} from '../../../services/authToken';
import {communityPlatform, inviteLink, resetSiteConfig} from '../../../services/beta';
import {FeedbackPanel, InvitesPanel} from '../BetaAdmin';
import {CommunityLink, ReportProblem} from '../ReportProblem';

type Reply = { status?: number; body: unknown };

function stub(handler: (url: string, init?: RequestInit) => Reply | unknown) {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
        const reply = handler(String(url), init);
        const {status = 200, body} = reply && typeof reply === 'object' && 'body' in reply ? reply as Reply : {body: reply};
        return {ok: status < 400, status, json: async () => body} as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

const calls = (fetchMock: ReturnType<typeof stub>, method: string, part: string) =>
    (fetchMock.mock.calls as unknown as [string, RequestInit | undefined][])
        .filter(([url, init]) => (init?.method ?? 'GET') === method && url.includes(part));

const headers = (init: RequestInit | undefined) => (init?.headers ?? {}) as Record<string, string>;

const CONFIG = {invite_only: false, community_url: 'https://t.me/example', version: '1.2.2'};

beforeEach(() => resetSiteConfig());
afterEach(() => {
    setToken(null);
    resetSiteConfig();
    vi.unstubAllGlobals();
});

describe('report a problem', () => {
    it('a guest sends the text; the page path, language and window size are attached — without the address parameters', async () => {
        const fetchMock = stub((url) => (url.endsWith('/beta/config') ? CONFIG : {id: 7}));
        const onClose = vi.fn();
        render(<MemoryRouter initialEntries={['/reset-password?token=secret']}><ReportProblem onClose={onClose}/></MemoryRouter>);

        expect(await screen.findByText(/the app version \(1\.2\.2\)/)).toBeInTheDocument();
        expect(screen.getByTestId('report-problem-context')).toHaveTextContent('/reset-password');
        expect(screen.getByTestId('report-problem-context')).not.toHaveTextContent('secret');
        fireEvent.change(screen.getByTestId('report-problem-text'), {target: {value: '  The clock runs a minute fast  '}});
        await act(async () => fireEvent.click(screen.getByTestId('report-problem-send')));

        const [[url, init]] = calls(fetchMock, 'POST', '/beta/feedback');
        expect(url).toMatch(/\/api\/v1\/beta\/feedback$/);
        expect(JSON.parse(String(init?.body))).toEqual({
            message: 'The clock runs a minute fast', page: '/reset-password', language: 'en',
            screen: `${window.innerWidth}x${window.innerHeight}`,
        });
        expect(headers(init).Authorization).toBeUndefined();
        expect(screen.getByTestId('report-problem-sent')).toHaveTextContent('Thank you! We have received your message.');
        fireEvent.keyDown(window, {key: 'Escape'});
        expect(onClose).toHaveBeenCalled();
    });

    it('a too short text is not sent', async () => {
        const fetchMock = stub(() => ({}));
        render(<MemoryRouter><ReportProblem onClose={vi.fn()}/></MemoryRouter>);
        fireEvent.change(screen.getByTestId('report-problem-text'), {target: {value: ' oops '}});
        fireEvent.click(screen.getByTestId('report-problem-send'));
        expect(await screen.findByRole('alert')).toHaveTextContent('Please write at least a few words');
        expect(calls(fetchMock, 'POST', '/beta/feedback')).toHaveLength(0);
    });

    it('a player sends with a token; the message limit — how long to wait', async () => {
        setToken('jwt');
        const fetchMock = stub((url) => (url.endsWith('/beta/feedback')
            ? {status: 429, body: {detail: {code: 'too_many_feedback', params: {retry_after: 90}, message: '…'}}} : {}));
        render(<MemoryRouter><ReportProblem onClose={vi.fn()}/></MemoryRouter>);
        fireEvent.change(screen.getByTestId('report-problem-text'), {target: {value: 'The button does not work'}});
        await act(async () => fireEvent.click(screen.getByTestId('report-problem-send')));
        expect(screen.getByRole('alert')).toHaveTextContent('Too many messages — please try again in 90 s');
        const [[, init]] = calls(fetchMock, 'POST', '/beta/feedback');
        expect(headers(init).Authorization).toBe('Bearer jwt');
    });
});

describe('community channel', () => {
    it('the link is visible only when set in the server settings', async () => {
        stub(() => CONFIG);
        render(<CommunityLink/>);
        const link = await screen.findByTestId('community-link');
        expect(link).toHaveAttribute('href', 'https://t.me/example');
        expect(link).toHaveAttribute('target', '_blank');
        expect(link).toHaveTextContent('regence channel on Telegram');
    });

    it.each([
        {community_url: null}, {community_url: ''}, {community_url: 'javascript:alert(1)'}, {}, [], null,
    ])('without a valid link nothing is shown: %j', async (config) => {
        const fetchMock = stub(() => config);
        render(<CommunityLink/>);
        await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
        await act(async () => undefined);
        expect(screen.queryByTestId('community-link')).toBeNull();
    });

    it('the platform is determined by the address', () => {
        expect(communityPlatform('https://t.me/example')).toBe('telegram');
        expect(communityPlatform('https://discord.gg/abc')).toBe('discord');
        expect(communityPlatform('https://example.org/t.me')).toBe('generic');
        expect(communityPlatform('not an address')).toBe('generic');
    });
});

describe('invitations for the moderator', () => {
    const invite = (over: object) => ({
        id: 1, code: 'K7QF2MXN9B', note: null, max_uses: null, uses: 0, expires_at: null, revoked_at: null,
        created_at: '2026-11-16T10:00:00+00:00', state: 'active', ...over,
    });

    it('the list: how many came by each code, the state, revocation', async () => {
        const fetchMock = stub(() => ({invite_only: true, invites: [
            invite({id: 1, uses: 3, max_uses: 10, note: 'club'}), invite({id: 2, code: 'ZZZZZZZZZZ', uses: 5, state: 'revoked'}),
        ]}));
        render(<InvitesPanel/>);
        expect(await screen.findByTestId('beta-invite-uses-1')).toHaveTextContent('joined: 3 of 10');
        expect(screen.getByTestId('beta-invite-uses-2')).toHaveTextContent('joined: 5');
        expect(screen.getByTestId('beta-invite-mode')).toHaveTextContent('Registration is closed: by invitation only.');
        expect(screen.getByTestId('beta-invite-2')).toHaveTextContent('revoked');
        // A revoked code has no actions.
        expect(screen.queryByTestId('beta-invite-revoke-2')).toBeNull();
        await act(async () => fireEvent.click(screen.getByTestId('beta-invite-revoke-1')));
        expect(calls(fetchMock, 'POST', '/beta/invites/1/revoke')).toHaveLength(1);
    });

    it('creating a code with a limit and an expiry; empty fields are not sent', async () => {
        const fetchMock = stub(() => ({invite_only: false, invites: []}));
        render(<InvitesPanel/>);
        expect(await screen.findByText('No codes yet.')).toBeInTheDocument();
        fireEvent.change(screen.getByTestId('beta-invite-note'), {target: {value: ' school '}});
        fireEvent.change(screen.getByTestId('beta-invite-max'), {target: {value: '25'}});
        await act(async () => fireEvent.submit(screen.getByTestId('beta-invite-form')));
        fireEvent.change(screen.getByTestId('beta-invite-max'), {target: {value: ''}});
        fireEvent.change(screen.getByTestId('beta-invite-days'), {target: {value: '14'}});
        await act(async () => fireEvent.submit(screen.getByTestId('beta-invite-form')));
        const bodies = calls(fetchMock, 'POST', '/beta/invites').map(([, init]) => JSON.parse(String(init?.body)));
        expect(bodies).toEqual([{note: 'school', max_uses: 25}, {expires_in_days: 14}]);
    });

    it('an invitation link leads to the site with the code', async () => {
        expect(inviteLink('K7QF2MXN9B')).toBe(`${window.location.origin}/?invite=K7QF2MXN9B`);
        const writeText = vi.fn(async () => undefined);
        Object.defineProperty(navigator, 'clipboard', {value: {writeText}, configurable: true});
        stub(() => ({invites: [invite({})]}));
        render(<InvitesPanel/>);
        const copy = await screen.findByTestId('beta-invite-copy-1');
        await act(async () => fireEvent.click(copy));
        expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/?invite=K7QF2MXN9B`);
        expect(screen.getByTestId('beta-invite-copy-1')).toHaveTextContent('Copied');
        Reflect.deleteProperty(navigator, 'clipboard');
    });
});

describe('moderator message queue', () => {
    const item = (over: object) => ({
        id: 1, message: 'The puzzle froze\nafter the second move', page: '/puzzles/42', app_version: '1.2.2', language: 'uk',
        screen: '390x844', status: 'new', author: null, created_at: '2026-11-16T10:00:00+00:00', updated_at: null, ...over,
    });

    it('a message with context, a status change, a filter by status', async () => {
        const fetchMock = stub((url) => (url.includes('status=done')
            ? {items: [item({id: 5, status: 'done', author: 'alice'})], counts: {new: 1, in_progress: 1, done: 1, rejected: 0}}
            : {items: [item({})], counts: {new: 1, in_progress: 1, done: 1, rejected: 0}}));
        render(<FeedbackPanel/>);
        expect(await screen.findByTestId('beta-feedback-context-1')).toHaveTextContent('/puzzles/42 · v1.2.2 · uk · 390x844');
        expect(screen.getByTestId('beta-feedback-1')).toHaveTextContent('guest');
        expect(screen.getByTestId('beta-feedback-tab-open')).toHaveTextContent('To review (2)');
        expect(screen.getByTestId('beta-feedback-tab-done')).toHaveTextContent('Done (1)');
        // The current status is not offered by a button.
        expect(screen.queryByTestId('beta-feedback-1-new')).toBeNull();

        await act(async () => fireEvent.click(screen.getByTestId('beta-feedback-1-in_progress')));
        const [[url, init]] = calls(fetchMock, 'POST', '/beta/feedback/1/status');
        expect(url).toMatch(/\/beta\/feedback\/1\/status$/);
        expect(JSON.parse(String(init?.body))).toEqual({status: 'in_progress'});

        await act(async () => fireEvent.click(screen.getByTestId('beta-feedback-tab-done')));
        expect(await screen.findByTestId('beta-feedback-5')).toHaveTextContent('alice');
        expect(screen.queryByTestId('beta-feedback-1')).toBeNull();
    });

    it('a foreign server answer does not break the panel', async () => {
        stub(() => ({reports: []}));
        render(<FeedbackPanel/>);
        expect(await screen.findByText('Nothing here.')).toBeInTheDocument();
        expect(screen.getByTestId('beta-feedback-tab-open')).toHaveTextContent('To review (0)');
    });
});

describe('registration by invitation', () => {
    const register = (fetchMock: ReturnType<typeof stub>) => calls(fetchMock, 'POST', '/auth/register')
        .map(([, init]) => JSON.parse(String(init?.body)));

    function fill(username: string, password: string) {
        fireEvent.change(screen.getByPlaceholderText('e.g. string1'), {target: {value: username}});
        fireEvent.change(screen.getByPlaceholderText('••••••••'), {target: {value: password}});
        fireEvent.click(screen.getByTestId('auth-terms'));  // consent to the terms (task 23.1)
    }

    it('open registration: no code field, the code is not sent', async () => {
        const fetchMock = stub((url) => (url.endsWith('/auth/register') ? {body: {blitz_rating: 1200}} : {access_token: 'jwt'}));
        render(<AuthModal onSuccess={vi.fn()}/>);
        fireEvent.click(screen.getByRole('button', {name: /No account/}));
        expect(screen.queryByTestId('auth-invite')).toBeNull();
        fill('alice', 'secret-pass');
        await act(async () => fireEvent.click(screen.getByRole('button', {name: /Sign up/})));
        expect(register(fetchMock)).toEqual([{username: 'alice', password: 'secret-pass', accept_terms: true}]);
    });

    it('closed registration: a code is required; a server refusal — a clear text', async () => {
        const fetchMock = stub((url) => (url.endsWith('/auth/register')
            ? {status: 403, body: {detail: {code: 'registration_invite_invalid', params: {}, message: '…'}}} : {}));
        render(<AuthModal onSuccess={vi.fn()} inviteOnly/>);
        fireEvent.click(screen.getByRole('button', {name: /No account/}));
        expect(screen.getByTestId('auth-invite')).toBeRequired();
        expect(screen.getByTestId('auth-invite-only')).toHaveTextContent('Registration is currently by invitation only.');
        fill('alice', 'secret-pass');
        fireEvent.change(screen.getByTestId('auth-invite'), {target: {value: ' k7qf2mxn9b '}});
        await act(async () => fireEvent.click(screen.getByRole('button', {name: /Sign up/})));
        expect(register(fetchMock)).toEqual([{username: 'alice', password: 'secret-pass', accept_terms: true, invite_code: 'k7qf2mxn9b'}]);
        expect(screen.getByRole('alert')).toHaveTextContent('This invite code is invalid, expired or already used up');
    });

    it('an invitation link: registration at once, the code is filled in and checked', async () => {
        const fetchMock = stub((url) => (url.includes('/beta/invites/check') ? {valid: true} : {}));
        render(<AuthModal onSuccess={vi.fn()} inviteCode="K7QF2MXN9B"/>);
        expect(screen.getByRole('heading', {name: 'Create an account'})).toBeInTheDocument();
        expect(screen.getByTestId('auth-invite')).toHaveValue('K7QF2MXN9B');
        expect(screen.getByTestId('auth-invite')).not.toBeRequired();
        expect(await screen.findByTestId('auth-invite-status')).toHaveTextContent('The invitation is valid');
        expect(calls(fetchMock, 'GET', '/beta/invites/check')[0][0]).toMatch(/check\?code=K7QF2MXN9B$/);
        // The code was changed — the previous verdict is no longer shown.
        fireEvent.change(screen.getByTestId('auth-invite'), {target: {value: 'OTHER'}});
        expect(screen.queryByTestId('auth-invite-status')).toBeNull();
    });

    it('an invalid invitation link — it is said at once', async () => {
        stub((url) => (url.includes('/beta/invites/check') ? {valid: false} : {}));
        render(<AuthModal onSuccess={vi.fn()} inviteCode="OLDCODE"/>);
        expect(await screen.findByTestId('auth-invite-status')).toHaveTextContent('This invitation is invalid, expired or already used up');
    });
});
