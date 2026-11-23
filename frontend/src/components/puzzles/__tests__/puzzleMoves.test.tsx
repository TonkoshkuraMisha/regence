// Mouse moves on the puzzle page in all modes: the daily puzzle entirely by dragging, a multi-move puzzle with the opponent's
// reply, a wrong move, promotion, "My mistakes", defence exercises, and also attempts to move while the opponent
// is moving or the server reply has not yet arrived. The reason is the board where a piece was not dragged (the daily puzzle).

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import PuzzlesPage from '../PuzzlesPage';
import {resetThemeRegistryCache} from '../../../services/themes';
import {setToken} from '../../../services/authToken';

// Black deflects the rook: ...Re2, then Rd8+ Re8 Rxe8#.
const BACK_RANK = {
    id: 7, fen: '4r1k1/5ppp/8/8/8/8/3R1PPP/3R2K1 b - - 0 1', first_move: 'e8e2', rating: 1480,
    themes: ['back_rank_mate'], color: 'white', solution_length: 2,
};
// The king goes to the corner — promotion on a8.
const PROMOTE = {
    id: 8, fen: '6k1/P4ppp/8/8/8/8/8/K7 b - - 0 1', first_move: 'g8h8', rating: 900,
    themes: ['promotion'], color: 'white', solution_length: 1,
};
const SOLVED = {solved: true, rating_before: 1500, rating_after: 1510, delta: 10, streak: 1, themes: [], run: null};
const FAILED = {...SOLVED, solved: false, delta: -10, rating_after: 1490, streak: 0};
const PROFILE = {rating: 1500, games: 0, streak: 0, best: {'3': 0, '5': 0}, history: []};

type Handler = (url: string, body: { move?: string; square?: string } | null) => unknown;

function stub(handler: Handler, {delayMoveMs = 0} = {}) {
    const calls: { url: string; body: unknown }[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = String(input);
        const body = init?.body ? JSON.parse(String(init.body)) : null;
        calls.push({url, body});
        if (delayMoveMs && url.includes('/move')) await new Promise((resolve) => setTimeout(resolve, delayMoveMs));
        const answer = url.includes('/themes') ? {sections: [], themes: []}
            : url.endsWith('/puzzles/me') ? PROFILE : handler(url, body);
        return {ok: true, status: 200, json: async () => answer} as Response;
    }));
    return calls;
}

const cell = (name: string) => document.querySelector(`[data-square="${name}"]`) as HTMLElement;
const pieceAt = (name: string) => cell(name).querySelector('img')?.getAttribute('alt') ?? null;
const moves = (calls: { url: string; body: unknown }[], part = '/move') =>
    calls.filter((c) => c.url.includes(part)).map((c) => (c.body as { move: string }).move);

async function drag(from: string, to: string) {
    document.elementsFromPoint = vi.fn(() => [cell(to)]);
    await act(async () => {
        fireEvent.pointerDown(cell(from), {button: 0, pointerType: 'mouse', clientX: 5, clientY: 5});
    });
    await act(async () => {
        fireEvent.pointerMove(window, {clientX: 50, clientY: 50});
    });
    await act(async () => {
        fireEvent.pointerUp(window, {clientX: 90, clientY: 90});
    });
}

async function wait(ms: number) {
    await act(async () => {
        await vi.advanceTimersByTimeAsync(ms);
    });
}

async function openMode(mode: string, start = true) {
    render(<MemoryRouter><PuzzlesPage/></MemoryRouter>);
    await act(async () => {
        fireEvent.click(await screen.findByTestId(`puzzle-mode-${mode}`));
    });
    if (start && mode === 'rated') {
        await act(async () => {
            fireEvent.click(screen.getByTestId('puzzle-next'));
        });
    }
}

beforeEach(() => {
    setToken('jwt');
    vi.useFakeTimers({shouldAdvanceTime: true});
    resetThemeRegistryCache();
});
afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    localStorage.clear();
});

describe('the daily puzzle by dragging', () => {
    it('the opponent\'s move, two moves of the solver, the opponent\'s reply between them, the result', async () => {
        const calls = stub((url, body) => {
            if (url.includes('/daily')) return {...BACK_RANK, daily: true};
            return body?.move === 'd2d8'
                ? {correct: true, done: false, reply: 'e2e8', solution: null, result: null}
                : {correct: true, done: true, reply: null, solution: null, result: SOLVED};
        });
        await openMode('daily');
        await wait(600);
        expect(pieceAt('e2')).toBe('br');  // the opponent's move is played
        expect(screen.getByTestId('puzzle-status').textContent).toContain('Your move');

        await drag('d2', 'd8');
        expect(pieceAt('d8')).toBe('wr');  // the move is at once on the board
        await wait(500);
        expect(pieceAt('e8')).toBe('br');  // the opponent's reply
        await drag('d8', 'e8');

        expect(moves(calls)).toEqual(['d2d8', 'd8e8']);
        expect(await screen.findByTestId('puzzle-outcome')).toHaveTextContent('Solved!');
        expect(screen.getByTestId('puzzle-info').textContent).toContain('puzzle of the day');
    });

    it('while the opponent makes the first move, the pieces do not move', async () => {
        const calls = stub((url) => (url.includes('/daily') ? {...BACK_RANK, daily: true} : null));
        await openMode('daily');
        await drag('d2', 'd8');  // before the opponent's move
        expect(moves(calls)).toEqual([]);
        expect(pieceAt('d2')).toBe('wr');
    });
});

describe('the rated puzzle', () => {
    it('a wrong move by dragging: a mark, the move is taken back, the solution is played out', async () => {
        stub((url) => (url.includes('/next') ? BACK_RANK : {
            correct: false, done: true, reply: null, solution: ['d2d8', 'e2e8', 'd8e8'], result: FAILED,
        }));
        await openMode('rated');
        await wait(600);
        await drag('d2', 'd5');
        expect(await screen.findByTestId('puzzle-mark-wrong')).toBeTruthy();
        expect(screen.getByTestId('puzzle-outcome')).toHaveTextContent('Not this time');
        await wait(3000);
        expect(pieceAt('e8')).toBe('wr');  // the solution is played out on the board
        expect(pieceAt('d5')).toBeNull();
    });

    it('until the server replies, the second move does not go out', async () => {
        const calls = stub((url) => (url.includes('/next') ? BACK_RANK
            : {correct: true, done: false, reply: 'e2e8', solution: null, result: null}), {delayMoveMs: 300});
        await openMode('rated');
        await wait(600);
        await drag('d2', 'd8');
        await drag('d1', 'd7');  // the server is still thinking about the first move
        expect(moves(calls)).toEqual(['d2d8']);
        await wait(1000);
    });

    it('promotion by dragging: a piece choice, the move with a piece goes to the server', async () => {
        const calls = stub((url) => (url.includes('/next') ? PROMOTE
            : {correct: true, done: true, reply: null, solution: null, result: SOLVED}));
        await openMode('rated');
        await wait(600);
        await drag('a7', 'a8');
        expect(moves(calls)).toEqual([]);  // first — the piece choice
        await act(async () => {
            fireEvent.click(screen.getByTestId('puzzle-promote-r'));
        });
        expect(moves(calls)).toEqual(['a7a8r']);
        expect(pieceAt('a8')).toBe('wr');
    });

    it('after the result the board accepts no moves', async () => {
        const calls = stub((url) => (url.includes('/next') ? PROMOTE
            : {correct: true, done: true, reply: null, solution: null, result: SOLVED}));
        await openMode('rated');
        await wait(600);
        await drag('a7', 'a8');
        await act(async () => {
            fireEvent.click(screen.getByTestId('puzzle-promote-q'));
        });
        await screen.findByTestId('puzzle-outcome');
        await drag('a1', 'a2');
        expect(moves(calls)).toEqual(['a7a8q']);
    });
});

describe('"My mistakes" by dragging', () => {
    it('a position from the game: the move goes to the server', async () => {
        const calls = stub((url) => {
            if (url.endsWith('/personal')) return {due: 1, active: 1, mastered: 0, next_due_at: null};
            if (url.endsWith('/personal/next')) {
                return {id: 3, game_id: 41, ply: 6, previous_move: 'd1h5', color: 'black', themes: [], attempts: 0,
                    solved_streak: 0, fen: 'r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3'};
            }
            return {correct: true, solution: 'g7g6', played: 'g8f6', done: false, solved_streak: 1,
                next_due_at: new Date(Date.now() + 3 * 86_400_000).toISOString()};
        });
        await openMode('personal');
        await drag('g7', 'g6');
        expect(moves(calls, '/answer')).toEqual(['g7g6']);
        expect(await screen.findByTestId('personal-result')).toHaveTextContent('Correct!');
    });
});

describe('defence exercises by dragging', () => {
    it('a threat by click, the defence — by dragging', async () => {
        const calls = stub((url) => {
            if (url.includes('/defense/next')) {
                return {id: 4, kind: 'threat', theme: 'find_the_threat', color: 'white', rating: 1300, stage: 2, choices: [],
                    fen: 'r1b1k2r/pppp1ppp/2n5/2b1p3/2B1P2q/5N2/PPPP1PPP/RNBQ1RK1 w kq - 0 1'};
            }
            if (url.includes('/threat')) return {correct: true, threat: 'h4f2', motifs: []};
            return {correct: true, clean: true, good: ['f3h4'], threat: 'h4f2', refutations: {}, motifs: [],
                training: {theme: 'find_the_threat', stage: 2, recent: '1', mastered: false, advanced: false, window: 10, pass: 8}};
        });
        await openMode('defense', false);
        await act(async () => {
            fireEvent.click(screen.getByTestId('defense-next'));
        });
        await act(async () => {
            fireEvent.click(cell('h4'));
        });
        await drag('f3', 'h4');
        expect(moves(calls, '/answer')).toEqual(['f3h4']);
        expect(await screen.findByTestId('defense-outcome')).toHaveTextContent('Correct!');
    });

    it('"Don\'t blunder": the board does not move — only the buttons of the three moves', async () => {
        const calls = stub((url) => (url.includes('/defense/next') ? {
            id: 5, kind: 'blunder', theme: 'blunder_check', color: 'white', rating: 900, stage: 1,
            fen: 'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 1', choices: ['f1c4', 'f3e5', 'd2d4'],
        } : null));
        await openMode('defense', false);
        await act(async () => {
            fireEvent.click(screen.getByTestId('defense-kind-blunder'));
        });
        await drag('f1', 'c4');
        expect(moves(calls, '/answer')).toEqual([]);
    });
});
