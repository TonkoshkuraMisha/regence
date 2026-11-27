// Board settings (task 18.4): storage, the order of captured pieces, "quick move"; on the board — the last move arrow,
// a quick move and the animation of the opponent's move.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {Chess} from 'chess.js';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {
    DEFAULT_BOARD_PREFS, getBoardPrefs, orderCaptured, quickMoveFrom, reloadBoardPrefs, setBoardPref,
} from '../boardPrefs';
import Chessboard from '../../components/Chessboard';
import {resetBotCatalogCache} from '../../services/botCatalog';
import {setToken} from '../../services/authToken';
import {mockFetchRouter} from '../../test/mocks';
import {openBots} from '../../test/newGame';

// How long the board test waits for the bot's reply and its animation: generous because the full suite runs in
// parallel workers and a mocked reply can still take seconds there (the test's own limit is 20 s).
const BOT_REPLY_WAIT_MS = 5000;

vi.mock('../../services/gameSocket', () => ({gameSocket: {connect: vi.fn(), disconnect: vi.fn(), send: vi.fn(), on: vi.fn(), off: vi.fn()}}));
vi.mock('../../services/soundEngine', async (importOriginal) => ({
    ...(await importOriginal<typeof import('../../services/soundEngine')>()),
    soundEngine: {play: vi.fn(), isMuted: vi.fn(() => false), toggleMute: vi.fn(() => true)},
}));

beforeEach(() => {
    localStorage.clear();
    reloadBoardPrefs();
});

afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    reloadBoardPrefs();
});

describe('board settings', () => {
    it('by default — as before; the choice is saved; junk in storage is ignored', () => {
        expect(getBoardPrefs()).toEqual(DEFAULT_BOARD_PREFS);
        setBoardPref('lastMove', 'arrow');
        expect(JSON.parse(localStorage.getItem('regence_board_prefs')!).lastMove).toBe('arrow');
        localStorage.setItem('regence_board_prefs', JSON.stringify({lastMove: 'laser', quickMove: 'yes', captured: 'order'}));
        reloadBoardPrefs();
        expect(getBoardPrefs()).toEqual({...DEFAULT_BOARD_PREFS, captured: 'order'});
        localStorage.setItem('regence_board_prefs', '{broken');
        reloadBoardPrefs();
        expect(getBoardPrefs()).toEqual(DEFAULT_BOARD_PREFS);
    });

    it('captured pieces: by value, by kind, by order of capture', () => {
        const byValue = {white: ['♛', '♞', '♟'], black: ['♝', '♟']};
        expect(orderCaptured('value', byValue, [])).toBe(byValue);
        expect(orderCaptured('kind', byValue, [])).toEqual({white: ['♟', '♞', '♛'], black: ['♟', '♝']});
        const history = [{color: 'w', captured: 'p'}, {color: 'b', captured: 'n'}, {color: 'w'}, {color: 'w', captured: 'q'}];
        expect(orderCaptured('order', byValue, history)).toEqual({white: ['♟', '♛'], black: ['♞']});
    });

    it('a quick move — only when exactly one piece can go to the square', () => {
        const start = new Chess().moves({verbose: true});
        expect(quickMoveFrom(start, 'e4')).toBe('e2');
        expect(quickMoveFrom(start, 'a4')).toBe('a2');
        expect(quickMoveFrom(start, 'f3')).toBeNull();   // both the knight g1 and the pawn f2 can — the choice is ambiguous
        expect(quickMoveFrom(start, 'e5')).toBeNull();
        const knights = new Chess('4k3/8/8/8/8/8/8/1N2KN2 w - - 0 1').moves({verbose: true});
        expect(quickMoveFrom(knights, 'd2')).toBeNull();
    });
});

describe('settings on the board', () => {
    const squareEl = (square: string) => document.querySelector(`[data-square="${square}"]`) as HTMLElement;

    async function startBotGame() {
        resetBotCatalogCache();
        setToken('test-token');
        vi.stubGlobal('fetch', mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
            '/bots/move': () => ({uci: 'e7e5', san: 'e5', fen_after: '', source: 'book', comment: '', thinking_time_ms: 10}),
        }));
        render(<MemoryRouter><Chessboard/></MemoryRouter>);
        await openBots();
        const start = await screen.findByRole('button', {name: /White/});
        await act(async () => fireEvent.click(start));
    }

    it('the last move arrow instead of the highlight; a quick move by a click on a square; the animation of the bot\'s reply', async () => {
        setBoardPref('lastMove', 'arrow');
        setBoardPref('quickMove', true);
        await startBotGame();
        await act(async () => fireEvent.click(squareEl('e4')));   // only the pawn e2 can take e4
        expect(screen.getByText('e4')).toBeInTheDocument();
        expect(await screen.findByTestId('last-move-arrow', {}, {timeout: BOT_REPLY_WAIT_MS})).toBeInTheDocument();
        // The bot's reply (e7e5) is animated. The reply goes through the mocked request and the hook's minimum think
        // pause, which under a full parallel run takes longer than the default 1 s of findBy; the animation node is
        // caught by the DOM observer as soon as it is inserted, so a wider wait does not miss its short life.
        const sliding = await screen.findByTestId('move-animation', {}, {timeout: BOT_REPLY_WAIT_MS});
        // The piece is already on its own square (the squares show the real position) and slides there from the old one.
        expect(squareEl('e5').contains(sliding)).toBe(true);
        expect(sliding.querySelector('img')).not.toBeNull();
        await waitFor(() => expect(screen.queryByTestId('move-animation')).toBeNull(), {timeout: BOT_REPLY_WAIT_MS});
        setToken(null);
    }, 20_000);  // under load (coverage measurement, CI) the default 5 s was not enough

    it('"clicks only": dragging does not start', async () => {
        setBoardPref('moveInput', 'click');
        await startBotGame();
        fireEvent.pointerDown(squareEl('e2').querySelector('div.relative.w-full') as HTMLElement, {button: 0, pointerType: 'mouse', clientX: 1, clientY: 1});
        expect(document.querySelector('[data-testid="drag-ghost"]')).toBeNull();
        fireEvent.click(squareEl('e2'));
        fireEvent.click(squareEl('e4'));
        expect(screen.getByText('e4')).toBeInTheDocument();
        setToken(null);
    });
});
