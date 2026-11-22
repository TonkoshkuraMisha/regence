// Импорт партий, дополнительные пути: фоновый разбор (список перечитывается, пока есть неразобранные партии),
// успешная вставка PGN, «ничего не добавлено» и пропущенные, постраничный список, отказ в удалении.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ImportPage} from '../ImportPage';
import {clearToken, setToken} from '../../../services/authToken';
import {IMPORT_PAGE} from '../../../services/gameImport';

const game = (id: number, extra: Record<string, unknown> = {}) => ({
    id, source: 'lichess', color: 'white', white: 'me', black: 'rival', white_rating: 1500, black_rating: 1490,
    result: '1-0', speed: 'blitz', played_at: '2026-11-01T10:00:00+00:00', analyzed: true, puzzles: 0, ...extra,
});

type Reply = { status?: number; body: unknown };

function stub(routes: (url: string, init?: RequestInit) => Reply | undefined) {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({url: String(url), init});
        const reply = routes(String(url), init) ?? {body: {total: 0, max: 300, games: []}};
        const status = reply.status ?? 200;
        return {ok: status < 400, status, json: async () => reply.body} as Response;
    }));
    return calls;
}

const renderPage = () => render(<MemoryRouter><ImportPage/></MemoryRouter>);

beforeEach(() => {
    localStorage.clear();
    setToken('t');
});
afterEach(() => {
    clearToken();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe('Импорт партий: список', () => {
    it('неразобранная партия помечена, список перечитывается через 8 секунд, пока разбор не закончится', async () => {
        vi.useFakeTimers({shouldAdvanceTime: true});
        let analyzed = false;
        const calls = stub((url) => url.includes('/imports/games')
            ? {body: {total: 1, max: 300, games: [game(1, {analyzed})]}} : undefined);
        renderPage();
        expect(await screen.findByTestId('imported-status')).toHaveTextContent('Разбираем');
        const before = calls.filter((c) => c.url.includes('/imports/games')).length;
        analyzed = true;
        await act(async () => {
            await vi.advanceTimersByTimeAsync(8100);
        });
        await waitFor(() => expect(calls.filter((c) => c.url.includes('/imports/games')).length).toBeGreaterThan(before));
        await waitFor(() => expect(screen.getByTestId('imported-status')).not.toHaveTextContent('Разбираем'));
    });

    it('длинный список листается: «назад» неактивна на первой странице, «вперёд» запрашивает следующую', async () => {
        const calls = stub((url) => {
            if (!url.includes('/imports/games')) return undefined;
            const offset = Number(new URL(url, 'http://x').searchParams.get('offset') ?? 0);
            return {body: {total: IMPORT_PAGE + 5, max: 300, games: [game(offset + 1)]}};
        });
        renderPage();
        await screen.findByTestId('imported-game');
        const [prev, next] = [screen.getByRole('button', {name: 'Назад'}), screen.getByRole('button', {name: 'Дальше'})];
        expect(prev).toBeDisabled();
        fireEvent.click(next);
        await waitFor(() => expect(calls.some((c) => c.url.includes(`offset=${IMPORT_PAGE}`))).toBe(true));
        await waitFor(() => expect(screen.getByRole('button', {name: 'Дальше'})).toBeDisabled());
        fireEvent.click(screen.getByRole('button', {name: 'Назад'}));
        await waitFor(() => expect(screen.getByRole('button', {name: 'Назад'})).toBeDisabled());
    });
});

describe('Импорт партий: форма', () => {
    it('PGN принят: поле очищено, показан итог с пропущенными', async () => {
        stub((url) => url.endsWith('/imports/pgn') ? {body: {added: [game(5)], duplicates: 0, skipped: 2}} : undefined);
        renderPage();
        fireEvent.click(screen.getByTestId('import-tab-pgn'));
        fireEvent.change(screen.getByTestId('import-pgn'), {target: {value: '1. e4 e5'}});
        fireEvent.click(screen.getByTestId('import-submit'));
        const result = await screen.findByTestId('import-result');
        expect(result).toHaveTextContent('Добавлена 1 партия');
        expect(result.textContent).toMatch(/2/);
        expect(screen.getByTestId('import-pgn')).toHaveValue('');
    });

    it('ничего нового не нашлось — понятная подпись, PGN остаётся в поле', async () => {
        stub((url) => url.endsWith('/imports/pgn') ? {body: {added: [], duplicates: 3, skipped: 0}} : undefined);
        renderPage();
        fireEvent.click(screen.getByTestId('import-tab-pgn'));
        fireEvent.change(screen.getByTestId('import-pgn'), {target: {value: '1. e4 e5'}});
        fireEvent.click(screen.getByTestId('import-submit'));
        expect(await screen.findByTestId('import-result')).toBeInTheDocument();
        expect(screen.getByTestId('import-pgn')).toHaveValue('1. e4 e5');
    });

    it('сеть недоступна при импорте — сообщение об ошибке', async () => {
        vi.stubGlobal('fetch', vi.fn(async (url: string) => {
            if (String(url).includes('/imports/games')) return {ok: true, status: 200, json: async () => ({total: 0, max: 300, games: []})} as Response;
            throw new TypeError('Failed to fetch');
        }));
        renderPage();
        fireEvent.change(screen.getByTestId('import-nick'), {target: {value: 'me_42'}});
        fireEvent.click(screen.getByTestId('import-submit'));
        expect(await screen.findByTestId('import-error')).toBeInTheDocument();
    });
});

describe('Импорт партий: удаление', () => {
    it('отказ в подтверждении ничего не удаляет', async () => {
        const calls = stub((url) => url.includes('/imports/games') ? {body: {total: 1, max: 300, games: [game(3)]}} : undefined);
        vi.stubGlobal('confirm', () => false);
        renderPage();
        fireEvent.click(await screen.findByTestId('imported-delete'));
        expect(calls.some((c) => c.init?.method === 'DELETE')).toBe(false);
    });

    it('сервер отказал в удалении — сообщение об ошибке, партия остаётся', async () => {
        stub((url, init) => {
            if (init?.method === 'DELETE') return {status: 500, body: {detail: {code: 'internal_error', params: {}, message: ''}}};
            return url.includes('/imports/games') ? {body: {total: 1, max: 300, games: [game(3)]}} : undefined;
        });
        vi.stubGlobal('confirm', () => true);
        renderPage();
        fireEvent.click(await screen.findByTestId('imported-delete'));
        expect(await screen.findByTestId('import-error')).toBeInTheDocument();
        expect(screen.getByTestId('imported-game')).toBeInTheDocument();
    });
});
