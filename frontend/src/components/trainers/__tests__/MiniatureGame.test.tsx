// "Miniatures" (task 27.9): any mate counts, a wrong move shows the game move, the result after the last one.

import {act, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {isMate, MiniatureGame} from '../MiniatureGame';

let boardMove: ((uci: string) => void) | null = null;
vi.mock('../../puzzles/PuzzleBoard', () => ({
    PuzzleBoard: ({onMove, fen, interactive, arrows}: {
        onMove: (uci: string) => void; fen: string; interactive: boolean; arrows: { from: string; to: string }[];
    }) => {
        boardMove = onMove;
        return <div data-testid="board" data-fen={fen} data-interactive={String(interactive)}
                    data-arrows={arrows.map((a) => a.from + a.to).join(',')}/>;
    },
}));

afterEach(() => vi.unstubAllGlobals());

const BEFORE_MATE = 'r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4';
const ITEM = {id: 7, white: 'A', black: 'B', event: '', site: '', date: '', year: 1900, result: '1-0', eco: 'C20', opening: '',
    plies: 7, structure: null, fen: BEFORE_MATE, moves: ['e2e4', 'e7e5', 'd1h5', 'b8c6', 'f1c4', 'g8f6'], answer: 'h5f7'};

describe('Miniatures', () => {
    it('mate is checked by the position', () => {
        expect(isMate(BEFORE_MATE, 'h5f7')).toBe(true);
        expect(isMate(BEFORE_MATE, 'h5e5')).toBe(false);
        expect(isMate(BEFORE_MATE, 'a1a8')).toBe(false);  // an illegal move
    });

    it('a right and a wrong answer, the result', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, json: async () => ({miniatures: [ITEM, ITEM]})}) as Response));
        const onFinish = vi.fn();
        await act(async () => render(<MemoryRouter><MiniatureGame seed={1} onFinish={onFinish}/></MemoryRouter>));
        expect(screen.getByTestId('miniature-players')).toHaveTextContent('A — B, 1900');
        act(() => boardMove!('h5f7'));
        expect(screen.getByTestId('miniature-verdict')).toHaveTextContent('Mate!');
        expect(screen.getByTestId('miniature-game-link')).toHaveAttribute('href', '/library/game/7');
        act(() => screen.getByTestId('quiz-next').click());
        act(() => boardMove!('h5e5'));
        expect(screen.getByTestId('miniature-verdict')).toHaveTextContent('Not mate');
        act(() => screen.getByTestId('quiz-next').click());
        expect(onFinish).toHaveBeenCalledWith(10, 1);
    });

    it('after the answer the board is free: the move stands on the board, the position can be played out and returned', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, json: async () => ({miniatures: [ITEM, ITEM]})}) as Response));
        await act(async () => render(<MemoryRouter><MiniatureGame seed={1} onFinish={vi.fn()}/></MemoryRouter>));
        const board = () => screen.getByTestId('board');
        // A right mate — the queen stands on f7, no arrow, the board still responds.
        act(() => boardMove!('h5f7'));
        expect(board().dataset.fen).toContain('r1bqkb1r/pppp1Qpp/');
        expect(board().dataset.interactive).toBe('true');
        expect(board().dataset.arrows).toBe('');
        act(() => screen.getByTestId('explorer-reset').click());
        expect(board().dataset.fen).toBe(BEFORE_MATE);

        // A wrong answer — the puzzle position and the game move's arrow; it can be played out yourself and taken back.
        act(() => screen.getByTestId('quiz-next').click());
        act(() => boardMove!('h5e5'));
        expect(board().dataset.fen).toBe(BEFORE_MATE);
        expect(board().dataset.arrows).toBe('h5f7');
        act(() => boardMove!('h5f7'));
        expect(board().dataset.fen).toContain('pppp1Qpp');
        expect(board().dataset.arrows).toBe('');
        expect(screen.getByTestId('miniature-verdict')).toHaveTextContent('Not mate');  // the first answer is counted
        act(() => screen.getByTestId('explorer-back').click());
        expect(board().dataset.fen).toBe(BEFORE_MATE);
    });
});
