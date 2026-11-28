// "Import every day" (task 24.1): turning the daily import on with the typed username, its state and turning it off.

import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ImportPage} from '../ImportPage';
import {clearToken, setToken} from '../../../services/authToken';

type Reply = { status?: number; body: unknown };

function stub(routes: (url: string, init?: RequestInit) => Reply | undefined) {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
        const reply = routes(String(url), init) ?? {body: {total: 0, max: 300, games: []}};
        const status = reply.status ?? 200;
        return {ok: status < 400, status, json: async () => reply.body} as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

const SUB = {source: 'lichess', username: 'me_1', last_run_at: null, last_added: 0, last_error: null};

beforeEach(() => {
    localStorage.clear();
    setToken('t');
});
afterEach(() => {
    clearToken();
    vi.unstubAllGlobals();
});

describe('Daily import', () => {
    it('turns on with the username typed in the form', async () => {
        const fetchMock = stub((url, init) => {
            if (url.endsWith('/imports/subscriptions/lichess') && init?.method === 'PUT') return {body: SUB};
            if (url.endsWith('/imports/subscriptions')) return {body: {subscriptions: []}};
            return undefined;
        });
        render(<MemoryRouter><ImportPage/></MemoryRouter>);
        const button = await screen.findByTestId('daily-turn-on');
        expect(button).toBeDisabled();
        fireEvent.change(screen.getByTestId('import-nick'), {target: {value: 'me_1'}});
        fireEvent.click(button);
        expect(await screen.findByTestId('daily-on')).toHaveTextContent('me_1');
        expect(screen.getByTestId('daily-status')).toHaveTextContent('within a day');
        const put = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT');
        expect(JSON.parse(String(put?.[1]?.body))).toEqual({username: 'me_1'});
    });

    it('shows the last run and a refusal, and turns off', async () => {
        const failed = {...SUB, last_run_at: '2026-11-28T06:29:00+00:00', last_error: 'import_player_not_found'};
        const fetchMock = stub((url, init) => {
            if (url.endsWith('/imports/subscriptions/lichess') && init?.method === 'DELETE') return {status: 204, body: null};
            if (url.endsWith('/imports/subscriptions')) return {body: {subscriptions: [failed]}};
            return undefined;
        });
        render(<MemoryRouter><ImportPage/></MemoryRouter>);
        expect(await screen.findByTestId('daily-status')).toHaveTextContent('No player with this username');
        fireEvent.click(screen.getByTestId('daily-off'));
        expect(await screen.findByTestId('daily-turn-on')).toBeInTheDocument();
        expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(true);
    });

    it('is not shown on the PGN tab', async () => {
        stub((url) => (url.endsWith('/imports/subscriptions') ? {body: {subscriptions: []}} : undefined));
        render(<MemoryRouter><ImportPage/></MemoryRouter>);
        await screen.findByTestId('daily-import');
        fireEvent.click(screen.getByTestId('import-tab-pgn'));
        expect(screen.queryByTestId('daily-import')).toBeNull();
    });
});
