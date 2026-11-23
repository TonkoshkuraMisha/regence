// --- FILE: frontend/src/components/__tests__/Chessboard.test.tsx ---
// Behavioural tests of the five key scenarios before decomposing Chessboard.tsx (task 7.13
// from ToDo.md): a move, a premove, the flag, resignation, a rematch. We run them through a game against a historical bot —
// it needs no real WebSocket handshake and uses the same executeMove/clock/premove
// as a real PvP.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import Chessboard from '../Chessboard';
import {mockFetchRouter} from '../../test/mocks';
import {DEFAULT_CONFIG} from '../../services/personalities';
import {resetBotCatalogCache} from '../../services/botCatalog';
import {setToken} from '../../services/authToken';
import {openBots} from '../../test/newGame';
import {saveBotGameSnapshot} from '../../services/botGameSnapshot';

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

const BOT_MOVE_DEFAULT = {uci: 'e7e5', san: 'e5', fen_after: '', source: 'book', comment: 'Classical.', thinking_time_ms: 10};

function renderChessboard() {
    return render(
        <MemoryRouter initialEntries={['/']}>
            <Chessboard/>
        </MemoryRouter>,
    );
}


function squareEl(square: string): HTMLElement {
    const el = document.querySelector(`[data-square="${square}"]`);
    if (!el) throw new Error(`Square ${square} not found on the board`);
    return el as HTMLElement;
}

function clickSquare(square: string) {
    fireEvent.click(squareEl(square));
}

async function startBotGame(color: 'white' | 'black', botReply: Partial<typeof BOT_MOVE_DEFAULT> = {}) {
    vi.stubGlobal('fetch', mockFetchRouter({
        '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
        '/profile/matchmaking/queue': () => [],
        '/profile/games/live': () => [],
        '/profile/games/my-active': () => ({active: false}),
        '/bots/move': () => ({...BOT_MOVE_DEFAULT, ...botReply}),
        '/bots/save-game': () => ({game_id: 999, status: 'finished', result: '1-0'}),
    }));

    renderChessboard();
    await openBots();

    const startButton = await screen.findByRole('button', {name: color === 'white' ? /White/ : /Black/});
    await act(async () => {
        fireEvent.click(startButton);
    });
}

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

describe('"New game" step by step (owner scheme 18.11)', () => {
    it('the first time — opponent, time, start; the game began — the window closed; afterwards the window opens right at the start', async () => {
        vi.stubGlobal('fetch', mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
            '/bots/move': () => BOT_MOVE_DEFAULT,
        }));
        renderChessboard();
        // The column has neither a bot catalogue nor an opponent search — only the window button.
        expect(screen.queryByRole('button', {name: /White/})).toBeNull();
        expect(screen.queryByRole('button', {name: /Find an opponent/})).toBeNull();

        fireEvent.click(await screen.findByTestId('new-game-open'));
        expect(screen.getByTestId('new-game-step-who')).toHaveAttribute('aria-current', 'step');
        expect(screen.getByTestId('new-game-step-start')).toBeDisabled();
        fireEvent.click(screen.getByTestId('new-game-who-bot'));
        expect(screen.getByTestId('new-game-step-time')).toHaveAttribute('aria-current', 'step');
        fireEvent.click(screen.getByTestId('new-game-next'));
        await act(async () => {
            fireEvent.click(await screen.findByRole('button', {name: /White/}));
        });
        expect(screen.queryByTestId('new-game')).toBeNull();
        expect(screen.getByTestId('new-game-open')).toBeDisabled();  // a game is on — a new one cannot be started
        expect(screen.getByTestId('opponent-note')).toBeInTheDocument();
        expect(localStorage.getItem('regence_new_game_who')).toBe('bot');
    });

    it('a remembered "person" — the window opens right at the opponent search; Esc closes', async () => {
        vi.stubGlobal('fetch', mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
        }));
        localStorage.setItem('regence_new_game_who', 'human');
        renderChessboard();
        fireEvent.click(await screen.findByTestId('new-game-open'));
        expect(screen.getByTestId('new-game-start-human')).toBeInTheDocument();
        expect(screen.getByRole('button', {name: /Find an opponent/})).toBeInTheDocument();
        fireEvent.keyDown(window, {key: 'Escape'});
        expect(screen.queryByTestId('new-game')).toBeNull();
    });
});

describe('move', () => {
    it('a human move to a free square is applied and goes into the move log', async () => {
        await startBotGame('white');

        clickSquare('e2');
        clickSquare('e4');

        expect(screen.getByText('e4')).toBeInTheDocument();
    });
});

describe('premove', () => {
    it('a move on the opponent\'s turn is queued and executed when it becomes the player\'s turn', async () => {
        await startBotGame('black', {uci: 'e2e4', san: 'e4', thinking_time_ms: 200});

        // The bot plays White — it is not our turn now, a click must set a premove, not a move.
        clickSquare('e7');
        clickSquare('e5');

        expect(screen.getByText(/Premove: e7 → e5/)).toBeInTheDocument();

        // The bot replies, the premove must be executed automatically.
        await act(async () => {
            await vi.advanceTimersByTimeAsync(300);
        });

        await waitFor(() => {
            expect(screen.queryByText(/Premove:/)).not.toBeInTheDocument();
        });
        expect(screen.getByText('e5')).toBeInTheDocument();
    });

    it('a chain: the second premove — with the piece from the first one\'s square, executed one by one', async () => {
        await startBotGame('black', {uci: 'e2e4', san: 'e4', thinking_time_ms: 200});
        clickSquare('g8');
        clickSquare('f6');
        // The knight already stands on f6 "in a premove" — it can be moved on.
        expect(squareEl('f6').querySelector('img')).not.toBeNull();
        clickSquare('f6');
        clickSquare('g4');
        expect(screen.getByTestId('premove-queue').textContent).toBe('Premove: g8 → f6 · Premove: f6 → g4');

        await act(async () => {
            await vi.advanceTimersByTimeAsync(300);
        });
        // The bot replied e4 — the first premove is executed, the second waits for the opponent's next move.
        await waitFor(() => expect(screen.getByTestId('premove-queue').textContent).toBe('Premove: f6 → g4'));
        expect(screen.getByText('Nf6')).toBeInTheDocument();
    });
});

describe('flag', () => {
    it('running out of time ends the game with a bot by a loss on the flag', async () => {
        await startBotGame('white');

        // It ticks every 50 ms and subtracts the really elapsed time — 3 minutes with a margin.
        await act(async () => {
            await vi.advanceTimersByTimeAsync(3 * 60 * 1000 + 2000);
        });

        expect(screen.getByText(/Flag fell!.*\(0-1\)/)).toBeInTheDocument();
    });
});

describe('resignation', () => {
    it('a confirmed resignation ends the game with the player\'s loss', async () => {
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        await startBotGame('white');

        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Resign/}));
        });

        expect(screen.getByText(/You resigned.*\(0-1\)/)).toBeInTheDocument();
    });

    it('a cancelled confirmation does not end the game', async () => {
        vi.spyOn(window, 'confirm').mockReturnValue(false);
        await startBotGame('white');

        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Resign/}));
        });

        expect(screen.queryByText(/You resigned/)).not.toBeInTheDocument();
    });
});

describe('rematch', () => {
    it('a rematch with a bot starts a new game with the opposite colour of the player', async () => {
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        await startBotGame('white');

        // a8 is first in the DOM — the board is not flipped (we play White).
        expect(squareEl('a8')).toBeInTheDocument();

        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Resign/}));
        });
        expect(screen.getByText(/You resigned/)).toBeInTheDocument();

        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Rematch/}));
        });

        // The rematch changes the player's colour to Black — the board flips, h1 is now first.
        expect(squareEl('h1')).toBeInTheDocument();
        expect(screen.queryByText(/You resigned/)).not.toBeInTheDocument();
        expect(screen.getByRole('button', {name: /Resign/})).toBeInTheDocument();
    });
});

describe('a connection failure with the server in a game with a bot', () => {
    function stubBotFetch(moveReplies: Array<() => Promise<Response>>) {
        const base = mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
            '/bots/save-game': () => ({game_id: 999, status: 'finished', result: '1-0'}),
        });
        const moveCalls: number[] = [];
        vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
            if (input.toString().includes('/bots/move')) {
                moveCalls.push(Date.now());
                const reply = moveReplies[Math.min(moveCalls.length - 1, moveReplies.length - 1)];
                return reply();
            }
            return base(input);
        }));
        return moveCalls;
    }

    const okMove = () => Promise.resolve({
        ok: true, status: 200, headers: new Headers(),
        json: async () => ({...BOT_MOVE_DEFAULT, uci: 'e2e4', san: 'e4', thinking_time_ms: 10}),
    } as unknown as Response);

    async function startAsBlack() {
        renderChessboard();
        await openBots();
        const startButton = await screen.findByRole('button', {name: /Black/});
        await act(async () => {
            fireEvent.click(startButton);
        });
    }

    it('the bot repeats the request after a network error and a 500 and still moves', async () => {
        const moveCalls = stubBotFetch([
            () => Promise.reject(new TypeError('Failed to fetch')),
            () => Promise.resolve({ok: false, status: 500, headers: new Headers(), json: async () => ({})} as unknown as Response),
            okMove,
        ]);
        await startAsBlack();

        await act(async () => {
            await vi.advanceTimersByTimeAsync(4000);
        });

        expect(moveCalls).toHaveLength(3);
        await waitFor(() => expect(screen.getByText('e4')).toBeInTheDocument());
    });

    it('on a long failure the bot says it is waiting for the connection rather than staying silent', async () => {
        stubBotFetch([() => Promise.reject(new TypeError('Failed to fetch'))]);
        await startAsBlack();

        await act(async () => {
            await vi.advanceTimersByTimeAsync(4000);
        });

        expect(screen.getByText(/No connection to the server/)).toBeInTheDocument();
    });

    it('a permanent error (4xx) is shown, the bot does not repeat the request endlessly', async () => {
        const moveCalls = stubBotFetch([() => Promise.resolve({
            ok: false, status: 400, headers: new Headers(),
            json: async () => ({detail: 'Invalid position'}),
        } as unknown as Response)]);
        await startAsBlack();

        await act(async () => {
            await vi.advanceTimersByTimeAsync(4000);
        });

        expect(moveCalls).toHaveLength(1);
        expect(screen.getByText(/The bot could not make a move: Invalid position/)).toBeInTheDocument();
    });
});

describe('a game with a bot from an arbitrary position', () => {
    const KQ_VS_K = 'k7/7Q/1K6/8/8/8/8/8 w - - 0 57';

    function stubBotApi() {
        const fetchMock = mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
            '/bots/move': () => BOT_MOVE_DEFAULT,
            '/bots/save-game': () => ({game_id: 999, status: 'finished', result: '1-0'}),
        });
        vi.stubGlobal('fetch', fetchMock);
        return fetchMock;
    }

    async function loadFen(fen: string) {
        fireEvent.change(await screen.findByLabelText('Position in FEN'), {target: {value: fen}});
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Set up/}));
        });
    }

    it('a position from FEN is put on the free board, an incorrect one is rejected', async () => {
        stubBotApi();
        renderChessboard();

        await loadFen('not a fen at all');
        expect(screen.getByRole('alert')).toHaveTextContent('Invalid position');

        await loadFen(KQ_VS_K);
        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
        expect(squareEl('h7').querySelector('img')?.getAttribute('alt')).toBe('wq');
        expect(squareEl('e2').querySelector('img')).toBeNull();
        // Reset returns the ordinary setup even without moves made.
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Reset board/}));
        });
        expect(squareEl('e2').querySelector('img')?.getAttribute('alt')).toBe('wp');
    });

    it('a game with a bot starts from the position on the board and is saved together with it', async () => {
        const fetchMock = stubBotApi();
        renderChessboard();
        await openBots();
        await loadFen(KQ_VS_K);

        expect(screen.getByLabelText('Start from the position on the board')).toBeChecked();
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /White/}));
        });
        expect(squareEl('h7').querySelector('img')?.getAttribute('alt')).toBe('wq');

        // Qa7# — mate; the game goes to the server with the start position.
        clickSquare('h7');
        clickSquare('a7');

        await waitFor(() => {
            expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/bots/save-game'))).toBe(true);
        });
        const saveCall = (fetchMock.mock.calls as unknown as [string, RequestInit][]).find(([url]) => String(url).includes('/bots/save-game'))!;
        const body = JSON.parse((saveCall as unknown as [string, RequestInit])[1].body as string);
        expect(body).toMatchObject({start_fen: KQ_VS_K, moves_uci: ['h7a7'], result: '1-0'});
        // The log numbers the move by the position: the 57th, not the first.
        expect(screen.getByText('57.')).toBeInTheDocument();
    });

    it('without the checkbox the game starts from the ordinary setup', async () => {
        const fetchMock = stubBotApi();
        renderChessboard();
        await openBots();
        await loadFen(KQ_VS_K);
        fireEvent.click(screen.getByLabelText('Start from the position on the board'));

        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /White/}));
        });

        expect(squareEl('e2').querySelector('img')?.getAttribute('alt')).toBe('wp');
        expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/bots/save-game'))).toBe(false);
    });

    it('odds: a game with a bot starts without the opponent\'s knight (task 21.1)', async () => {
        stubBotApi();
        renderChessboard();
        await openBots();
        await screen.findByRole('button', {name: /White/});
        fireEvent.change(screen.getByTestId('odds-kind'), {target: {value: 'knight'}});
        expect(screen.getByTestId('odds-giver')).toHaveValue('opponent');
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /White/}));
        });
        // I play White, the opponent gives the odds — Black has no b8 knight, White has everything in place.
        expect(squareEl('b8').querySelector('img')).toBeNull();
        expect(squareEl('b1').querySelector('img')?.getAttribute('alt')).toBe('wn');
    });

    it('on the ordinary setup there is no "from a position" choice', async () => {
        stubBotApi();
        renderChessboard();
        await openBots();
        await screen.findByRole('button', {name: /White/});
        expect(screen.queryByLabelText('Start from the position on the board')).not.toBeInTheDocument();
    });
});

describe('opponent workshop', () => {
    it('a game with an archetype: moves through /custom-move with the config, saving as bot_id custom', async () => {
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        const fetchMock = mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
            '/bots/personalities': () => [],
            '/bots/catalog': () => ({
                calibration: null, historical: [],
                archetypes: [{
                    id: 'rusher', config: {...DEFAULT_CONFIG, target_elo: 700},
                    declared_rating: 700, rating: 700, measured: false, games: 0, ci95: null,
                }],
            }),
            '/bots/custom-move': () => ({
                ...BOT_MOVE_DEFAULT, uci: 'e2e4', san: 'e4', comment: {key: 'personality.develop', params: {}},
            }),
            '/bots/save-game': () => ({game_id: 1000, status: 'finished', result: '1-0'}),
        });
        vi.stubGlobal('fetch', fetchMock);
        renderChessboard();
        await openBots();

        fireEvent.click(await screen.findByRole('tab', {name: 'Workshop'}));
        fireEvent.click(await screen.findByRole('button', {name: /Rusher/}));
        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Black/}));
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(200);
        });

        const moveCall = (fetchMock.mock.calls as unknown as [string, RequestInit][]).find(([url]) => String(url).includes('/bots/custom-move'));
        const moveBody = JSON.parse(String(moveCall?.[1].body));
        expect(moveBody.config.target_elo).toBe(700);
        expect(moveBody.bot_id).toBeUndefined();
        await waitFor(() => expect(screen.getByText('e4')).toBeInTheDocument());
        expect(screen.getAllByText('Rusher').length).toBeGreaterThan(0);
        // The bot remark came by key and is shown from the catalogue.
        expect(screen.getByText('Developing the pieces — every tempo counts.')).toBeInTheDocument();

        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Resign/}));
        });
        const saveCall = (fetchMock.mock.calls as unknown as [string, RequestInit][]).find(([url]) => String(url).includes('/bots/save-game'));
        const saveBody = JSON.parse(String(saveCall?.[1].body));
        expect(saveBody).toMatchObject({bot_id: 'custom', personality_name: 'archetype:rusher', player_color: 'black'});
    });
});

describe('club ladder', () => {
    it('a ladder game: an opponent from the server, no take back, the result in the status', async () => {
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        const ladderState = {
            rating: 1000, games: 0, step: 0, total: 2, active_opponent: null,
            rungs: [
                {key: 'morphy', kind: 'historical', id: 'morphy', rating: 2050, measured: true, status: 'current'},
                {key: 'paulsen', kind: 'historical', id: 'paulsen', rating: 2100, measured: false, status: 'locked'},
            ],
        };
        const fetchMock = mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
            '/bots/catalog': () => ({calibration: null, historical: [], archetypes: []}),
            '/bots/ladder/start': () => ({
                opponent: {key: 'morphy', kind: 'historical', id: 'morphy', rating: 2050, bot_id: 'morphy', config: null},
                color: 'white', step: 0, forfeited: null,
            }),
            '/bots/ladder': () => ladderState,
            '/bots/move': () => BOT_MOVE_DEFAULT,
            '/bots/save-game': () => ({
                game_id: 1001, status: 'finished', result: '0-1',
                ladder: {counted: true, reason: null, delta: -6, rating: 994, step: 0, promoted: false, opponent: 'Morphy'},
            }),
        });
        vi.stubGlobal('fetch', fetchMock);
        renderChessboard();
        await openBots();

        fireEvent.click(await screen.findByRole('tab', {name: 'Ladder'}));
        const white = await screen.findByRole('button', {name: /White/});
        await act(async () => {
            fireEvent.click(white);
        });

        clickSquare('e2');
        clickSquare('e4');
        await act(async () => {
            await vi.advanceTimersByTimeAsync(200);
        });
        expect(screen.getByRole('button', {name: /Take back/})).toBeDisabled();

        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Resign/}));
        });
        const saveCall = (fetchMock.mock.calls as unknown as [string, RequestInit][])
            .find(([url]) => String(url).includes('/bots/save-game'));
        expect(JSON.parse(String(saveCall?.[1].body))).toMatchObject({bot_id: 'morphy', ladder: true, player_color: 'white'});
        expect(await screen.findByText('Ladder: rating 994 (-6).')).toBeInTheDocument();
    });
});

describe('keyboard', () => {
    it('arrows page through the moves, the handler is registered once', async () => {
        const addListener = vi.spyOn(window, 'addEventListener');
        vi.stubGlobal('fetch', mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
        }));
        renderChessboard();
        await screen.findByTestId('new-game-open');

        // Free board: a move right after a move — the arrow must see the already updated history.
        clickSquare('e2');
        clickSquare('e4');
        fireEvent.keyDown(window, {key: 'ArrowLeft'});
        await waitFor(() => expect(squareEl('e2').querySelector('img')?.getAttribute('alt')).toBe('wp'));
        expect(squareEl('e4').querySelector('img')).toBeNull();

        fireEvent.keyDown(window, {key: 'ArrowDown'});
        await waitFor(() => expect(squareEl('e4').querySelector('img')?.getAttribute('alt')).toBe('wp'));

        expect(addListener.mock.calls.filter(([type]) => type === 'keydown')).toHaveLength(1);
        addListener.mockRestore();
    });
});

describe('play with the mentor', () => {
    const BLUNDER = {
        available: true, cp_loss: 320, classification: 'Blunder', symbol: '??', eval_before: 30, eval_after: -290,
        best_move_uci: 'd2d4', reply_uci: 'd8h4', missed_tactic: false,
        coach: {comment: [{key: 'coach.verdict.blunder.v1', params: {move: 'f3'}}],
            arrows: [{from: 'd8', to: 'h4', kind: 'threat'}], highlights: []},
    };

    async function startCoachedGame(check: object) {
        localStorage.setItem('regence_coach_enabled', '1');
        const calls: string[] = [];
        vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
            const url = String(input);
            calls.push(url);
            const body = (() => {
                if (url.includes('/analysis/check-move')) return check;
                if (url.includes('/bots/move')) return BOT_MOVE_DEFAULT;
                if (url.includes('/bots/save-game')) return {game_id: 1};
                if (url.includes('/profile/me')) return {id: 1, username: 'TestPlayer', blitz_rating: 1500};
                if (url.includes('/profile/games/my-active')) return {active: false};
                return [];
            })();
            return {ok: true, status: 200, json: async () => body} as Response;
        }));
        renderChessboard();
        await openBots();
        const startButton = await screen.findByRole('button', {name: /White/});
        await act(async () => {
            fireEvent.click(startButton);
        });
        return {calls};
    }

    it('a blunder: the game does not wait for advice, "Why?" draws an arrow, "Take the move back" returns the position before the move', async () => {
        const {calls} = await startCoachedGame(BLUNDER);
        clickSquare('f2');
        clickSquare('f3');

        expect(await screen.findByTestId('coach-warning')).toBeInTheDocument();
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1500);
        });
        // Owner decision 18.11: the mentor advises but does not stop — the bot replies without waiting for the player.
        expect(calls.some((url) => url.includes('/bots/move'))).toBe(true);

        fireEvent.click(screen.getByTestId('coach-why'));
        expect(screen.getByTestId('coach-arrow-threat')).toBeInTheDocument();

        // The warning cannot be skipped: the "Mentor" tab opened by itself (tabs on the right, owner plan 18.11).
        expect(screen.getByTestId('side-tab-coach')).toHaveAttribute('aria-selected', 'true');
        expect(screen.getByTestId('side-panel-coach')).toHaveClass('contents');
        expect(screen.getByTestId('side-panel-moves')).toHaveClass('hidden');

        fireEvent.click(screen.getByTestId('coach-takeback'));
        expect(screen.queryByTestId('coach-warning')).toBeNull();
        expect(screen.queryByText('f3')).toBeNull();
        // Answered — the column returned to the moves.
        await waitFor(() => expect(screen.getByTestId('side-tab-moves')).toHaveAttribute('aria-selected', 'true'));
    });

    it('tabs on the right: moves, mentor and x-ray; a hidden tab stays in the markup', async () => {
        renderChessboard();
        const tabs = await screen.findAllByRole('tab', {name: /Moves|Coach|X-ray/});
        expect(tabs.map((tab) => tab.getAttribute('data-testid'))).toEqual(['side-tab-moves', 'side-tab-coach', 'side-tab-xray']);
        expect(screen.queryByTestId('side-tab-chat')).toBeNull();  // chat — only in a game with a person
        expect(screen.getByTestId('side-panel-moves')).toHaveClass('contents');
        fireEvent.click(screen.getByTestId('side-tab-xray'));
        expect(screen.getByTestId('side-panel-xray')).toHaveClass('contents');
        expect(screen.getByTestId('side-panel-moves')).toHaveClass('hidden');
        expect(screen.getByTestId('side-panel-coach')).toBeInTheDocument();
    });

    it('a move is left — the bot replies, the game is saved as a training one', async () => {
        const {calls} = await startCoachedGame(BLUNDER);
        clickSquare('f2');
        clickSquare('f3');
        fireEvent.click(await screen.findByTestId('coach-keep'));
        await waitFor(() => expect(calls.some((url) => url.includes('/bots/move'))).toBe(true));
        expect(screen.getByTestId('coach-assisted')).toBeInTheDocument();
    });

    it('a good move — no warning, the bot replies at once', async () => {
        const {calls} = await startCoachedGame({...BLUNDER, cp_loss: 0, classification: 'Best', eval_after: 30});
        clickSquare('e2');
        clickSquare('e4');
        await waitFor(() => expect(calls.some((url) => url.includes('/bots/move'))).toBe(true));
        expect(screen.queryByTestId('coach-warning')).toBeNull();
    });
});

describe('game summary', () => {
    it('after a mate: the summary with the game type and a recommendation, "Play" starts a new game', async () => {
        const replies = [
            {...BOT_MOVE_DEFAULT, uci: 'e7e5', san: 'e5'},
            {...BOT_MOVE_DEFAULT, uci: 'd8h4', san: 'Qh4#'},
            {...BOT_MOVE_DEFAULT, uci: 'e7e5', san: 'e5'},
        ];
        const calls: string[] = [];
        vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
            const url = String(input);
            calls.push(url);
            const body = (() => {
                if (url.includes('/bots/move')) return replies.shift();
                if (url.includes('/bots/save-game')) return {game_id: 77, status: 'finished', result: '0-1'};
                if (url.includes('/analysis/game/77')) return {
                    white: {accuracy: 20}, black: {accuracy: 100},
                    moves: [
                        {ply: 1, move_number: 1, color: 'white', san: 'f3'},
                        {ply: 2, move_number: 1, color: 'black', san: 'e5'},
                        {ply: 3, move_number: 2, color: 'white', san: 'g4'},
                        {ply: 4, move_number: 2, color: 'black', san: 'Qh4#'},
                    ],
                    summary: {kind: 'decisive_blunder', turning_point_ply: 3, lead_changes: 0, equal_share: 0.5,
                              white: {best_ply: null, worst_ply: 3}, black: {best_ply: 4, worst_ply: null}},
                };
                if (url.includes('/bots/catalog')) return {calibration: null, historical: [], archetypes: []};
                if (url.includes('/profile/me')) return {id: 1, username: 'TestPlayer', blitz_rating: 1500};
                if (url.includes('/profile/games/my-active')) return {active: false};
                return [];
            })();
            return {ok: true, status: 200, json: async () => body} as Response;
        }));
        renderChessboard();
        await openBots();
        await act(async () => {
            fireEvent.click(await screen.findByRole('button', {name: /White/}));
        });
        clickSquare('f2');
        clickSquare('f3');
        await waitFor(() => expect(screen.getByText('e5')).toBeInTheDocument());
        clickSquare('g2');
        clickSquare('g4');

        const summary = await screen.findByTestId('game-summary');
        await waitFor(() => expect(summary.textContent).toContain('Decided by one mistake'));
        expect(summary.textContent).toContain('Turning point: 2. g4');
        // The end-of-game buttons are above the summary, not under it beyond the column edge (owner feedback 18.11).
        const review = screen.getByRole('button', {name: /Game review/});
        expect(review.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
        // Lost to Philidor (1850 by default) — there is no weaker next opponent among the historical bots,
        // so the nearest by strength.
        expect(screen.getByTestId('summary-recommendation').textContent).toMatch(/\(\d{4}\)/);

        await act(async () => {
            fireEvent.click(screen.getByTestId('summary-play'));
        });
        expect(screen.queryByTestId('game-summary')).toBeNull();
        expect(calls.filter((url) => url.includes('/bots/save-game'))).toHaveLength(1);
    });
});

describe('board x-ray', () => {
    it('on a free board it is available and draws square control', async () => {
        vi.stubGlobal('fetch', mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
        }));
        renderChessboard();
        fireEvent.click(await screen.findByTestId('xray-mode-control'));
        expect(screen.getByTestId('xray-control-f3').textContent).toBe('+3');
    });

    it('in a game with a bot — only with the mentor on', async () => {
        await startBotGame('white');
        expect(screen.queryByTestId('xray-panel')).toBeNull();
        fireEvent.click(screen.getByTestId('coach-toggle'));
        expect(screen.getByTestId('xray-panel')).toBeInTheDocument();
    });
});

describe('the first game after registration (task 17.8)', () => {
    it('an archetype by the starting rating, the player is White', async () => {
        const archetypeOf = (id: string, rating: number) => ({
            id, config: {...DEFAULT_CONFIG, target_elo: rating},
            declared_rating: rating, rating, measured: true, games: 80, ci95: 100,
        });
        const fetchMock = mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 600}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
            '/bots/personalities': () => [],
            '/bots/catalog': () => ({
                calibration: null, historical: [], archetypes: [archetypeOf('quiet', 848), archetypeOf('rusher', 792)],
            }),
            '/bots/custom-move': () => ({...BOT_MOVE_DEFAULT, uci: 'e7e5', san: 'e5'}),
        });
        vi.stubGlobal('fetch', fetchMock);
        render(
            <MemoryRouter initialEntries={[{pathname: '/', state: {firstGame: {rating: 600}}}]}>
                <Chessboard/>
            </MemoryRouter>,
        );

        await waitFor(() => expect(screen.getAllByText('Rusher').length).toBeGreaterThan(0));
        clickSquare('e2');
        clickSquare('e4');
        await act(async () => {
            await vi.advanceTimersByTimeAsync(200);
        });
        const moveCall = (fetchMock.mock.calls as unknown as [string, RequestInit][])
            .find(([url]) => String(url).includes('/bots/custom-move'));
        expect(JSON.parse(String(moveCall?.[1].body)).config.target_elo).toBe(792);
    });
});

describe('tournament game', () => {
    it('starts with the tournament control, without take back, the result goes to the tournament', async () => {
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        const fetchMock = mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
            '/bots/catalog': () => ({calibration: null, historical: [], archetypes: []}),
            '/bots/move': () => BOT_MOVE_DEFAULT,
            '/bots/save-game': () => ({game_id: 1002, status: 'finished', result: '0-1', tournament_id: 7,
                rating_before: 1500, rating_after: 1488, rating_delta: -12}),
            '/tournaments/7': () => ({
                id: 7, format: 'round_robin', size: 2, status: 'active', base_time_ms: 150000, increment_ms: 1000,
                current_round: 1, created_at: '2026-11-17T10:00:00Z', finished_at: null, my_seat: 1, withdrawn: false,
                event_key: null,
                players: [{seat: 1, kind: 'user', user_id: 1, bot_key: null, personality_name: null, rating: 1500, place: null,
                    eliminated_round: null, config: null},
                {seat: 2, kind: 'bot', user_id: null, bot_key: 'morphy', personality_name: null, rating: 2100, place: null,
                    eliminated_round: null, config: null}],
                games: [{id: 31, round: 1, board: 1, stage: 'main', white_seat: 1, black_seat: 2, base_time_ms: 150000,
                    increment_ms: 1000, result: null, game_id: null}],
                standings: [{seat: 1, points: 0, head_to_head: 0, sonneborn_berger: 0, place: 1},
                    {seat: 2, points: 0, head_to_head: 0, sonneborn_berger: 0, place: 2}],
            }),
        });
        vi.stubGlobal('fetch', fetchMock);
        const tournamentGame = {
            tournamentId: 7, gameId: 31, color: 'white', baseTimeMs: 150000, incrementMs: 1000, botId: 'morphy', custom: null,
        };
        render(
            <MemoryRouter initialEntries={[{pathname: '/', state: {tournamentGame}}]}>
                <Chessboard/>
            </MemoryRouter>,
        );

        // The tournament bar above the game: round and opponent; the table over the board, without leaving the page.
        expect(await screen.findByTestId('tournament-bar')).toHaveTextContent('vs');
        fireEvent.click(screen.getByTestId('tournament-bar-table'));
        expect(screen.getByTestId('tournament-standings-overlay')).toBeInTheDocument();
        expect(screen.queryByTestId('back-to-tournament')).toBeNull();
        expect(screen.getAllByText('02:30').length).toBeGreaterThan(0);  // 2.5 minutes — the shortened control of the tiebreak

        clickSquare('e2');
        clickSquare('e4');
        await act(async () => {
            await vi.advanceTimersByTimeAsync(200);
        });
        expect(screen.getByRole('button', {name: /Take back/})).toBeDisabled();

        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Resign/}));
        });
        const saveCall = (fetchMock.mock.calls as unknown as [string, RequestInit][])
            .find(([url]) => String(url).includes('/bots/save-game'));
        expect(JSON.parse(String(saveCall?.[1].body))).toMatchObject({
            bot_id: 'morphy', player_color: 'white', tournament_game_id: 31, base_time_ms: 150000, increment_ms: 1000,
        });
        // All tournaments are rated (15.4): the player sees the rating change.
        expect(await screen.findByText(/Rating: 1500 → 1488 \(-12\)/)).toBeInTheDocument();
        // After the game — the way back to the tournament; there is no rematch in a tournament.
        expect(await screen.findByTestId('back-to-tournament')).toHaveAttribute('href', '/tournaments/7');
        expect(screen.queryByRole('button', {name: /Rematch/})).toBeNull();
    });
});

describe('a game with a past master from the catalogue (task 28.5)', () => {
    it('plays with the master\'s character, his name on the board, the name from the PGN to the archive', async () => {
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        const fetchMock = mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
            '/bots/personalities': () => [],
            '/bots/catalog': () => ({calibration: null, historical: [], archetypes: []}),
            '/bots/custom-move': () => ({...BOT_MOVE_DEFAULT, uci: 'e7e5', san: 'e5'}),
            '/bots/save-game': () => ({game_id: 1003, status: 'finished', result: '0-1', tournament_id: null}),
        });
        vi.stubGlobal('fetch', fetchMock);
        const guestGame = {
            name: 'Paul Keres', savedName: 'Keres, Paul', config: {...DEFAULT_CONFIG, target_elo: 2400}, color: 'white',
        };
        render(
            <MemoryRouter initialEntries={[{pathname: '/', state: {guestGame}}]}>
                <Chessboard/>
            </MemoryRouter>,
        );

        await waitFor(() => expect(screen.getAllByText('Paul Keres').length).toBeGreaterThan(0));
        clickSquare('e2');
        clickSquare('e4');
        await act(async () => {
            await vi.advanceTimersByTimeAsync(200);
        });
        const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
        const moveCall = calls.find(([url]) => String(url).includes('/bots/custom-move'));
        expect(JSON.parse(String(moveCall?.[1].body)).config.target_elo).toBe(2400);

        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Resign/}));
        });
        const saveCall = calls.find(([url]) => String(url).includes('/bots/save-game'));
        // The server recognises the master by the name from the PGN; the game is outside a tournament.
        const saved = JSON.parse(String(saveCall?.[1].body));
        expect(saved).toMatchObject({bot_id: 'custom', personality_name: 'Keres, Paul', player_color: 'white'});
        expect(saved.tournament_game_id).toBeUndefined();
    });
});

describe('right-button marks (task B.1)', () => {
    function rightDrag(from: string, to: string, init: Record<string, unknown> = {}) {
        document.elementsFromPoint = () => [squareEl(from)];
        fireEvent.pointerDown(squareEl(from), {pointerType: 'mouse', button: 2});
        document.elementsFromPoint = () => [squareEl(to)];
        fireEvent.pointerUp(squareEl(to), {pointerType: 'mouse', button: 2, ...init});
    }

    it('an arrow in a live game, a move clears it; with a piece selected the right button clears the selection and draws', async () => {
        await startBotGame('white');
        rightDrag('g1', 'f3', {altKey: true});
        expect(screen.getByTestId('note-arrow-g1-f3').getAttribute('data-color')).toBe('blue');

        clickSquare('e2');
        rightDrag('d2', 'd4');
        fireEvent.contextMenu(squareEl('d4'));  // the browser sends it after the right button
        expect(screen.getByTestId('note-arrow-d2-d4')).toBeInTheDocument();

        clickSquare('e4');  // the selection is cleared — there is no move e2-e4, the marks are in place
        expect(screen.getByTestId('note-arrow-d2-d4')).toBeInTheDocument();

        clickSquare('e2');
        clickSquare('e4');
        await waitFor(() => expect(screen.queryByTestId('board-annotations')).toBeNull());
    });

    it('while a premove stands, the right button cancels it and draws no arrow', async () => {
        await startBotGame('black');
        clickSquare('e7');
        clickSquare('e5');  // White has not moved yet — this is a premove
        rightDrag('d7', 'd5');
        expect(screen.queryByTestId('note-arrow-d7-d5')).toBeNull();
    });
});

describe('draw with a bot (task 21.4)', () => {
    async function gameWithDrawAnswer(accepted: boolean) {
        const fetchMock = mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
            '/bots/move': () => BOT_MOVE_DEFAULT,
            '/bots/draw-offer': () => ({accepted, comment: {key: accepted ? 'personality.drawAccepted' : 'personality.drawDeclined', params: {}}}),
            '/bots/save-game': () => ({game_id: 999, status: 'finished', result: '1/2-1/2'}),
        });
        vi.stubGlobal('fetch', fetchMock);
        renderChessboard();
        await openBots();
        await act(async () => {
            fireEvent.click(await screen.findByRole('button', {name: /White/}));
        });
        clickSquare('e2');
        clickSquare('e4');
        await screen.findByText('e5');
        await act(async () => {
            fireEvent.click(screen.getByTestId('bot-offer-draw'));
        });
        return fetchMock;
    }

    const call = (fetchMock: ReturnType<typeof mockFetchRouter>, part: string) =>
        (fetchMock.mock.calls as unknown as [string, RequestInit][]).find(([url]) => String(url).includes(part));

    it('the bot accepted — a draw by agreement is saved', async () => {
        const fetchMock = await gameWithDrawAnswer(true);
        expect(await screen.findByText(/accepted the draw/)).toBeInTheDocument();
        const offer = JSON.parse(String(call(fetchMock, '/bots/draw-offer')![1].body));
        expect(offer).toMatchObject({bot_id: 'philidor', bot_color: 'black'});
        await waitFor(() => expect(call(fetchMock, '/bots/save-game')).toBeTruthy());
        expect(JSON.parse(String(call(fetchMock, '/bots/save-game')![1].body))).toMatchObject({termination: 'agreement', result: '1/2-1/2'});
    });

    it('the bot declined — the game goes on', async () => {
        const fetchMock = await gameWithDrawAnswer(false);
        expect(await screen.findByText(/declined the draw/)).toBeInTheDocument();
        expect(call(fetchMock, '/bots/save-game')).toBeUndefined();
    });
});

describe('board accessibility (task 26.3)', () => {
    it('a move from the keyboard: Tab to the board, arrows, Enter; the move and the bot reply are announced in words', async () => {
        await startBotGame('white');
        const start = squareEl('a8');
        expect(start).toHaveAttribute('tabindex', '0');           // one square enters the Tab order
        expect(squareEl('e2')).toHaveAttribute('tabindex', '-1');
        expect(squareEl('e2')).toHaveAttribute('aria-label', 'e2, white pawn');
        start.focus();
        const press = (key: string) => fireEvent.keyDown(document.activeElement as HTMLElement, {key});
        for (let i = 0; i < 6; i++) press('ArrowDown');
        for (let i = 0; i < 4; i++) press('ArrowRight');
        expect(document.activeElement).toBe(squareEl('e2'));
        press('Enter');
        expect(squareEl('e2')).toHaveAttribute('aria-pressed', 'true');
        press('ArrowUp');
        press('ArrowUp');
        await act(async () => {
            press(' ');
        });
        expect(squareEl('e4')).toHaveAttribute('aria-label', 'e4, white pawn');
        await waitFor(() => expect(screen.getByTestId('move-announcer')).toHaveTextContent('Black: pawn e7 to e5'),
            {timeout: 5000});
    });

    it('position in words by a button', async () => {
        await startBotGame('white');
        fireEvent.click(screen.getByTestId('describe-position'));
        expect(screen.getByTestId('position-words')).toHaveTextContent(/^White: king on e1; queen on d1;/);
    });
});


describe('continuing a game with a bot after a reload', () => {
    it('the snapshot restores the game position, not the initial setup', async () => {
        vi.stubGlobal('fetch', mockFetchRouter({
            '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
            '/profile/matchmaking/queue': () => [],
            '/profile/games/live': () => [],
            '/profile/games/my-active': () => ({active: false}),
            '/bots/move': () => new Promise(() => {}),
            '/bots/save-game': () => ({game_id: 1, status: 'finished', result: '1-0'}),
        }));
        saveBotGameSnapshot({
            username: 'TestPlayer', botId: 'philidor', custom: null, color: 'white', pgn: '1. e4 e5 2. Nf3',
            whiteTimeMs: 200000, blackTimeMs: 250000, baseMinutes: 5, incrementSeconds: 0, odds: null,
            ladder: false, tournamentGameId: null, tournamentId: null,
        });
        renderChessboard();
        // A knight on f3 and a pawn on e5 — the position from the snapshot, not the initial setup.
        await waitFor(() => expect(squareEl('f3').querySelector('img,svg,[data-piece]')).not.toBeNull());
        expect(squareEl('e2').querySelector('img,svg,[data-piece]')).toBeNull();
    });
});
