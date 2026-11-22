// --- FILE: frontend/src/components/__tests__/SettingsExtra.test.tsx ---
// Настройки (Settings.tsx), ветки вне основных тестов: фон страницы (узор и палитра), аватар и помощник перевода
// уходят в профиль, отказы сервера при привязке почты и выгрузке данных показываются сообщением по коду, выгрузка
// партий без единой партии сообщает, что выгружать нечего. Сеть — стаб fetch, ответы по адресу запроса.

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

describe('Settings: профиль и фон страницы', () => {
    it('узор и палитра страницы сохраняются в браузере', () => {
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

    it('аватар и помощник перевода уходят в профиль', async () => {
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

describe('Settings: отказы сервера', () => {
    it('отказ при привязке почты показывается под полем', async () => {
        stubFetch((url) => (url.endsWith('/account/email')
            ? response(400, {detail: {code: 'invalid_credentials'}})
            : response(200, {email: null})));
        renderSettings();
        await screen.findByText('E-mail не привязан.');
        fireEvent.change(screen.getByTestId('settings-email-input'), {target: {value: 'alice@example.com'}});
        fireEvent.change(screen.getByTestId('settings-email-password'), {target: {value: 'bad-pass'}});
        fireEvent.click(screen.getByTestId('settings-email-send'));
        await waitFor(() => expect(screen.queryByText(/Письмо отправлено/)).toBeNull());
        await waitFor(() => expect(document.querySelector('[role="alert"]')).not.toBeNull());
    });

    it('отказ при выгрузке данных показывается сообщением', async () => {
        stubFetch((url) => (url.endsWith('/account/export') ? response(500, {}) : response(200, {})));
        renderSettings();
        fireEvent.click(screen.getByTestId('settings-export'));
        await waitFor(() => expect(document.querySelector('[role="alert"]')).not.toBeNull());
    });

    it('выгрузка партий без единой партии сообщает, что выгружать нечего', async () => {
        stubFetch((url) => (url.endsWith('/account/games.pgn') ? response(200, {}, '') : response(200, {})));
        renderSettings();
        fireEvent.click(screen.getByTestId('settings-export-games'));
        await waitFor(() => expect(document.querySelector('[role="alert"]')).not.toBeNull());
    });

    it('отказ при выгрузке партий показывается сообщением', async () => {
        stubFetch((url) => (url.endsWith('/account/games.pgn') ? response(500, {}) : response(200, {})));
        renderSettings();
        fireEvent.click(screen.getByTestId('settings-export-games'));
        await waitFor(() => expect(document.querySelector('[role="alert"]')).not.toBeNull());
    });
});
