// The weekly tournament against legends (task 26.1): the page shows the line-up, results and standings; "Play" opens a
// game on the server and hands it to the board; the lobby banner shows the time left; the status line of a saved game.

import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {WeeklyLegendsBanner, WeeklyLegendsPage} from '../WeeklyLegends';
import {clearToken, setToken} from '../../../services/authToken';
import {weeklyOutcomeMessage} from '../../chessboard/hooks/useBotGame';
import type {WeeklyEvent} from '../../../services/weeklyLegends';

const response = (status: number, body: unknown = {}) =>
    ({ok: status < 400, status, json: async () => body}) as Response;

const EVENT: WeeklyEvent = {
    week: '2026-11-23', ends_at: new Date(Date.now() + 2 * 86_400_000 + 3 * 3_600_000 + 60_000).toISOString(),
    base_time_ms: 600_000, increment_ms: 5_000,
    legends: [
        {bot_id: 'morphy', rating: 2050, points: 1, forfeit: null},
        {bot_id: 'philidor', rating: 1500, points: null, forfeit: null},
    ],
    open_game: null,
    standings: {top: [{place: 1, username: 'alice', avatar: null, points: 1, wins: 1, games: 1}],
        me: {place: 1, username: 'alice', avatar: null, points: 1, wins: 1, games: 1}, players: 1},
    last_winner: {place: 1, username: 'bob', avatar: null, points: 4.5, wins: 4, games: 5},
};

/** Shows where the page navigated and with what state. */
function Board() {
    const location = useLocation();
    return <pre data-testid="board-state">{JSON.stringify(location.state)}</pre>;
}

function renderPage() {
    render(
        <MemoryRouter initialEntries={['/events/weekly']}>
            <Routes>
                <Route path="/events/weekly" element={<WeeklyLegendsPage/>}/>
                <Route path="/" element={<Board/>}/>
            </Routes>
        </MemoryRouter>,
    );
}

beforeEach(() => setToken('jwt'));
afterEach(() => {
    clearToken();
    vi.unstubAllGlobals();
});

describe('WeeklyLegendsPage', () => {
    it('shows the legends with results, the time control and the standings', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => response(200, EVENT)));
        renderPage();
        expect(await screen.findByTestId('legend-morphy')).toHaveTextContent('Morphy');
        expect(screen.getByTestId('legend-result-morphy')).toHaveTextContent('1 pt');
        expect(screen.getByTestId('legend-play-philidor')).toBeInTheDocument();
        expect(screen.getByTestId('weekly-meta')).toHaveTextContent('Time control 10+5 · 2 d 3 h left');
        expect(screen.getByTestId('weekly-standings')).toHaveTextContent('alice');
        expect(screen.getByTestId('weekly-last-winner')).toHaveTextContent('bob (4.5 pt)');
    });

    it('"Play" opens the game on the server and hands it to the board', async () => {
        const fetchMock = vi.fn(async (url: string) => (String(url).endsWith('/start')
            ? response(200, {bot_id: 'philidor', color: 'black', base_time_ms: 600_000, increment_ms: 5_000, abandoned: null})
            : response(200, EVENT)));
        vi.stubGlobal('fetch', fetchMock);
        renderPage();
        fireEvent.click(await screen.findByTestId('legend-play-philidor'));
        await waitFor(() => expect(screen.getByTestId('board-state')).toHaveTextContent('"botId":"philidor"'));
        const start = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/start')) as unknown as [string, RequestInit];
        expect(JSON.parse(String(start[1].body))).toEqual({bot_id: 'philidor', color: 'random'});
    });

    it('a guest sees the line-up but no "Play"', async () => {
        clearToken();
        vi.stubGlobal('fetch', vi.fn(async () => response(200, EVENT)));
        renderPage();
        expect(await screen.findByText('Log in to play the legends.')).toBeInTheDocument();
        expect(screen.queryByTestId('legend-play-philidor')).toBeNull();
    });
});

describe('WeeklyLegendsBanner and the status line', () => {
    it('the banner links to the page with the time left', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => response(200, EVENT)));
        render(<MemoryRouter><WeeklyLegendsBanner/></MemoryRouter>);
        const banner = await screen.findByTestId('weekly-banner');
        expect(banner).toHaveAttribute('href', '/events/weekly');
        expect(banner).toHaveTextContent('2 d 3 h left');
    });

    it('a counted game and a forfeit read differently', () => {
        expect(weeklyOutcomeMessage({points: 0.5, forfeit: null, total: 2})).toEqual(
            {key: 'weeklyLegends.result', params: {points: 0.5, total: 2}});
        expect(weeklyOutcomeMessage({points: 0, forfeit: 'takeback', total: 1}).key).toBe('weeklyLegends.resultForfeit');
    });
});
