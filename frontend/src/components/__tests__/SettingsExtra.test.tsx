// --- FILE: frontend/src/components/__tests__/SettingsExtra.test.tsx ---
// Settings (Settings.tsx), branches outside the main tests: the page background (pattern and palette), the avatar and the translation helper
// go to the profile, server refusals when linking an e-mail and exporting data are shown as a message by code, exporting
// games without a single game says there is nothing to export. The network is a fetch stub, answers by request address.

import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import Settings from '../Settings';
import {setToken} from '../../services/authToken';

vi.mock('../../services/gameSocket', () => ({
    gameSocket: {connect: vi.fn(), disconnect: vi.fn(), send: vi.fn(), on: vi.fn(), off: vi.fn()},
}));

const response = (status: number, body: unknown = {}, text = '') =>
    ({
        ok: status < 400, status, json: async () => body, text: async () => text,
        headers: new Headers(),
    }) as Response;

type Call = [string, RequestInit | undefined];

function stubFetch(handler: (url: string, init?: RequestInit) => Response) {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => handler(String(url), init));
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

function bodiesFor(fetchMock: ReturnType<typeof stubFetch>, suffix: string): unknown[] {
    return (fetchMock.mock.calls as unknown as Call[])
        .filter(([url]) => String(url).endsWith(suffix))
        .map(([, init]) => JSON.parse(String(init?.body)));
}

function renderSettings() {
    setToken('old-token');
    render(
        <MemoryRouter>
            <Settings token="old-token" username="alice" onTokenChange={vi.fn()} onLogoutEverywhere={vi.fn()}/>
        </MemoryRouter>,
    );
}

beforeEach(() => {
    localStorage.clear();
});

afterEach(() => {
    vi.unstubAllGlobals();
    setToken(null);
});

describe('Settings: profile and page background', () => {
    it('the pattern and palette of the page are saved in the browser', () => {
        stubFetch(() => response(200, {}));
        renderSettings();
        const patterns = screen.getByTestId('page-patterns').querySelectorAll('button');
        fireEvent.click(patterns[patterns.length - 1]);
        const palettes = screen.getByTestId('page-palettes').querySelectorAll('button');
        fireEvent.click(palettes[palettes.length - 1]);
        expect(localStorage.getItem('regence_page_pattern')).not.toBeNull();
        expect(patterns[patterns.length - 1]).toHaveAttribute('aria-pressed', 'true');
        expect(palettes[palettes.length - 1]).toHaveAttribute('aria-pressed', 'true');
    });

    it('the avatar and the translation helper go to the profile', async () => {
        const fetchMock = stubFetch(() => response(200, {email: null, avatar: null, translation_helper: false}));
        renderSettings();
        const piece = await screen.findByTestId('avatar-piece-wK');
        fireEvent.click(piece);
        fireEvent.click(screen.getByTestId('translation-helper-toggle'));
        await waitFor(() => expect(bodiesFor(fetchMock, '/profile/me/settings')).toEqual(
            expect.arrayContaining([{translation_helper: true}])));
        expect(bodiesFor(fetchMock, '/profile/me/settings').some((b) => 'avatar' in (b as object))).toBe(true);
        expect(screen.getByTestId('translation-helper-toggle')).toBeChecked();
    });
});

describe('Settings: server refusals', () => {
    it('a refusal when linking an e-mail is shown under the field', async () => {
        stubFetch((url) => (url.endsWith('/account/email')
            ? response(400, {detail: {code: 'invalid_credentials'}})
            : response(200, {email: null})));
        renderSettings();
        await screen.findByText('No e-mail linked.');
        fireEvent.change(screen.getByTestId('settings-email-input'), {target: {value: 'alice@example.com'}});
        fireEvent.change(screen.getByTestId('settings-email-password'), {target: {value: 'bad-pass'}});
        fireEvent.click(screen.getByTestId('settings-email-send'));
        await waitFor(() => expect(screen.queryByText(/A letter has been sent/)).toBeNull());
        await waitFor(() => expect(document.querySelector('[role="alert"]')).not.toBeNull());
    });

    it('a refusal when exporting data is shown as a message', async () => {
        stubFetch((url) => (url.endsWith('/account/export') ? response(500, {}) : response(200, {})));
        renderSettings();
        fireEvent.click(screen.getByTestId('settings-export'));
        await waitFor(() => expect(document.querySelector('[role="alert"]')).not.toBeNull());
    });

    it('exporting games without a single game says there is nothing to export', async () => {
        stubFetch((url) => (url.endsWith('/account/games.pgn') ? response(200, {}, '') : response(200, {})));
        renderSettings();
        fireEvent.click(screen.getByTestId('settings-export-games'));
        await waitFor(() => expect(document.querySelector('[role="alert"]')).not.toBeNull());
    });

    it('a refusal when exporting games is shown as a message', async () => {
        stubFetch((url) => (url.endsWith('/account/games.pgn') ? response(500, {}) : response(200, {})));
        renderSettings();
        fireEvent.click(screen.getByTestId('settings-export-games'));
        await waitFor(() => expect(document.querySelector('[role="alert"]')).not.toBeNull());
    });
});
