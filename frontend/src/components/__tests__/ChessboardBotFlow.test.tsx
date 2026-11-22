// --- FILE: frontend/src/components/__tests__/ChessboardBotFlow.test.tsx ---
// Ход партии с ботом в Chessboard.tsx, не покрытый основными тестами: мат ставит игрок (итог, сохранение
// партии, звук победы), возврат хода в партии с ботом и на свободной доске,
// переход по ходу из списка и возврат к живой позиции. Бот отвечает заготовленными ходами (стаб /bots/move),
// время — фальшивые таймеры; ход — щелчками через test/boardMoves.ts.

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

/** Ответы бота по порядку запросов: после последнего повторяется он же. */
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
        fireEvent.click(await screen.findByRole('button', {name: /Белыми/}));
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

describe('мат ставит игрок', () => {
    it('партия заканчивается победой, итог сохраняется, звучит победа; по ходу из списка можно вернуться назад', async () => {
        const fetchMock = await startBotGame([{uci: 'f7f6', san: 'f6'}, {uci: 'g7g5', san: 'g5'}]);
        await playMove('e2', 'e4');
        await botReplies();
        await playMove('d2', 'd4');
        await botReplies();
        await playMove('d1', 'h5');

        expect(screen.getByText(/Партия против .* окончена и сохранена.*\(1-0\)/)).toBeInTheDocument();
        expect(vi.mocked(soundEngine.play)).toHaveBeenCalledWith('victory');
        const saved = (fetchMock.mock.calls as unknown as [string][]).some(([url]) => String(url).includes('/bots/save-game'));
        expect(saved).toBe(true);

        // Список ходов: щелчок по первому ходу показывает позицию после него, повторный по тому же — ничего не меняет.
        fireEvent.click(screen.getByText('e4'));
        expect(pieceAt('d4')).toBeNull();
        expect(pieceAt('e4')).toBe('wp');
        fireEvent.click(screen.getByText('e4'));
        // Щелчок по последнему ходу возвращает к живой позиции.
        fireEvent.click(screen.getByText('Qh5#'));
        expect(pieceAt('h5')).toBe('wq');
    });
});

describe('возврат хода', () => {
    it('возврат хода в партии с ботом снимает свой ход и ответ бота', async () => {
        await startBotGame([{uci: 'e7e5', san: 'e5'}]);
        await playMove('e2', 'e4');
        await botReplies();
        expect(pieceAt('e5')).toBe('bp');

        await act(async () => {
            fireEvent.click(screen.getByRole('button', {name: /Вернуть ход/}));
        });
        expect(pieceAt('e5')).toBeNull();
        expect(pieceAt('e4')).toBeNull();
        expect(pieceAt('e2')).toBe('wp');
    });
});

describe('свободная доска: возврат хода', () => {
    it('кнопка «Отменить ход» откатывает последний ход', async () => {
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
            fireEvent.click(screen.getByRole('button', {name: /Отменить ход/}));
        });
        expect(pieceAt('e2')).toBe('wp');
        expect(pieceAt('e4')).toBeNull();
    });
});
