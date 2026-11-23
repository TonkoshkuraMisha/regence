// Pause of a game with a bot (owner decision 22.11): in a friendly game the clocks and the bot stand still, the position is hidden by a cover,
// moves are not accepted; the pause survives a reload; there is no pause in a ladder game (otherwise one could think without a clock).

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import Chessboard from '../Chessboard';
import {mockFetchRouter} from '../../test/mocks';
import {resetBotCatalogCache} from '../../services/botCatalog';
import {setToken} from '../../services/authToken';
import {openBots} from '../../test/newGame';
import {loadBotGameSnapshot, saveBotGameSnapshot} from '../../services/botGameSnapshot';

vi.mock('../../services/gameSocket', () => ({
    gameSocket: {connect: vi.fn(), disconnect: vi.fn(), send: vi.fn(), on: vi.fn(), off: vi.fn()},
}));
vi.mock('../../services/soundEngine', async (importOriginal) => {
    const actual = await importOriginal<typeof import('../../services/soundEngine')>();
    return {...actual, soundEngine: {play: vi.fn(), isMuted: vi.fn(() => false), toggleMute: vi.fn(() => true)}};
});

const stubApi = () => vi.stubGlobal('fetch', mockFetchRouter({
    '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
    '/profile/matchmaking/queue': () => [],
    '/profile/games/live': () => [],
    '/profile/games/my-active': () => ({active: false}),
    '/bots/move': () => new Promise(() => {}),   // the bot "thinks" forever: we do not need its move
    '/bots/save-game': () => ({game_id: 1, status: 'finished', result: '1-0'}),
}));

const renderBoard = () => render(<MemoryRouter initialEntries={['/']}><Chessboard/></MemoryRouter>);
const square = (id: string) => document.querySelector(`[data-square="${id}"]`) as HTMLElement;
const hasPiece = (id: string) => square(id).querySelector('img,svg,[data-piece]') !== null;

const SNAPSHOT = {
    username: 'TestPlayer', botId: 'philidor', custom: null, color: 'white' as const, pgn: '1. e4 e5',
    whiteTimeMs: 200000, blackTimeMs: 250000, baseMinutes: 5, incrementSeconds: 0, odds: null,
    ladder: false, tournamentGameId: null, tournamentId: null,
};

beforeEach(() => {
    resetBotCatalogCache();
    setToken('test-token');
    vi.useFakeTimers({shouldAdvanceTime: true});
});
afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    localStorage.clear();
});

describe('pause of a game with a bot', () => {
    it('the pause hides the position and accepts no moves, resuming returns the game', async () => {
        stubApi();
        renderBoard();
        await openBots();
        await act(async () => fireEvent.click(await screen.findByRole('button', {name: /White/})));

        await act(async () => fireEvent.click(await screen.findByTestId('bot-pause')));
        expect(screen.getByTestId('bot-paused-overlay')).toBeInTheDocument();
        fireEvent.click(square('e2'));
        fireEvent.click(square('e4'));
        expect(hasPiece('e2')).toBe(true);
        expect(hasPiece('e4')).toBe(false);   // the move was not made during the pause

        await act(async () => fireEvent.click(screen.getByTestId('bot-resume')));
        expect(screen.queryByTestId('bot-paused-overlay')).toBeNull();
        await act(async () => fireEvent.click(square('e2')));
        await act(async () => fireEvent.click(square('e4')));
        expect(hasPiece('e4')).toBe(true);
    });

    it('the pause survives a reload: a snapshot with a pause opens with the cover, and a recorded snapshot remembers the pause', async () => {
        stubApi();
        saveBotGameSnapshot({...SNAPSHOT, paused: true}, Date.now() - 3600_000);
        renderBoard();
        expect(await screen.findByTestId('bot-paused-overlay')).toBeInTheDocument();
        await waitFor(() => expect(loadBotGameSnapshot('TestPlayer')?.paused).toBe(true));
        await act(async () => fireEvent.click(screen.getByTestId('bot-resume')));
        await waitFor(() => expect(loadBotGameSnapshot('TestPlayer')?.paused).toBe(false));
    });

    it('there is no pause in a ladder game', async () => {
        stubApi();
        saveBotGameSnapshot({...SNAPSHOT, ladder: true});
        renderBoard();
        await waitFor(() => expect(hasPiece('e4')).toBe(true));   // the game went on
        expect(screen.queryByTestId('bot-pause')).toBeNull();
    });
});
