// Game import, extra paths: background analysis (the list is re-read while there are unanalysed games),
// successful PGN paste, "nothing added" and skipped games, a paged list, a refused deletion.

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

describe('Game import: list', () => {
    it('an unanalysed game is marked, the list is re-read after 8 seconds until analysis finishes', async () => {
        vi.useFakeTimers({shouldAdvanceTime: true});
        let analyzed = false;
        const calls = stub((url) => url.includes('/imports/games')
            ? {body: {total: 1, max: 300, games: [game(1, {analyzed})]}} : undefined);
        renderPage();
        expect(await screen.findByTestId('imported-status')).toHaveTextContent('Being analysed');
        const before = calls.filter((c) => c.url.includes('/imports/games')).length;
        analyzed = true;
        await act(async () => {
            await vi.advanceTimersByTimeAsync(8100);
        });
        await waitFor(() => expect(calls.filter((c) => c.url.includes('/imports/games')).length).toBeGreaterThan(before));
        await waitFor(() => expect(screen.getByTestId('imported-status')).not.toHaveTextContent('Being analysed'));
    });

    it('a long list is paged: "back" is disabled on the first page, "forward" requests the next', async () => {
        const calls = stub((url) => {
            if (!url.includes('/imports/games')) return undefined;
            const offset = Number(new URL(url, 'http://x').searchParams.get('offset') ?? 0);
            return {body: {total: IMPORT_PAGE + 5, max: 300, games: [game(offset + 1)]}};
        });
        renderPage();
        await screen.findByTestId('imported-game');
        const [prev, next] = [screen.getByRole('button', {name: 'Back'}), screen.getByRole('button', {name: 'Further'})];
        expect(prev).toBeDisabled();
        fireEvent.click(next);
        await waitFor(() => expect(calls.some((c) => c.url.includes(`offset=${IMPORT_PAGE}`))).toBe(true));
        await waitFor(() => expect(screen.getByRole('button', {name: 'Further'})).toBeDisabled());
        fireEvent.click(screen.getByRole('button', {name: 'Back'}));
        await waitFor(() => expect(screen.getByRole('button', {name: 'Back'})).toBeDisabled());
    });
});

describe('Game import: form', () => {
    it('PGN accepted: the field is cleared, a result with skipped games is shown', async () => {
        stub((url) => url.endsWith('/imports/pgn') ? {body: {added: [game(5)], duplicates: 0, skipped: 2}} : undefined);
        renderPage();
        fireEvent.click(screen.getByTestId('import-tab-pgn'));
        fireEvent.change(screen.getByTestId('import-pgn'), {target: {value: '1. e4 e5'}});
        fireEvent.click(screen.getByTestId('import-submit'));
        const result = await screen.findByTestId('import-result');
        expect(result).toHaveTextContent('Added 1 game');
        expect(result.textContent).toMatch(/2/);
        expect(screen.getByTestId('import-pgn')).toHaveValue('');
    });

    it('nothing new found — a clear label, the PGN stays in the field', async () => {
        stub((url) => url.endsWith('/imports/pgn') ? {body: {added: [], duplicates: 3, skipped: 0}} : undefined);
        renderPage();
        fireEvent.click(screen.getByTestId('import-tab-pgn'));
        fireEvent.change(screen.getByTestId('import-pgn'), {target: {value: '1. e4 e5'}});
        fireEvent.click(screen.getByTestId('import-submit'));
        expect(await screen.findByTestId('import-result')).toBeInTheDocument();
        expect(screen.getByTestId('import-pgn')).toHaveValue('1. e4 e5');
    });

    it('network unavailable during import — an error message', async () => {
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

describe('Game import: deletion', () => {
    it('refusing the confirmation deletes nothing', async () => {
        const calls = stub((url) => url.includes('/imports/games') ? {body: {total: 1, max: 300, games: [game(3)]}} : undefined);
        vi.stubGlobal('confirm', () => false);
        renderPage();
        fireEvent.click(await screen.findByTestId('imported-delete'));
        expect(calls.some((c) => c.init?.method === 'DELETE')).toBe(false);
    });

    it('the server refused the deletion — an error message, the game stays', async () => {
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
