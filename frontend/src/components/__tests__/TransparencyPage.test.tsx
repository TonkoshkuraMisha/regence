// "How we measure the bots' strength" (task 24.3): the "declared / measured ±95 %" table, the run journals, the export of one's own
// games to PGN and the description of the open API.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {TransparencyPage} from '../TransparencyPage';
import {resetBotCatalogCache} from '../../services/botCatalog';
import {setToken} from '../../services/authToken';

const CATALOG = {
    calibration: {date: '2026-11-16', games: 116},
    historical: [
        {id: 'morphy', declared_rating: 2100, rating: 2143, measured: true, games: 56, ci95: 98,
            live: {rating: 1980, games: 64, offset: 30}},
        {id: 'philidor', declared_rating: 1850, rating: 1850, measured: false, games: 0, ci95: null},
    ],
    archetypes: [{id: 'blunderer', config: {}, declared_rating: 900, rating: 848, measured: true, games: 96, ci95: 109}],
};
const RUNS = {
    calibration: {date: '2026-11-16', games: 116, anchors: [1350, 1600], anchor_movetime_s: 1},
    runs: [
        {name: '2026-11-16_masters.log', date: '2026-11-16', title: 'masters', kind: 'log', size: 6411},
        {name: '2026-11-14_style.pgn', date: '2026-11-14', title: 'style', kind: 'pgn', size: 254127},
    ],
};
const TUNING = {
    entries: [{key: 'archetype:blunderer', created_at: '2026-11-17T12:00:00Z', games: 20, measured: 1012, target: 900,
        randomness: [40, 45], blunder_guard_cp: [200, 220]}],
    rules: {games: 20, drift: 75},
};
const PUBLIC = {
    version: 1, rate_limit: {requests: 60, window_s: 60},
    endpoints: ['/api/v1/public', '/api/v1/public/players/{username}/games.pgn', '/api/v1/public/new-thing'],
};

function stub(pgn = '[Event "a"]\n\n1. e4 *\n\n[Event "b"]\n\n1. d4 *\n') {
    const calls: [string, RequestInit | undefined][] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        calls.push([u, init]);
        if (u.endsWith('/account/games.pgn')) {
            return {ok: true, text: async () => pgn, headers: new Headers({'X-Total-Count': pgn ? '2' : '0'})} as Response;
        }
        if (u.includes('/calibration/runs/')) return {ok: true, text: async () => '[1/2] morphy — anchor:1850: 1-0'} as Response;
        const body = u.endsWith('/bots/catalog') ? CATALOG : u.endsWith('/calibration/runs') ? RUNS
            : u.endsWith('/bots/tuning-log') ? TUNING : PUBLIC;
        return {ok: true, json: async () => body} as Response;
    }));
    return calls;
}

const renderPage = () => act(async () => {
    render(<MemoryRouter><TransparencyPage username="misha"/></MemoryRouter>);
});

beforeEach(() => {
    resetBotCatalogCache();
    vi.stubGlobal('URL', Object.assign(URL, {createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn()}));
});
afterEach(() => {
    vi.unstubAllGlobals();
    setToken(null);
});

describe('transparency', () => {
    it('the self-play tuning journal (task 32.3): what was measured and how the sliders moved', async () => {
        stub();
        await renderPage();
        const row = screen.getByTestId('tuning-archetype:blunderer');
        expect(row).toHaveTextContent('1012 vs 900 (20 games)');
        expect(row).toHaveTextContent('40 → 45');
        expect(row).toHaveTextContent('200 → 220');
        expect(screen.getByTestId('transparency-tuning')).toHaveTextContent('After 20 games');
    });

    it('bot memory: rating by games with people and a strength correction (task 32.1)', async () => {
        stub();
        await renderPage();
        expect(screen.getByTestId('live-morphy')).toHaveTextContent('1980 (64)');
        expect(screen.getByTestId('live-morphy')).toHaveTextContent('correction +30');
        expect(screen.getByTestId('live-philidor')).toHaveTextContent('—');
        expect(screen.getByTestId('transparency-memory')).toHaveTextContent('Bots also learn from their games');
    });

    it('the table: measured ones — with the error and the number of games, the others — "declared"; sorted by strength', async () => {
        stub();
        await renderPage();
        const morphy = screen.getByTestId('strength-morphy');
        expect(morphy).toHaveTextContent('Paul Charles Morphy');
        expect(morphy).toHaveTextContent('2143 ±98');
        expect(morphy).toHaveTextContent('measured');
        const philidor = screen.getByTestId('strength-philidor');
        expect(philidor).toHaveTextContent('1850');
        expect(philidor).toHaveTextContent('declared');
        expect(philidor).not.toHaveTextContent('±');
        expect(screen.getByTestId('strength-archetype:blunderer')).toHaveTextContent('Gaper');
        const order = Array.from(document.querySelectorAll('[data-testid^="strength-"]')).map((row) => row.getAttribute('data-testid'));
        expect(order).toEqual(['strength-morphy', 'strength-philidor', 'strength-archetype:blunderer']);
        expect(screen.getByTestId('transparency-meta')).toHaveTextContent('116 games. Measured: 2 of 3 bots.');
        expect(screen.getByText(/limited to a fixed strength \(1350, 1600\)/)).toBeInTheDocument();
    });

    it('the run journal opens on the page, the PGN — only as a link', async () => {
        const calls = stub();
        await renderPage();
        expect(screen.queryByTestId('run-show-2026-11-14_style.pgn')).toBeNull();
        await act(async () => fireEvent.click(screen.getByTestId('run-show-2026-11-16_masters.log')));
        expect(screen.getByTestId('run-text')).toHaveTextContent('morphy — anchor:1850: 1-0');
        expect(calls.some(([u]) => u.endsWith('/calibration/runs/2026-11-16_masters.log'))).toBe(true);
        await act(async () => fireEvent.click(screen.getByTestId('run-show-2026-11-16_masters.log')));
        expect(screen.queryByTestId('run-text')).toBeNull();
    });

    it('the open API: the limit and addresses with explanations; an unknown address — without an explanation', async () => {
        stub();
        await renderPage();
        expect(screen.getByTestId('transparency-api-limit')).toHaveTextContent('Limit: 60 requests per 60 s');
        expect(screen.getByText('GET /api/v1/public/players/{username}/games.pgn').parentElement).toHaveTextContent('the same games as one PGN file');
        expect(screen.getByText('GET /api/v1/public/new-thing').parentElement?.children).toHaveLength(1);
    });

    it('own games: without a login — a hint instead of the button, we do not go to the server for games', async () => {
        const calls = stub();
        await renderPage();
        expect(screen.queryByTestId('transparency-export')).toBeNull();
        expect(screen.getByTestId('transparency-data')).toHaveTextContent('Log in to download your games.');
        expect(calls.some(([u]) => u.endsWith('/account/games.pgn'))).toBe(false);
    });

    it('games export: a request with a token and the number of games; empty — a message without a file', async () => {
        setToken('jwt');
        const calls = stub();
        await renderPage();
        await act(async () => fireEvent.click(screen.getByTestId('transparency-export')));
        const call = calls.find(([u]) => u.endsWith('/account/games.pgn'));
        expect(call?.[1]?.headers).toMatchObject({Authorization: 'Bearer jwt'});
        expect(screen.getByTestId('transparency-export-note')).toHaveTextContent('Games in the file: 2.');
        expect(URL.createObjectURL).toHaveBeenCalledTimes(1);

        stub('');
        await act(async () => fireEvent.click(screen.getByTestId('transparency-export')));
        expect(screen.getByTestId('transparency-export-note')).toHaveTextContent('You have no finished games yet.');
        expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    });
});
