// --- FILE: frontend/src/components/__tests__/ChessboardPvp.test.tsx ---
// PvP and spectating games through WebSocket events: foreign events must not change the board,
// a lost game_over is restored over HTTP, a challenge returns to the lobby after a connection drop.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi, type Mock} from 'vitest';
import Chessboard from '../Chessboard';
import {gameSocket} from '../../services/gameSocket';
import {emitSocketEvent, mockFetchRouter} from '../../test/mocks';
import {setLanguage} from '../../i18n';
import {setToken} from '../../services/authToken';
import {openHuman} from '../../test/newGame';

vi.mock('../../services/gameSocket', () => ({
    gameSocket: {
        connect: vi.fn(),
        disconnect: vi.fn(),
        send: vi.fn(),
        on: vi.fn(),
        off: vi.fn(),
    },
}));

vi.mock('../../services/soundEngine', async (importOriginal) => {
    const actual = await importOriginal<typeof import('../../services/soundEngine')>();
    return {
        ...actual,
        soundEngine: {
            play: vi.fn(),
            isMuted: vi.fn(() => false),
            toggleMute: vi.fn(() => true),
        },
    };
});

const onMock = gameSocket.on as unknown as Mock;
const sendMock = gameSocket.send as unknown as Mock;

const MATCH = {
    event: 'match_found',
    game_id: 5,
    color: 'white',
    opponent_id: 2,
    white_username: 'TestPlayer',
    white_rating: 1500,
    black_username: 'Rival',
    black_rating: 1510,
    base_time_ms: 180000,
    increment_ms: 0,
    white_time_ms: 180000,
    black_time_ms: 180000,
    fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    pgn: '',
    state_version: 0,
};

/** The last registered handler of the event (the effect could have resubscribed). */
function emit(event: string, data: any) {
    const calls = onMock.mock.calls.filter(([name]: [string]) => name === event);
    if (calls.length === 0) {
        emitSocketEvent(onMock, event, data);
        return;
    }
    calls[calls.length - 1][1](data);
}

async function emitAct(event: string, data: any) {
    await act(async () => {
        emit(event, data);
    });
}

function renderBoard(fetchHandlers: Record<string, () => unknown> = {}) {
    vi.stubGlobal('fetch', mockFetchRouter({
        '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
        '/profile/matchmaking/queue': () => [],
        '/profile/games/live': () => [],
        '/profile/games/my-active': () => ({active: false}),
        ...fetchHandlers,
    }));
    return render(
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

describe('events of another game', () => {
    it('a move and the result of another game do not change the board and do not finish the current one', async () => {
        renderBoard({'/profile/games/my-active': () => ({...MATCH, active: true})});
        await emitAct('match_found', MATCH);

        await emitAct('move_made', {game_id: 7, state_version: 1, pgn: '1. d4', san: 'd4', game_over: false});
        expect(screen.queryByText('d4')).not.toBeInTheDocument();

        await emitAct('game_over', {game_id: 7, result: '0-1', reason: 'resignation'});
        expect(screen.queryByText(/Game over/)).not.toBeInTheDocument();

        await emitAct('move_made', {game_id: 5, state_version: 1, pgn: '1. e4', san: 'e4', game_over: false});
        expect(screen.getByText('e4')).toBeInTheDocument();
    });

    it('the result of one\'s own game is shown together with the reason', async () => {
        renderBoard({'/profile/games/my-active': () => ({...MATCH, active: true})});
        await emitAct('match_found', MATCH);
        await emitAct('game_over', {game_id: 5, result: '1-0', reason: 'resignation', white_delta: 8, black_delta: -8});

        expect(screen.getByText('Game over. Result: 1-0 (resignation)')).toBeInTheDocument();
    });
});

describe('draw offer', () => {
    it('is restored from the game snapshot and cleared by a reply move', async () => {
        const snapshot = {...MATCH, pgn: '1. e4 e5', state_version: 2, draw_offer_from: 2};
        renderBoard({'/profile/games/my-active': () => ({...snapshot, active: true})});
        await emitAct('match_found', snapshot);

        expect(screen.getByText('Your opponent offers a draw.')).toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Accept'})).toBeInTheDocument();

        // The player (White) replies with a move — the offer is declined, the buttons disappear.
        await emitAct('move_made', {game_id: 5, state_version: 3, pgn: '1. e4 e5 2. Nf3', san: 'Nf3', game_over: false});
        expect(screen.queryByText('Your opponent offers a draw.')).not.toBeInTheDocument();
    });
});

describe('berserk in an arena game (33.3)', () => {
    const ARENA_MATCH = {...MATCH, increment_ms: 2000, arena_id: 3, berserk_allowed: true, white_berserk: false,
        black_berserk: false};
    const BERSERK = {game_id: 5, color: 'white', white_time_ms: 90000, black_time_ms: 180000, berserk_allowed: true,
        white_berserk: true, black_berserk: false};

    it('the button before the first move sends the action; the event marks the player and removes the button', async () => {
        renderBoard({'/profile/games/my-active': () => ({...ARENA_MATCH, active: true})});
        await emitAct('match_found', ARENA_MATCH);
        expect(screen.queryByTestId('berserk-mark')).toBeNull();

        fireEvent.click(screen.getByTestId('berserk-button'));
        expect(sendMock).toHaveBeenCalledWith('berserk', {game_id: 5});

        await emitAct('berserk', BERSERK);
        expect(screen.queryByTestId('berserk-button')).toBeNull();
        expect(screen.getAllByTestId('berserk-mark')).toHaveLength(1);
        expect(screen.getByRole('img', {name: 'Berserk: half the time, no increment'})).toBeInTheDocument();
    });

    it('the opponent\'s berserk is visible and one\'s own button stays; after one\'s own first move it is gone', async () => {
        renderBoard({'/profile/games/my-active': () => ({...ARENA_MATCH, active: true})});
        await emitAct('match_found', ARENA_MATCH);
        await emitAct('berserk', {...BERSERK, color: 'black', white_time_ms: 180000, black_time_ms: 90000,
            white_berserk: false, black_berserk: true});
        expect(screen.getAllByTestId('berserk-mark')).toHaveLength(1);
        expect(screen.getByTestId('berserk-button')).toBeInTheDocument();

        await emitAct('move_made', {game_id: 5, state_version: 1, pgn: '1. e4', san: 'e4', game_over: false});
        expect(screen.queryByTestId('berserk-button')).toBeNull();
        expect(screen.getAllByTestId('berserk-mark')).toHaveLength(1);
    });

    it('Black can play berserk after White\'s first move; in an ordinary game there is no button', async () => {
        const asBlack = {...ARENA_MATCH, color: 'black', opponent_id: 1, white_username: 'Rival',
            black_username: 'TestPlayer', pgn: '1. e4', state_version: 1};
        const view = renderBoard({'/profile/games/my-active': () => ({...asBlack, active: true})});
        await emitAct('match_found', asBlack);
        expect(screen.getByTestId('berserk-button')).toBeInTheDocument();
        view.unmount();

        renderBoard({'/profile/games/my-active': () => ({...MATCH, active: true})});
        await emitAct('match_found', MATCH);
        expect(screen.queryByTestId('berserk-button')).toBeNull();
    });

    it('a foreign berserk event and a snapshot of the same game without berserk fields change nothing', async () => {
        renderBoard({'/profile/games/my-active': () => ({...MATCH, active: true})});
        await emitAct('match_found', ARENA_MATCH);
        await emitAct('berserk', {...BERSERK, game_id: 7});
        expect(screen.queryByTestId('berserk-mark')).toBeNull();

        await emitAct('berserk', BERSERK);
        // The my-active poll returns a snapshot without berserk fields — the mark stays.
        await act(async () => {
            await vi.advanceTimersByTimeAsync(3500);
        });
        expect(screen.getAllByTestId('berserk-mark')).toHaveLength(1);
    });
});

describe('a lost game_over', () => {
    it('a game that is no longer on the server finishes by the HTTP result', async () => {
        renderBoard({
            '/profile/games/5/summary': () => ({
                game_id: 5, status: 'COMPLETED', result: '0-1', termination: 'timeout',
                white_delta: -8, black_delta: 8,
            }),
        });
        await emitAct('match_found', MATCH);

        // The my-active poll every 1.5 s answers "no active game" twice in a row.
        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000);
        });

        await waitFor(() => {
            expect(screen.getByText('Game over. Result: 0-1 (time ran out)')).toBeInTheDocument();
        });
    });

    it('until the result is recorded on the server, the game on the screen goes on', async () => {
        renderBoard({
            '/profile/games/5/summary': () => ({game_id: 5, status: 'IN_PROGRESS', result: null, termination: null}),
        });
        await emitAct('match_found', MATCH);
        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000);
        });

        expect(screen.queryByText(/Game over/)).not.toBeInTheDocument();
        expect(screen.getByText('Rated game in progress')).toBeInTheDocument();
    });
});

describe('opponent search', () => {
    it('after the WebSocket reconnects the challenge returns to the lobby', async () => {
        renderBoard();
        await openHuman();
        await act(async () => {
            fireEvent.click(await screen.findByRole('button', {name: /Find an opponent/}));
        });
        const joinsBefore = sendMock.mock.calls.filter(([action]) => action === 'join_queue').length;
        expect(joinsBefore).toBe(1);

        await emitAct('connected', {event: 'connected'});

        const joins = sendMock.mock.calls.filter(([action]) => action === 'join_queue');
        expect(joins).toHaveLength(2);
        expect(joins[1][1]).toEqual(joins[0][1]);
    });

    it('connected without an active search sends nothing', async () => {
        renderBoard();
        await emitAct('connected', {event: 'connected'});
        expect(sendMock.mock.calls.filter(([action]) => action === 'join_queue')).toHaveLength(0);
    });

    it('"you are already playing" when the game has already started is not shown as an error', async () => {
        renderBoard({'/profile/games/my-active': () => ({...MATCH, active: true})});
        await emitAct('match_found', MATCH);
        await emitAct('error', {event: 'error', code: 'self_in_game', message: 'You are already playing a game'});

        expect(screen.queryByText('You are already playing a game')).not.toBeInTheDocument();
    });

    it('a server refusal with a code is shown from the catalogue in the player\'s language and is translated when the language changes', async () => {
        renderBoard();
        await emitAct('error', {
            event: 'error', code: 'rating_out_of_range',
            params: {rating: 1500, min: 1600, max: 1800}, message: 'Your rating 1500 is outside the challenge range (1600–1800)',
        });
        expect(screen.getByText('Your rating 1500 is outside the challenge range (1600–1800)')).toBeInTheDocument();

        act(() => setLanguage('uk', {persist: false}));
        expect(screen.getByText('Ваш рейтинг 1500 поза діапазоном виклику (1600–1800)')).toBeInTheDocument();
    });
});

describe('spectator', () => {
    const SPECTATE = {
        event: 'spectate_started', game_id: 9,
        white_username: 'Alpha', white_rating: 1600, black_username: 'Beta', black_rating: 1610,
        base_time_ms: 180000, increment_ms: 0, white_time_ms: 170000, black_time_ms: 175000,
        fen: '', pgn: '1. e4 e5', state_version: 2,
    };

    it('cannot write in the chat, move pieces and does not see the sandbox buttons', async () => {
        renderBoard();
        await emitAct('spectate_started', SPECTATE);

        expect(screen.getByText('Spectators can only read the chat.')).toBeInTheDocument();
        expect(screen.queryByPlaceholderText('Write a message…')).not.toBeInTheDocument();
        expect(screen.queryByRole('button', {name: /Reset board/})).not.toBeInTheDocument();

        const whitePawn = document.querySelector('[data-square="d2"] > div.relative') as HTMLElement;
        fireEvent.pointerDown(whitePawn, {button: 0, pointerType: 'mouse', clientX: 10, clientY: 10});
        fireEvent.pointerUp(window, {clientX: 10, clientY: 10});
        expect(screen.queryByText(/Premove:/)).not.toBeInTheDocument();
    });

    it('the start of one\'s own game ends spectating on the server', async () => {
        renderBoard();
        await emitAct('spectate_started', SPECTATE);
        await emitAct('match_found', MATCH);

        expect(sendMock).toHaveBeenCalledWith('leave_spectate', {game_id: 9});
        // The moves of the watched game no longer reach the board.
        await emitAct('move_made', {game_id: 9, state_version: 3, pgn: '1. e4 e5 2. Nf3', san: 'Nf3', game_over: false});
        expect(screen.queryByText('Nf3')).not.toBeInTheDocument();
    });
});

describe('result of a game with a person', () => {
    it('after the game ends — the review of this game and the key moves; during the game the review is not requested', async () => {
        renderBoard({
            '/profile/games/my-active': () => ({...MATCH, active: true}),
            '/analysis/game/5': () => ({
                white: {accuracy: 91}, black: {accuracy: 64},
                moves: [{ply: 1, move_number: 1, color: 'white', san: 'e4'}, {ply: 2, move_number: 1, color: 'black', san: 'f6'}],
                summary: {kind: 'decisive_blunder', turning_point_ply: 2, lead_changes: 0, equal_share: 0.5,
                          white: {best_ply: 1, worst_ply: null}, black: {best_ply: null, worst_ply: 2}},
            }),
            '/learn/after-game/5': () => ({cards: []}),
        });
        await emitAct('match_found', MATCH);
        const analysisCalls = () => (vi.mocked(fetch).mock.calls as unknown as [string][]).filter(([url]) => String(url).includes('/analysis/game/'));
        expect(analysisCalls()).toHaveLength(0);  // fair play: during the game — not a single review request

        await emitAct('game_over', {game_id: 5, result: '1-0', reason: 'resignation'});
        const summary = await screen.findByTestId('game-summary');
        await waitFor(() => expect(summary.textContent).toContain('Decided by one mistake'));
        expect(String(analysisCalls()[0][0])).toContain('/analysis/game/5');
        expect(screen.queryByTestId('summary-recommendation')).toBeNull();  // we do not recommend a bot opponent
    });
});

describe('rematch', () => {
    it('leaving a finished game withdraws one\'s own rematch offer', async () => {
        renderBoard({'/profile/games/my-active': () => ({...MATCH, active: true})});
        await emitAct('match_found', MATCH);
        await emitAct('game_over', {game_id: 5, result: '1-0', reason: 'resignation'});

        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /^Rematch$/}));
        });
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /To the lobby/}));
        });

        expect(sendMock).toHaveBeenCalledWith('decline_rematch', {game_id: 5});
    });
});

describe('casual games', () => {
    it('the chosen type goes to the server over WebSocket and HTTP and returns after a reconnect', async () => {
        renderBoard();
        await openHuman();
        await act(async () => {
            fireEvent.click(await screen.findByRole('radio', {name: 'Casual'}));
        });
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Find an opponent/}));
        });

        const joins = () => sendMock.mock.calls.filter(([action]) => action === 'join_queue');
        expect(joins()[0][1]).toMatchObject({rated: false});
        const fetchMock = fetch as unknown as Mock;
        const httpJoin = fetchMock.mock.calls.find(([url]) => String(url).includes('/matchmaking/join'));
        expect(JSON.parse(httpJoin![1].body)).toMatchObject({rated: false});
        expect(screen.getByText(/casual challenge/)).toBeInTheDocument();
        // While the search is on the type cannot be changed — the challenge is already published.
        expect(screen.getByRole('radio', {name: 'Rated'})).toBeDisabled();

        await emitAct('connected', {event: 'connected'});
        expect(joins()[1][1]).toMatchObject({rated: false});
    });

    it('an invitation by link is created of the chosen type', async () => {
        renderBoard();
        await openHuman();
        await act(async () => {
            fireEvent.click(await screen.findByRole('radio', {name: 'Casual'}));
            fireEvent.click(screen.getByRole('button', {name: /With a friend/}));
        });
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Generate and copy the link/}));
        });

        expect(sendMock).toHaveBeenCalledWith('create_invite', expect.objectContaining({rated: false}));
    });

    it('an invitation with odds (21.1): the kind of odds and who gives go to the server', async () => {
        renderBoard();
        await openHuman();
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /With a friend/}));
        });
        fireEvent.change(screen.getByTestId('invite-odds-kind'), {target: {value: 'knight'}});
        expect(screen.getByTestId('invite-odds')).toHaveTextContent('does not change ratings');
        fireEvent.change(screen.getByTestId('invite-odds-giver'), {target: {value: 'opponent'}});
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Generate and copy the link/}));
        });
        expect(sendMock).toHaveBeenCalledWith('create_invite', expect.objectContaining({odds_kind: 'knight', odds_giver: 'acceptor'}));
    });

    it('"hourglass" (21.1): without choosing "who gives", the kind goes to the server; the waiting player\'s clock grows', async () => {
        renderBoard();
        await openHuman();
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /With a friend/}));
        });
        fireEvent.change(screen.getByTestId('invite-odds-kind'), {target: {value: 'hourglass'}});
        expect(screen.queryByTestId('invite-odds-giver')).toBeNull();
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Generate and copy the link/}));
        });
        expect(sendMock).toHaveBeenCalledWith('create_invite', expect.objectContaining({odds_kind: 'hourglass'}));

        await emitAct('match_found', {...MATCH, hourglass: true});
        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000);
        });
        // White thinks for 5 seconds: they have 02:55, Black has 03:05.
        expect(screen.getAllByText('02:55').length).toBeGreaterThan(0);
        expect(screen.getAllByText('03:05').length).toBeGreaterThan(0);
    });

    it('a Fischer game (21.3): the variant goes to the server, the odds are hidden; match_found 960 leads to its own page', async () => {
        vi.stubGlobal('fetch', mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [], '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
        }));
        render(
            <MemoryRouter initialEntries={['/']}>
                <Routes>
                    <Route path="/" element={<Chessboard/>}/>
                    <Route path="/play/960/live" element={<div data-testid="live-960-route"/>}/>
                </Routes>
            </MemoryRouter>,
        );
        await openHuman();
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /With a friend/}));
        });
        fireEvent.change(screen.getByTestId('invite-variant-select'), {target: {value: 'chess960'}});
        expect(screen.queryByTestId('invite-odds')).toBeNull();
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Generate and copy the link/}));
        });
        expect(sendMock).toHaveBeenCalledWith('create_invite', expect.objectContaining({variant: 'chess960'}));
        expect(sendMock).not.toHaveBeenCalledWith('create_invite', expect.objectContaining({odds_kind: expect.anything()}));
        await emitAct('match_found', {...MATCH, variant: 'chess960', fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w HAha - 0 1'});
        expect(screen.getByTestId('live-960-route')).toBeInTheDocument();
    });

    it('the type of a game in progress is taken from the server snapshot, the rating change is not shown', async () => {
        const casual = {...MATCH, is_rated: false};
        renderBoard({'/profile/games/my-active': () => ({...casual, active: true})});
        await emitAct('match_found', casual);

        expect(screen.getByText('Casual game in progress')).toBeInTheDocument();

        await emitAct('game_over', {game_id: 5, result: '1-0', reason: 'resignation', white_delta: 0, black_delta: 0});
        expect(screen.queryByText('(+0)')).not.toBeInTheDocument();
    });

    it('a rated game shows the rating change', async () => {
        renderBoard({'/profile/games/my-active': () => ({...MATCH, active: true})});
        await emitAct('match_found', MATCH);
        expect(screen.getByText('Rated game in progress')).toBeInTheDocument();

        await emitAct('game_over', {game_id: 5, result: '1-0', reason: 'resignation', white_delta: 8, black_delta: -8});
        expect(screen.getByText('(+8)')).toBeInTheDocument();
    });

    it('a casual challenge is marked in the lobby', async () => {
        renderBoard({
            '/profile/matchmaking/queue': () => [
                {user_id: 7, username: 'Friendly', rating: 1500, base_time_ms: 180000, increment_ms: 0, rated: false},
                {user_id: 8, username: 'Serious', rating: 1500, base_time_ms: 180000, increment_ms: 0, rated: true},
            ],
        });
        // The lobby is always in the left column of the game hall (the "Bots / Lobby" tabs are gone: bots are in the "New game" window).
        const friendly = (await screen.findByText('Friendly')).closest('div')!.parentElement!;
        expect(friendly.textContent).toContain('casual');
        const serious = screen.getByText('Serious').closest('div')!.parentElement!;
        expect(serious.textContent).not.toContain('casual');
    });
});

describe('spectator mode from the "View" page (16.3)', () => {
    it('the board itself asks the server to show the game from location.state', async () => {
        vi.stubGlobal('fetch', mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
        }));
        render(
            <MemoryRouter initialEntries={[{pathname: '/', state: {spectate: 42}}]}>
                <Chessboard/>
            </MemoryRouter>,
        );
        await act(async () => undefined);
        expect(sendMock).toHaveBeenCalledWith('spectate_game', {game_id: 42});
    });
});

describe('a direct challenge from the profile (17.1)', () => {
    it('the board creates an invitation and sends it to the opponent by a notification', async () => {
        const fetchMock = mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
            '/social/challenge/magnus': () => ({sent: true, online: true}),
        });
        vi.stubGlobal('fetch', fetchMock);
        render(
            <MemoryRouter initialEntries={[{pathname: '/', state: {challenge: 'magnus'}}]}>
                <Chessboard/>
            </MemoryRouter>,
        );
        await act(async () => undefined);
        expect(sendMock).toHaveBeenCalledWith('create_invite', expect.objectContaining({color_pref: expect.any(String)}));
        await emitAct('invite_created', {code: 'abc12345'});
        expect(await screen.findByTestId('challenge-sent')).toHaveTextContent('magnus');
        const call = (fetchMock as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls
            .find(([url]) => String(url).includes('/social/challenge/magnus'))!;
        expect(JSON.parse(String(call[1].body))).toEqual({code: 'abc12345'});
    });
});
