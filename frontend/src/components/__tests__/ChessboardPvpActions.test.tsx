// --- FILE: frontend/src/components/__tests__/ChessboardPvpActions.test.tsx
// Actions of a player and a spectator in a game with a person (Chessboard.tsx): aborting the game before the second half-move goes to
// the server as the abort_game command, leaving the view as the leave_spectate command. WebSocket events are fed the same way
// as in ChessboardPvp.test.tsx; the server decides on the abort, the client only sends the command.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi, type Mock} from 'vitest';
import Chessboard from '../Chessboard';
import {gameSocket} from '../../services/gameSocket';
import {emitSocketEvent, mockFetchRouter} from '../../test/mocks';
import {setToken} from '../../services/authToken';

vi.mock('../../services/gameSocket', () => ({
    gameSocket: {connect: vi.fn(), disconnect: vi.fn(), send: vi.fn(), on: vi.fn(), off: vi.fn()},
}));

vi.mock('../../services/soundEngine', async (importOriginal) => {
    const actual = await importOriginal<typeof import('../../services/soundEngine')>();
    return {
        ...actual,
        soundEngine: {play: vi.fn(), isMuted: vi.fn(() => false), toggleMute: vi.fn(() => true)},
    };
});

const onMock = gameSocket.on as unknown as Mock;
const sendMock = gameSocket.send as unknown as Mock;

const MATCH = {
    event: 'match_found', game_id: 5, color: 'white', opponent_id: 2,
    white_username: 'TestPlayer', white_rating: 1500, black_username: 'Rival', black_rating: 1510,
    base_time_ms: 180000, increment_ms: 0, white_time_ms: 180000, black_time_ms: 180000,
    fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', pgn: '', state_version: 0,
};

const SPECTATE = {
    event: 'spectate_started', game_id: 9,
    white_username: 'Alpha', white_rating: 1600, black_username: 'Beta', black_rating: 1610,
    base_time_ms: 180000, increment_ms: 0, white_time_ms: 170000, black_time_ms: 175000,
    fen: '', pgn: '1. e4 e5', state_version: 2,
};

/** The last registered handler of the event (the effect could have resubscribed). */
async function emitAct(event: string, data: unknown) {
    await act(async () => {
        const calls = onMock.mock.calls.filter(([name]: [string]) => name === event);
        if (calls.length === 0) emitSocketEvent(onMock, event, data);
        else calls[calls.length - 1][1](data);
    });
}

function renderBoard() {
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
}

beforeEach(() => {
    setToken('test-token');
    onMock.mockClear();
    sendMock.mockClear();
    vi.useFakeTimers({shouldAdvanceTime: true});
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    localStorage.clear();
});

describe('actions in a game with a person', () => {
    it('"Abort game" before the second half-move sends abort_game', async () => {
        renderBoard();
        await emitAct('match_found', MATCH);
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Abort game/}));
        });
        expect(sendMock).toHaveBeenCalledWith('abort_game', {game_id: 5});
    });

    it('a spectator leaves the view: leave_spectate, the board becomes free again', async () => {
        renderBoard();
        await emitAct('spectate_started', SPECTATE);
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Stop watching/}));
        });
        expect(sendMock).toHaveBeenCalledWith('leave_spectate', {game_id: 9});
    });
});
