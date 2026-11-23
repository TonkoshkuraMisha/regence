// Trainer games (task 19.8): the list, a click move goes to the server, the bot's reply, the result, a move error, playing as Black.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {MINI_GAMES, MiniGamePage, MiniGamesPage} from '../MiniGames';
import {setToken} from '../../../services/authToken';

afterEach(() => {
    vi.unstubAllGlobals();
    setToken(null);
});

const page = (path: string) => render(
    <MemoryRouter initialEntries={[path]}>
        <Routes>
            <Route path="/train/games" element={<MiniGamesPage/>}/>
            <Route path="/train/games/:gameId" element={<MiniGamePage/>}/>
        </Routes>
    </MemoryRouter>,
);
const click = (square: string) => fireEvent.click(document.querySelector(`[data-square="${square}"]`)!);

describe('trainer games', () => {
    it('the list — five games with links', () => {
        page('/train/games');
        expect(MINI_GAMES.map((id) => screen.getByTestId(`mini-${id}`).getAttribute('href'))).toEqual(MINI_GAMES.map((id) => `/train/games/${id}`));
    });

    it('a click move — to the server; the bot replies; the result', async () => {
        const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
            const body = JSON.parse(String(init!.body));
            const won = body.move === 'a7a8';
            return {ok: true, json: async () => (won
                ? {fen: 'Q7/8/8/8/8/8/8/8 b - - 0 1', result: '1-0', bot_move: null}
                : {fen: '8/pppppppp/8/8/4P3/8/PPPP1PPP/8 w - - 0 2', result: null, bot_move: 'd7d6'})} as Response;
        });
        vi.stubGlobal('fetch', fetchMock);
        page('/train/games/pawn_war');
        expect(screen.getByTestId('mini-status')).toHaveTextContent('White to move');
        click('e2');
        await act(async () => click('e4'));
        expect(JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body))).toMatchObject({move: 'e2e4', bot: true});
        expect(String((fetchMock.mock.calls[0] as unknown as [string])[0])).toContain('/mini-games/pawn_war/move');
        click('a7');
        await act(async () => click('a8'));
        expect(screen.getByTestId('mini-status')).toHaveTextContent('White wins!');
        // Without login progress is not written.
        expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/learn/progress/'))).toBe(false);
    });

    it('a win over the bot counts a course step (the mini-<id> record)', async () => {
        setToken('jwt');
        const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({ok: true, json: async () => (
            {fen: 'Q7/8/8/8/8/8/8/8 b - - 0 1', result: '1-0', bot_move: null})}) as Response);
        vi.stubGlobal('fetch', fetchMock);
        page('/train/games/pawn_war');
        click('a7');
        await act(async () => click('a8'));
        const put = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT');
        expect(String(put?.[0])).toContain('/learn/progress/mini-pawn-war');
        expect(JSON.parse(String(put?.[1]?.body))).toMatchObject({completed: true});
    });

    it('two players — without a bot; as Black — the bot moves first; a move error is shown', async () => {
        const fetchMock = vi.fn(async (url: string) => {
            if (String(url).endsWith('/bot-first')) {
                return {ok: true, json: async () => ({fen: '4k3/pppppppp/8/8/4P3/8/PPPP1PPP/4K3 b - - 0 1', result: null, bot_move: 'e2e4'})} as Response;
            }
            return {ok: false, status: 400, json: async () => ({detail: {code: 'mini_game_illegal_move', message: 'x'}})} as Response;
        });
        vi.stubGlobal('fetch', fetchMock);
        page('/train/games/capture_flag');
        fireEvent.click(screen.getByTestId('mini-mode-hotseat'));
        click('e2');
        await act(async () => click('e5'));
        expect(JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body)).bot).toBe(false);
        expect(screen.getByRole('alert')).toHaveTextContent('This move is not allowed by the rules of the game');
        await act(async () => fireEvent.click(screen.getByTestId('mini-mode-bot-black')));
        expect(screen.getByTestId('mini-status')).toHaveTextContent('Black to move');
    });

    it('an unknown game — a message', () => {
        page('/train/games/chess960');
        expect(screen.getByText('There is no such game.')).toBeInTheDocument();
    });
});
