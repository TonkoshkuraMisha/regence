// Additional App checks: the profile menu (items lead to their own pages), logout, "log out everywhere", the "Legends" menu,
// closing a menu by a click outside, the connection ping, retrying the profile load, the language from the profile and the "Moderation" item.
// The network is only a fetch stub; login is a token in memory.

import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {MemoryRouter, useLocation} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import App from '../App';
import {setToken} from '../services/authToken';
import {setLanguage} from '../i18n';
import {SLOW_FLOW_TIMEOUT_MS} from '../test/timeouts';

vi.mock('../services/gameSocket', () => ({
    gameSocket: {connect: vi.fn(), disconnect: vi.fn(), send: vi.fn(), on: vi.fn(), off: vi.fn()},
}));

const PROFILE = {
    id: 1, username: 'alice', bullet_rating: 1400, blitz_rating: 1500, rapid_rating: 1600,
    classical_rating: 1700, is_cheater: false,
};

type Reply = { ok: boolean; status: number; body?: unknown } | 'offline';
type Routes = Record<string, Reply | (() => Reply)>;

function ok(body: unknown): Reply {
    return {ok: true, status: 200, body};
}

/** fetch by a substring of the address; undeclared addresses answer with an empty list. */
function stubFetch(routes: Routes) {
    const calls: { url: string; method: string }[] = [];
    const fn = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = String(input);
        calls.push({url, method: init?.method ?? 'GET'});
        const key = Object.keys(routes).find((k) => url.includes(k));
        const entry = key ? routes[key] : ok([]);
        const reply = typeof entry === 'function' ? entry() : entry;
        if (reply === 'offline') throw new TypeError('Failed to fetch');
        return {ok: reply.ok, status: reply.status, json: async () => reply.body ?? {}, text: async () => ''} as Response;
    });
    vi.stubGlobal('fetch', fn);
    return calls;
}

function Where() {
    return <div data-testid="where">{useLocation().pathname}</div>;
}

async function renderApp(path = '/about') {
    await act(async () => {
        render(<MemoryRouter initialEntries={[path]}><App/><Where/></MemoryRouter>);
    });
}

beforeEach(() => {
    localStorage.clear();
    setToken('jwt');
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    setToken(null);
    setLanguage('en');
});

describe('App: profile menu', () => {
    it('menu buttons close it and lead to their own pages', async () => {
        stubFetch({'/profile/me': ok(PROFILE), '/moderation/me': ok({is_moderator: true, is_cheater: false})});
        await renderApp();
        const header = screen.getByRole('banner');
        /** Navigation items of the profile menu: they share a hover class; "Report a problem" opens a dialog, not a page. */
        const items = () => within(header).getAllByRole('button')
            .filter((b) => b.className.includes('w-full px-4 py-2 text-left') && b.className.includes('hover:bg-black/30') && b.getAttribute('data-testid') !== 'report-problem-menu');
        fireEvent.click(await within(header).findByText('alice'));
        const total = items().length;
        fireEvent.click(within(header).getByTitle('alice'));
        expect(total).toBeGreaterThanOrEqual(12);
        const visited: string[] = [];
        for (let i = 0; i < total; i++) {
            fireEvent.click(within(header).getByTitle('alice'));
            await act(async () => {
                fireEvent.click(items()[i]);
            });
            visited.push(screen.getByTestId('where').textContent ?? '');
            // The menu closed (otherwise the item path would be visible in the message).
            expect(screen.queryByTestId('report-problem-menu') ? `open after ${visited.join()}` : 'closed').toBe('closed');
        }
        for (const path of ['/profile/alice', '/puzzles', '/import', '/learn', '/watch', '/tools', '/teams', '/feed',
            '/messages', '/study', '/moderation', '/tournaments', '/leaderboard', '/settings']) {
            expect(visited, path).toContain(path);
        }
    }, SLOW_FLOW_TIMEOUT_MS);  // renders fourteen pages one after another

    it('ping: on a network error the menu shows an error message', async () => {
        stubFetch({'/profile/me': ok(PROFILE), '/health': 'offline'});
        await renderApp();
        fireEvent.click(await within(screen.getByRole('banner')).findByText('alice'));
        expect(await screen.findByText('PING ERROR')).toBeInTheDocument();
    });

    it('ping repeats every three seconds while the menu is open', async () => {
        const calls = stubFetch({'/profile/me': ok(PROFILE), '/health': ok({status: 'healthy'})});
        vi.useFakeTimers();
        await renderApp();
        await act(async () => {
            await vi.advanceTimersByTimeAsync(10);
        });
        fireEvent.click(within(screen.getByRole('banner')).getByText('alice'));
        const before = calls.filter((c) => c.url.includes('/health')).length;
        await act(async () => {
            await vi.advanceTimersByTimeAsync(3100);
        });
        expect(calls.filter((c) => c.url.includes('/health')).length).toBeGreaterThan(before);
    });

    it('a click outside the menu closes it', async () => {
        stubFetch({'/profile/me': ok(PROFILE)});
        await renderApp();
        fireEvent.click(await within(screen.getByRole('banner')).findByText('alice'));
        expect(screen.getByTestId('report-problem-menu')).toBeInTheDocument();
        fireEvent.mouseDown(document.body);
        expect(screen.queryByTestId('report-problem-menu')).not.toBeInTheDocument();
    });

    it('"Log out" resets the login and leads to the home page', async () => {
        stubFetch({'/profile/me': ok(PROFILE)});
        await renderApp('/leaderboard');
        fireEvent.click(await within(screen.getByRole('banner')).findByText('alice'));
        const logout = within(screen.getByRole('banner')).getAllByRole('button')
            .find((b) => b.className.includes('text-red-300 hover:text-red-200'))!;
        await act(async () => {
            fireEvent.click(logout);
        });
        expect(screen.getByTestId('where')).toHaveTextContent(/^\/$/);
        await waitFor(() => expect(within(screen.getByRole('banner')).queryByText('alice')).not.toBeInTheDocument());
    });

    it.each([['the server answers', false], ['no network', true]])('"Log out everywhere": %s — the local logout is performed', async (_name, offline) => {
        const calls = stubFetch({
            '/profile/me': ok(PROFILE),
            '/auth/logout-all': offline ? 'offline' : ok({}),
        });
        await renderApp('/leaderboard');
        fireEvent.click(await within(screen.getByRole('banner')).findByText('alice'));
        const everywhere = within(screen.getByRole('banner')).getAllByRole('button')
            .find((b) => b.className.includes('text-red-300/80'))!;
        await act(async () => {
            fireEvent.click(everywhere);
        });
        expect(calls.some((c) => c.url.includes('/auth/logout-all') && c.method === 'POST')).toBe(true);
        expect(screen.getByTestId('where')).toHaveTextContent(/^\/$/);
    });
});

describe('App: "Legends" menu', () => {
    it('opens, leads to a champion and closes; also closes by a click outside', async () => {
        stubFetch({'/profile/me': ok(PROFILE)});
        await renderApp('/about');
        const legends = within(screen.getByRole('navigation')).getByRole('button');
        fireEvent.click(legends);
        const first = screen.getAllByRole('link').find((l) => l.getAttribute('href')?.startsWith('/champions/'))!;
        await act(async () => {
            fireEvent.click(first);
        });
        expect(screen.getByTestId('where').textContent).toMatch(/^\/champions\//);
        expect(screen.queryByTestId('nav-masters')).not.toBeInTheDocument();

        fireEvent.click(legends);
        fireEvent.mouseDown(document.body);
        expect(screen.queryByTestId('nav-masters')).not.toBeInTheDocument();

        fireEvent.click(legends);
        await act(async () => {
            fireEvent.click(screen.getByTestId('nav-masters'));
        });
        expect(screen.getByTestId('where')).toHaveTextContent('/masters');
    });
});

describe('App: profile and session', () => {
    it('the server answered 500 — the profile is requested again after three seconds, no logout', async () => {
        let attempt = 0;
        const calls = stubFetch({'/profile/me': () => (++attempt === 1 ? {ok: false, status: 500} : ok(PROFILE))});
        vi.useFakeTimers();
        await renderApp();
        await act(async () => {
            await vi.advanceTimersByTimeAsync(10);
        });
        expect(calls.filter((c) => c.url.includes('/profile/me'))).toHaveLength(1);
        await act(async () => {
            await vi.advanceTimersByTimeAsync(3100);
        });
        expect(calls.filter((c) => c.url.includes('/profile/me')).length).toBeGreaterThanOrEqual(2);
    });

    it('401 on the profile starts a token refresh by cookie', async () => {
        const calls = stubFetch({'/profile/me': {ok: false, status: 401}, '/auth/refresh': {ok: false, status: 401}});
        await renderApp();
        await waitFor(() => expect(calls.some((c) => c.url.includes('/auth/refresh'))).toBe(true));
    });

    it('the language from the profile is applied on login', async () => {
        stubFetch({'/profile/me': ok({...PROFILE, language: 'uk'})});
        await renderApp('/about');
        await waitFor(() => expect(document.documentElement.lang).toBe('uk'));
    });

    it('if the profile has no language, the current one is written to the server', async () => {
        const calls = stubFetch({'/profile/me': ok({...PROFILE, language: null})});
        await renderApp('/about');
        await waitFor(() => expect(calls.some((c) => c.method !== 'GET' && c.url.includes('/profile'))).toBe(true));
    });

    it('a player with the unfair-play flag sees the "Moderation" item (appeal)', async () => {
        stubFetch({'/profile/me': ok(PROFILE), '/moderation/me': ok({is_moderator: false, is_cheater: true})});
        await renderApp();
        fireEvent.click(await within(screen.getByRole('banner')).findByText('alice'));
        expect(await within(screen.getByRole('banner')).findByText('Moderation')).toBeInTheDocument();
    });
});
