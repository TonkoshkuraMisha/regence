// --- FILE: frontend/src/components/__tests__/ChessboardBotFlow.test.tsx ---
// The course of a game with a bot in Chessboard.tsx not covered by the main tests: the player delivers mate (result, saving
// the game, the victory sound), taking back a move in a game with a bot and on a free board,
// going to a move from the list and returning to the live position. The bot answers with prepared moves (the /bots/move stub),
// time is fake timers; moves are made by clicks through test/boardMoves.ts.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import Chessboard from '../Chessboard';
import {mockFetchRouter} from '../../test/mocks';
import {resetBotCatalogCache} from '../../services/botCatalog';
import {setToken} from '../../services/authToken';
import {openBots} from '../../test/newGame';
import {boardCell, playMove} from '../../test/boardMoves';
import {soundEngine} from '../../services/soundEngine';

vi.mock('../../services/gameSocket', () => ({
    gameSocket: {connect: vi.fn(), disconnect: vi.fn(), send: vi.fn(), on: vi.fn(), off: vi.fn()},
}));

vi.mock('../../services/soundEngine', async (importOriginal) => {
    const actual = await importOriginal<typeof import('../../services/soundEngine')>();
    return {
        ...actual,
        soundEngine: {play: vi.fn(), isMuted: vi.fn(() => false), toggleMute: vi.fn(() => false)},
    };
});

const pieceAt = (square: string) => boardCell(square).querySelector('img')?.getAttribute('alt') ?? null;

/** Bot replies in order of requests: after the last one it repeats itself. */
async function startBotGame(replies: Array<{ uci: string; san: string }>) {
    let call = 0;
    const fetchMock = mockFetchRouter({
        '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
        '/profile/matchmaking/queue': () => [],
        '/profile/games/live': () => [],
        '/profile/games/my-active': () => ({active: false}),
        '/bots/move': () => {
            const reply = replies[Math.min(call, replies.length - 1)];
            call += 1;
            return {...reply, fen_after: '', source: 'book', comment: '', thinking_time_ms: 10};
        },
        '/bots/save-game': () => ({game_id: 999, status: 'finished', result: '1-0'}),
    });
    vi.stubGlobal('fetch', fetchMock);
    render(
        <MemoryRouter initialEntries={['/']}>
            <Chessboard/>
        </MemoryRouter>,
    );
    await openBots();
    await act(async () => {
        fireEvent.click(await screen.findByRole('button', {name: /White/}));
    });
    return fetchMock;
}

async function botReplies() {
    await act(async () => {
        await vi.advanceTimersByTimeAsync(500);
    });
}

beforeEach(() => {
    resetBotCatalogCache();
    setToken('test-token');
    vi.useFakeTimers({shouldAdvanceTime: true});
    vi.mocked(soundEngine.play).mockClear();
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    localStorage.clear();
});

describe('the player delivers mate', () => {
    it('the game ends with a win, the result is saved, the victory sounds; one can go back by a move from the list', async () => {
        const fetchMock = await startBotGame([{uci: 'f7f6', san: 'f6'}, {uci: 'g7g5', san: 'g5'}]);
        await playMove('e2', 'e4');
        await botReplies();
        await playMove('d2', 'd4');
        await botReplies();
        await playMove('d1', 'h5');

        expect(screen.getByText(/The game against .* is over and saved to the archive \(1-0\)/)).toBeInTheDocument();
        expect(vi.mocked(soundEngine.play)).toHaveBeenCalledWith('victory');
        const saved = (fetchMock.mock.calls as unknown as [string][]).some(([url]) => String(url).includes('/bots/save-game'));
        expect(saved).toBe(true);

        // The move list: a click on the first move shows the position after it, a repeated one on the same — changes nothing.
        fireEvent.click(screen.getByText('e4'));
        expect(pieceAt('d4')).toBeNull();
        expect(pieceAt('e4')).toBe('wp');
        fireEvent.click(screen.getByText('e4'));
        // A click on the last move returns to the live position.
        fireEvent.click(screen.getByText('Qh5#'));
        expect(pieceAt('h5')).toBe('wq');
    });
});

describe('taking back a move', () => {
    it('taking back a move in a game with a bot removes one\'s own move and the bot reply', async () => {
        await startBotGame([{uci: 'e7e5', san: 'e5'}]);
        await playMove('e2', 'e4');
        await botReplies();
        expect(pieceAt('e5')).toBe('bp');

        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Take back/}));
        });
        expect(pieceAt('e5')).toBeNull();
        expect(pieceAt('e4')).toBeNull();
        expect(pieceAt('e2')).toBe('wp');
    });
});

describe('free board: taking back a move', () => {
    it('the "Undo move" button rolls back the last move', async () => {
        vi.stubGlobal('fetch', mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
        }));
        render(
            <MemoryRouter initialEntries={['/']}>
                <Chessboard/>
            </MemoryRouter>,
        );
        await screen.findByTestId('new-game-open');
        await playMove('e2', 'e4');
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Undo move/}));
        });
        expect(pieceAt('e2')).toBe('wp');
        expect(pieceAt('e4')).toBeNull();
    });
});
