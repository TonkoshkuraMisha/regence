// --- FILE: frontend/src/__tests__/App.test.tsx ---
// The header and the profile menu: no control without an action. A menu item appears only
// together with a working page (ToDo.md, "Part II rules").

import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import App, {SESSION_RESTORE_WAIT_MS} from '../App';
import {mockFetchRouter} from '../test/mocks';
import {setToken} from '../services/authToken';

vi.mock('../services/gameSocket', () => ({
    gameSocket: {connect: vi.fn(), disconnect: vi.fn(), send: vi.fn(), on: vi.fn(), off: vi.fn()},
}));

vi.mock('../services/soundEngine', async (importOriginal) => {
    const actual = await importOriginal<typeof import('../services/soundEngine')>();
    return {
        ...actual,
        soundEngine: {play: vi.fn(), isMuted: vi.fn(() => false), toggleMute: vi.fn(() => true), setMuted: vi.fn(),
            getSoundSet: vi.fn(() => 'wood'), setSoundSet: vi.fn()},
    };
});

const PROFILE = {
    id: 1, username: 'alice', bullet_rating: 1400, blitz_rating: 1500, rapid_rating: 1600,
    classical_rating: 1700, is_cheater: false,
};

function renderApp(path = '/leaderboard') {
    vi.stubGlobal('fetch', mockFetchRouter({
        '/profile/me': () => PROFILE,
        '/profile/leaderboard': () => [],
        '/profile/matchmaking/queue': () => [],
        '/profile/games/live': () => [],
        '/profile/games/my-active': () => ({active: false}),
        '/health': () => ({status: 'healthy'}),
    }));
    return render(
        <MemoryRouter initialEntries={[path]}>
            <App/>
        </MemoryRouter>,
    );
}

/** React keeps an element's props on the DOM node — that shows whether a button has a handler. */
function hasClickHandler(element: Element): boolean {
    const propsKey = Object.keys(element).find((key) => key.startsWith('__reactProps'));
    const props = propsKey ? (element as unknown as Record<string, {onClick?: unknown}>)[propsKey] : undefined;
    return typeof props?.onClick === 'function';
}

function expectNoDeadControls(container: HTMLElement) {
    for (const button of within(container).queryAllByRole('button')) {
        expect(hasClickHandler(button), `the button "${button.textContent || button.title}" does nothing`).toBe(true);
    }
    for (const link of within(container).queryAllByRole('link')) {
        expect(link.getAttribute('href'), `the link "${link.textContent || link.title}" leads nowhere`).toBeTruthy();
    }
}

beforeEach(() => {
    localStorage.clear();
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('App: viewing a game on a single screen', () => {
    // The board and the move panel take exactly one screen: the page does not scroll, the move list scrolls.
    it.each(['/game/5', '/library/game/17321', '/import/game/3'])('%s', (path) => {
        const {container} = renderApp(path);
        expect(container.firstElementChild?.className).toContain('xl:h-dvh');
        expect(screen.getByRole('main').className).toContain('xl:overflow-hidden');
    });

    it('an ordinary page scrolls as a whole', () => {
        const {container} = renderApp('/library');
        expect(container.firstElementChild?.className).not.toContain('xl:h-dvh');
    });

    // The page background (pattern and palette, tasks 18.1 and 31.1) is drawn on body: a root block with its own fill
    // used to cover it entirely, and the chosen background was visible only in the settings preview.
    it('the root block is transparent: the page background shows through it', () => {
        const {container} = renderApp('/library');
        expect(container.firstElementChild?.className).not.toMatch(/(^|\s)bg-/);
    });
});

describe('App: header menu at medium widths', () => {
    // At 768–1360 px the item labels are hidden (icons remain): every item must have a tooltip and an accessible
    // name, and the label itself is a separate element that is shown from the width where the header fits.
    it('every menu item has a tooltip, an accessible name and a label hidden on a narrow header', () => {
        renderApp('/library');
        const nav = screen.getByRole('navigation');
        const items = [...within(nav).getAllByRole('link'), within(nav).getByRole('button')];
        expect(items).toHaveLength(7);
        for (const item of items) {
            const name = item.getAttribute('aria-label');
            expect(name, item.textContent ?? '').toBeTruthy();
            expect(item.getAttribute('title')).toBe(name);
            const label = within(item).getByText(name!);
            expect(label.className).toMatch(/^hidden min-\[1(360|500)px\]:inline$/);
        }
        // Tournaments and the leaderboard are distinguishable without labels: their icons differ.
        const icon = (name: string) => within(nav).getByRole('link', {name}).querySelector('svg')?.getAttribute('class');
        expect(icon('Tournaments')).not.toBe(icon('Leaderboard'));
    });

    it('a long player name in the header is truncated, not stretching it', async () => {
        setToken('jwt');
        renderApp('/library');
        const name = await screen.findByTitle('alice');
        expect(name.className).toContain('truncate');
        expect(name.className).toContain('max-w-[7rem]');
    });
});

describe('App: beta programme (task 24.4)', () => {
    it('a guest opens "Report a problem" from the header', () => {
        renderApp('/puzzles');
        fireEvent.click(within(screen.getByRole('banner')).getByRole('button', {name: 'Report a problem'}));
        expect(screen.getByTestId('report-problem')).toBeInTheDocument();
        expect(screen.getByTestId('report-problem-context')).toHaveTextContent('/puzzles');
        fireEvent.click(screen.getByRole('button', {name: 'Close'}));
        expect(screen.queryByTestId('report-problem')).not.toBeInTheDocument();
    });

    it('a logged-in player opens "Report a problem" from the profile menu', async () => {
        setToken('test-token');
        renderApp();
        fireEvent.click(await within(screen.getByRole('banner')).findByText('alice'));
        fireEvent.click(screen.getByTestId('report-problem-menu'));
        expect(screen.getByTestId('report-problem')).toBeInTheDocument();
        // The profile menu closed at the same time.
        expect(screen.queryByTestId('report-problem-menu')).not.toBeInTheDocument();
        setToken(null);
    });

    it('an invitation link opens registration for a guest with the code filled in', async () => {
        renderApp('/?invite=K7QF2MXN9B');
        expect(await screen.findByTestId('auth-invite')).toHaveValue('K7QF2MXN9B');
        expect(screen.getByRole('heading', {name: 'Create an account'})).toBeInTheDocument();
    });

    it('without an invitation the login window does not open by itself', async () => {
        renderApp('/leaderboard');
        await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
});

describe('App: navigation', () => {
    it('the guest header has no elements without an action', () => {
        renderApp();
        const header = screen.getByRole('banner');

        expectNoDeadControls(header);
        for (const label of ['Learning', 'Watch', 'Tools']) {
            expect(within(header).queryByText(label)).not.toBeInTheDocument();
        }
        // "Puzzles" returned to the header together with the section (task 13.3) — it is a working link.
        expect(within(header).getByText('Puzzles').closest('a')?.getAttribute('href')).toBe('/puzzles');
        expect(within(header).queryByTitle('Game search')).not.toBeInTheDocument();
        expect(within(header).queryByTitle('Notifications')).not.toBeInTheDocument();
    });

    it('the header and profile menu of a logged-in player have no elements without an action', async () => {
        setToken('test-token');
        renderApp();
        const header = screen.getByRole('banner');

        fireEvent.click(await within(header).findByText('alice'));
        expect(within(header).getByText('Profile')).toBeInTheDocument();

        expectNoDeadControls(header);
        expect(within(header).queryByText('Inbox')).not.toBeInTheDocument();
    });

    it('"Settings" from the profile menu opens the settings page', async () => {
        setToken('test-token');
        renderApp();
        const header = screen.getByRole('banner');

        fireEvent.click(await within(header).findByText('alice'));
        fireEvent.click(within(header).getByRole('button', {name: /Settings/}));

        expect(await screen.findByRole('heading', {name: 'Settings'})).toBeInTheDocument();
        expect(screen.getByText('Account alice')).toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Change password'})).toBeInTheDocument();
    });

    it('a guest reaches the settings by the header link', async () => {
        renderApp();
        fireEvent.click(within(screen.getByRole('banner')).getByTitle('Settings'));
        // The page appears after an attempt to restore the login (for a guest it ends with nothing).
        expect(await screen.findByRole('heading', {name: 'Settings'})).toBeInTheDocument();
        expect(screen.getByText(/Log in to change your password/)).toBeInTheDocument();
    });
});

describe('App: login is restored before the first page', () => {
    // Each scenario starts from a clean state: a token from a neighbouring test would mean "already logged in".
    beforeEach(() => setToken(null));
    afterEach(() => setToken(null));

    // On a direct visit and on a page refresh there is no token yet — it comes by cookie. Pages that
    // request data at once used to get a 401 ("Could not load tournaments" in the "Time machine").
    it('the page is not rendered and requests no data until the login is restored; then it gets the token', async () => {
        let finishRefresh: (response: Response) => void = () => undefined;
        const requests: { url: string; authorized: boolean }[] = [];
        vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
            const address = String(url);
            requests.push({url: address, authorized: Boolean((init?.headers as Record<string, string> | undefined)?.Authorization)});
            if (address.includes('/auth/refresh')) return new Promise<Response>((resolve) => { finishRefresh = resolve; });
            const body = address.includes('/tournaments/time-machine') ? {events: []} : address.includes('/profile/me') ? PROFILE : [];
            return Promise.resolve({ok: true, status: 200, json: async () => body} as Response);
        }));
        render(
            <MemoryRouter initialEntries={['/time-machine']}>
                <App/>
            </MemoryRouter>,
        );
        // The header is already in place, the page is not yet, no tournament requests were made.
        expect(screen.getByRole('banner')).toBeInTheDocument();
        expect(screen.getByTestId('session-restoring')).toBeInTheDocument();
        expect(screen.queryByTestId('time-machine')).toBeNull();
        expect(requests.some((r) => r.url.includes('/tournaments/time-machine'))).toBe(false);

        await act(async () => {
            finishRefresh({ok: true, status: 200, json: async () => ({access_token: 'restored'})} as Response);
        });
        expect(await screen.findByTestId('time-machine')).toBeInTheDocument();
        expect(screen.queryByTestId('session-restoring')).toBeNull();
        const list = requests.filter((r) => r.url.includes('/tournaments/time-machine'));
        expect(list.length).toBeGreaterThan(0);
        expect(list.every((r) => r.authorized)).toBe(true);
    });

    it('the server does not answer the login restore — the page opens by itself after three seconds', async () => {
        vi.useFakeTimers();
        try {
            vi.stubGlobal('fetch', vi.fn((url: string) => String(url).includes('/auth/refresh')
                ? new Promise<Response>(() => undefined)
                : Promise.resolve({ok: true, status: 200, json: async () => []} as Response)));
            render(
                <MemoryRouter initialEntries={['/about']}>
                    <App/>
                </MemoryRouter>,
            );
            expect(screen.getByTestId('session-restoring')).toBeInTheDocument();
            await act(async () => {
                await vi.advanceTimersByTimeAsync(SESSION_RESTORE_WAIT_MS - 100);
            });
            expect(screen.getByTestId('session-restoring')).toBeInTheDocument();
            await act(async () => {
                await vi.advanceTimersByTimeAsync(200);
            });
            expect(screen.queryByTestId('session-restoring')).toBeNull();
        } finally {
            vi.useRealTimers();
        }
    });

    it('for a logged-in player the page is rendered at once', () => {
        setToken('jwt');
        renderApp('/library');
        expect(screen.queryByTestId('session-restoring')).toBeNull();
    });

    it('for a guest the page appears when the login restore yielded nothing', async () => {
        vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(String(url).includes('/auth/refresh')
            ? {ok: false, status: 401, json: async () => ({})} as Response
            : {ok: true, status: 200, json: async () => []} as Response)));
        render(
            <MemoryRouter initialEntries={['/about']}>
                <App/>
            </MemoryRouter>,
        );
        await waitFor(() => expect(screen.queryByTestId('session-restoring')).toBeNull());
        expect(screen.getByRole('main')).not.toBeEmptyDOMElement();
    });
});
