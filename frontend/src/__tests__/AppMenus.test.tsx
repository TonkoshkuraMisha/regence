// Дополнительные проверки App: меню профиля (пункты ведут на свои страницы), выход, «выйти везде», меню «Легенды»,
// закрытие меню щелчком снаружи, замер связи, повтор загрузки профиля, язык из профиля и пункт «Модерация».
// Сеть — только подменой fetch; вход — токеном в памяти.

import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {MemoryRouter, useLocation} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import App from '../App';
import {setToken} from '../services/authToken';
import {setLanguage} from '../i18n';

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

/** fetch по подстроке адреса; необъявленные адреса отвечают пустым списком. */
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
    setLanguage('ru');
});

describe('App: меню профиля', () => {
    it('кнопки меню закрывают его и ведут на свои страницы', async () => {
        stubFetch({'/profile/me': ok(PROFILE), '/moderation/me': ok({is_moderator: true, is_cheater: false})});
        await renderApp();
        const header = screen.getByRole('banner');
        /** Пункты-переходы меню профиля: у них общий класс наведения; «Сообщить о проблеме» открывает окно, а не страницу. */
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
            // Меню закрылось (иначе в сообщении будет виден путь пункта).
            expect(screen.queryByTestId('report-problem-menu') ? `открыто после ${visited.join()}` : 'закрыто').toBe('закрыто');
        }
        for (const path of ['/profile/alice', '/puzzles', '/import', '/learn', '/watch', '/tools', '/teams', '/feed',
            '/messages', '/study', '/moderation', '/tournaments', '/leaderboard', '/settings']) {
            expect(visited, path).toContain(path);
        }
    });

    it('замер связи: при ошибке сети в меню показано сообщение об ошибке', async () => {
        stubFetch({'/profile/me': ok(PROFILE), '/health': 'offline'});
        await renderApp();
        fireEvent.click(await within(screen.getByRole('banner')).findByText('alice'));
        expect(await screen.findByText('ПИНГ ОШИБКА')).toBeInTheDocument();
    });

    it('замер связи повторяется каждые три секунды, пока меню открыто', async () => {
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

    it('щелчок вне меню закрывает его', async () => {
        stubFetch({'/profile/me': ok(PROFILE)});
        await renderApp();
        fireEvent.click(await within(screen.getByRole('banner')).findByText('alice'));
        expect(screen.getByTestId('report-problem-menu')).toBeInTheDocument();
        fireEvent.mouseDown(document.body);
        expect(screen.queryByTestId('report-problem-menu')).not.toBeInTheDocument();
    });

    it('«Выйти» сбрасывает вход и ведёт на главную', async () => {
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

    it.each([['сервер отвечает', false], ['сети нет', true]])('«Выйти везде»: %s — локальный выход выполняется', async (_name, offline) => {
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

describe('App: меню «Легенды»', () => {
    it('открывается, ведёт к чемпиону и закрывается; закрывается и щелчком снаружи', async () => {
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

describe('App: профиль и сессия', () => {
    it('сервер ответил 500 — профиль запрашивается повторно через три секунды, выхода нет', async () => {
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

    it('401 на профиль запускает обновление токена по cookie', async () => {
        const calls = stubFetch({'/profile/me': {ok: false, status: 401}, '/auth/refresh': {ok: false, status: 401}});
        await renderApp();
        await waitFor(() => expect(calls.some((c) => c.url.includes('/auth/refresh'))).toBe(true));
    });

    it('язык из профиля применяется при входе', async () => {
        stubFetch({'/profile/me': ok({...PROFILE, language: 'en'})});
        await renderApp('/about');
        await waitFor(() => expect(document.documentElement.lang).toBe('en'));
    });

    it('если языка в профиле нет, текущий записывается на сервер', async () => {
        const calls = stubFetch({'/profile/me': ok({...PROFILE, language: null})});
        await renderApp('/about');
        await waitFor(() => expect(calls.some((c) => c.method !== 'GET' && c.url.includes('/profile'))).toBe(true));
    });

    it('игрок с флагом нечестной игры видит пункт «Модерация» (апелляция)', async () => {
        stubFetch({'/profile/me': ok(PROFILE), '/moderation/me': ok({is_moderator: false, is_cheater: true})});
        await renderApp();
        fireEvent.click(await within(screen.getByRole('banner')).findByText('alice'));
        expect(await within(screen.getByRole('banner')).findByText('Модерация')).toBeInTheDocument();
    });
});
