// --- FILE: frontend/src/components/__tests__/ChessboardBotServer.test.tsx ---
// Ответы сервера в партии с ботом (useBotGame.ts через Chessboard.tsx): итог партии, который сервер рассудил иначе,
// отказ и сбой сохранения партии, отказ и сбой предложения ничьей; чистые функции ladderOutcomeMessage и
// botCommentMessage (сообщение об итоге лестницы по коду, реплика бота по ключу каталога). Сервер — стаб fetch
// с кодами ответов, бот отвечает заготовленными ходами, время — фальшивые таймеры.

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

/** Партия белыми против бота; ответы /bots/save-game и /bots/draw-offer задаёт тест. */
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
        fireEvent.click(await screen.findByRole('button', {name: /Белыми/}));
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

describe('итог партии с ботом по ответу сервера', () => {
    it('если сервер рассудил иначе, на экране остаётся его итог', async () => {
        await startBotGame(FOOLS_MATE_REPLIES, {saveGame: () => json({game_id: 999, status: 'finished', result: '1/2-1/2'})});
        await playFoolsMate();
        await waitFor(() => expect(screen.getByText('Итог по правилам ФИДЕ: 1/2-1/2')).toBeInTheDocument());
    });

    it('сбой сохранения партии пишется в журнал и не ломает доску', async () => {
        const errors = vi.spyOn(console, 'error').mockImplementation(() => undefined);
        await startBotGame(FOOLS_MATE_REPLIES, {saveGame: () => Promise.reject(new Error('offline'))});
        await playFoolsMate();
        await waitFor(() => expect(errors).toHaveBeenCalledWith('Failed to save the bot game:', expect.any(Error)));
        expect(screen.getByText(/Партия против .* окончена/)).toBeInTheDocument();
    });
});

describe('предложение ничьей боту', () => {
    async function offerDraw() {
        await playMove('e2', 'e4');
        await botReplies();
        await playMove('d2', 'd4');
        await botReplies();
        await act(async () => {
            fireEvent.click(screen.getByTestId('bot-offer-draw'));
        });
    }

    it('отказ сервера — сообщение, партия продолжается', async () => {
        await startBotGame(FOOLS_MATE_REPLIES, {drawOffer: () => json({}, 500)});
        await offerDraw();
        await waitFor(() => expect(screen.getByText(/не смог ответить на предложение ничьей/)).toBeInTheDocument());
        expect(screen.getByTestId('bot-offer-draw')).toBeInTheDocument();
    });

    it('сетевой сбой — то же сообщение', async () => {
        await startBotGame(FOOLS_MATE_REPLIES, {drawOffer: () => Promise.reject(new Error('offline'))});
        await offerDraw();
        await waitFor(() => expect(screen.getByText(/не смог ответить на предложение ничьей/)).toBeInTheDocument());
    });
});

describe('ladderOutcomeMessage и botCommentMessage', () => {
    const paramsOf = (m: ReturnType<typeof ladderOutcomeMessage>) => (m as {params?: Record<string, unknown>}).params;
    const base = {counted: true, reason: null, delta: 12, rating: 1512, step: 3, promoted: false, opponent: 'x'};

    it('не засчитана: причина — из каталога по коду, незнакомая — как есть, пустая — пусто', () => {
        // Известный код — не строка, а ссылка на сообщение каталога (текст соберёт клиент на языке игрока).
        expect(typeof paramsOf(ladderOutcomeMessage({...base, counted: false, reason: 'takeback'}))?.reason).toBe('object');
        expect(paramsOf(ladderOutcomeMessage({...base, counted: false, reason: 'new_reason'}))).toEqual({reason: 'new_reason'});
        expect(paramsOf(ladderOutcomeMessage({...base, counted: false, reason: null}))).toEqual({reason: ''});
        expect(ladderOutcomeMessage({...base, counted: false, reason: 'takeback'}).key).toBe('ladder.notCounted');
    });

    it('засчитана: знак изменения и повышение', () => {
        expect(ladderOutcomeMessage(base)).toMatchObject({key: 'ladder.result', params: {rating: 1512, delta: '+12'}});
        expect(ladderOutcomeMessage({...base, delta: -8, promoted: true}))
            .toMatchObject({key: 'ladder.resultPromoted', params: {delta: '-8'}});
    });

    it('реплика бота: незнакомый ключ и не объект — без реплики', () => {
        expect(botCommentMessage(null)).toBeNull();
        expect(botCommentMessage('текст')).toBeNull();
        expect(botCommentMessage({key: 'no_such_key_at_all', params: {}})).toBeNull();
        expect(botCommentMessage({key: 7, params: {}})).toBeNull();
    });
});
