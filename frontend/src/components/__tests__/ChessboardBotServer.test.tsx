// --- FILE: frontend/src/components/__tests__/ChessboardBotServer.test.tsx ---
// Server answers in a game with a bot (useBotGame.ts through Chessboard.tsx): a game result that the server judged differently,
// a refusal and a failure to save the game, a refusal and a failure of a draw offer; the pure functions ladderOutcomeMessage and
// botCommentMessage (a ladder result message by code, a bot remark by catalogue key). The server is a fetch stub
// with response codes, the bot answers with prepared moves, time is fake timers.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import Chessboard from '../Chessboard';
import {botCommentMessage, ladderOutcomeMessage} from '../chessboard/hooks/useBotGame';
import {resetBotCatalogCache} from '../../services/botCatalog';
import {setToken} from '../../services/authToken';
import {openBots} from '../../test/newGame';
import {playMove} from '../../test/boardMoves';

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

const FOOLS_MATE_REPLIES = [{uci: 'f7f6', san: 'f6'}, {uci: 'g7g5', san: 'g5'}];

interface ServerStub {
    saveGame?: () => Response | Promise<Response>;
    drawOffer?: () => Response | Promise<Response>;
}

const json = (body: unknown, status = 200) =>
    ({ok: status < 400, status, json: async () => body, text: async () => JSON.stringify(body)}) as Response;

/** A game as White against the bot; the answers of /bots/save-game and /bots/draw-offer are set by the test. */
async function startBotGame(replies: Array<{ uci: string; san: string }>, server: ServerStub = {}) {
    let call = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes('/bots/save-game')) return server.saveGame ? server.saveGame() : json({game_id: 999, status: 'finished'});
        if (url.includes('/bots/draw-offer')) return server.drawOffer ? server.drawOffer() : json({accepted: false, comment: null});
        if (url.includes('/bots/move')) {
            const reply = replies[Math.min(call, replies.length - 1)];
            call += 1;
            return json({...reply, fen_after: '', source: 'book', comment: '', thinking_time_ms: 10});
        }
        if (url.includes('/profile/me')) return json({id: 1, username: 'TestPlayer', blitz_rating: 1500});
        if (url.includes('/profile/matchmaking/queue') || url.includes('/profile/games/live')) return json([]);
        if (url.includes('/profile/games/my-active')) return json({active: false});
        return json({}, 404);
    }));
    render(
        <MemoryRouter initialEntries={['/']}>
            <Chessboard/>
        </MemoryRouter>,
    );
    await openBots();
    await act(async () => {
        fireEvent.click(await screen.findByRole('button', {name: /White/}));
    });
}

async function botReplies() {
    await act(async () => {
        await vi.advanceTimersByTimeAsync(500);
    });
}

async function playFoolsMate() {
    await playMove('e2', 'e4');
    await botReplies();
    await playMove('d2', 'd4');
    await botReplies();
    await playMove('d1', 'h5');
}

beforeEach(() => {
    resetBotCatalogCache();
    setToken('test-token');
    vi.useFakeTimers({shouldAdvanceTime: true});
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    localStorage.clear();
});

describe('game result by the server answer', () => {
    it('if the server judged differently, its result stays on the screen', async () => {
        await startBotGame(FOOLS_MATE_REPLIES, {saveGame: () => json({game_id: 999, status: 'finished', result: '1/2-1/2'})});
        await playFoolsMate();
        await waitFor(() => expect(screen.getByText('Result under FIDE rules: 1/2-1/2')).toBeInTheDocument());
    });

    it('a failure to save the game is written to the log and does not break the board', async () => {
        const errors = vi.spyOn(console, 'error').mockImplementation(() => undefined);
        await startBotGame(FOOLS_MATE_REPLIES, {saveGame: () => Promise.reject(new Error('offline'))});
        await playFoolsMate();
        await waitFor(() => expect(errors).toHaveBeenCalledWith('Failed to save the bot game:', expect.any(Error)));
        expect(screen.getByText(/The game against .* is over/)).toBeInTheDocument();
    });
});

describe('a draw offer to the bot', () => {
    async function offerDraw() {
        await playMove('e2', 'e4');
        await botReplies();
        await playMove('d2', 'd4');
        await botReplies();
        await act(async () => {
            fireEvent.click(screen.getByTestId('bot-offer-draw'));
        });
    }

    it('a server refusal — a message, the game continues', async () => {
        await startBotGame(FOOLS_MATE_REPLIES, {drawOffer: () => json({}, 500)});
        await offerDraw();
        await waitFor(() => expect(screen.getByText(/could not answer the draw offer/)).toBeInTheDocument());
        expect(screen.getByTestId('bot-offer-draw')).toBeInTheDocument();
    });

    it('a network failure — the same message', async () => {
        await startBotGame(FOOLS_MATE_REPLIES, {drawOffer: () => Promise.reject(new Error('offline'))});
        await offerDraw();
        await waitFor(() => expect(screen.getByText(/could not answer the draw offer/)).toBeInTheDocument());
    });
});

describe('ladderOutcomeMessage and botCommentMessage', () => {
    const paramsOf = (m: ReturnType<typeof ladderOutcomeMessage>) => (m as {params?: Record<string, unknown>}).params;
    const base = {counted: true, reason: null, delta: 12, rating: 1512, step: 3, promoted: false, opponent: 'x'};

    it('not counted: the reason is from the catalogue by code, an unknown one as is, an empty one — empty', () => {
        // A known code is not a string but a reference to a catalogue message (the client assembles the text in the player\'s language).
        expect(typeof paramsOf(ladderOutcomeMessage({...base, counted: false, reason: 'takeback'}))?.reason).toBe('object');
        expect(paramsOf(ladderOutcomeMessage({...base, counted: false, reason: 'new_reason'}))).toEqual({reason: 'new_reason'});
        expect(paramsOf(ladderOutcomeMessage({...base, counted: false, reason: null}))).toEqual({reason: ''});
        expect(ladderOutcomeMessage({...base, counted: false, reason: 'takeback'}).key).toBe('ladder.notCounted');
    });

    it('counted: the sign of the change and the promotion', () => {
        expect(ladderOutcomeMessage(base)).toMatchObject({key: 'ladder.result', params: {rating: 1512, delta: '+12'}});
        expect(ladderOutcomeMessage({...base, delta: -8, promoted: true}))
            .toMatchObject({key: 'ladder.resultPromoted', params: {delta: '-8'}});
    });

    it('bot remark: an unknown key and a non-object — no remark', () => {
        expect(botCommentMessage(null)).toBeNull();
        expect(botCommentMessage('text')).toBeNull();
        expect(botCommentMessage({key: 'no_such_key_at_all', params: {}})).toBeNull();
        expect(botCommentMessage({key: 7, params: {}})).toBeNull();
    });
});
