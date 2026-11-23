// Board puzzles (task 19.4): a placement with conflict highlighting and a solution counter, a knight's tour with a hint.

import {fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {KnightTourGame, PlacementGame} from '../BoardPuzzleGames';
import {CLOSED_TOUR_SCORE, OPEN_TOUR_SCORE, allQueenSolutions, warnsdorffHint} from '../../../trainers/boardPuzzles';
import type {Cell} from '../../../trainers/boardPuzzles';

const FILES = 'abcdefgh';
const click = ([x, y]: Cell) => fireEvent.click(document.querySelector(`[data-cell="${FILES[x]}${y + 1}"]`)!);

afterEach(() => localStorage.clear());

describe('placement', () => {
    it('4 queens: a conflict — an error and highlighting; a solution — the result and the solution counter', () => {
        const onFinish = vi.fn();
        render(<PlacementGame level={1} seed={1} onFinish={onFinish}/>);
        click([0, 0]);
        click([1, 1]);   // diagonally — a conflict
        expect(screen.getByTestId('placement-status')).toHaveTextContent('some pieces attack each other');
        click([1, 1]);   // take back
        click([0, 0]);
        for (const cell of allQueenSolutions(4)[0]) click(cell);
        expect(onFinish).toHaveBeenCalledWith(90, 1);
        expect(screen.getByTestId('placement-found')).toHaveTextContent('Different solutions found: 1 of 2');
        expect(JSON.parse(localStorage.getItem('regence_placement_solutions_queens4')!)).toHaveLength(1);
    });

    it('more pieces than needed cannot be placed; domination shows the uncovered squares', () => {
        render(<PlacementGame level={10} seed={1} onFinish={vi.fn()}/>);
        expect(screen.getByTestId('placement-status')).toHaveTextContent('squares not covered: 64');
        for (const cell of [[0, 0], [1, 0], [5, 1], [0, 4], [4, 5], [7, 7]] as Cell[]) click(cell);
        expect(screen.getByTestId('placement-status')).toHaveTextContent('Placed: 5 of 5');
    });
});

describe('knight\'s tour', () => {
    it('Warnsdorff\'s hint leads to the end of 5×5; a wrong move — an error; the result of an open tour', () => {
        const onFinish = vi.fn();
        render(<KnightTourGame level={1} seed={1} onFinish={onFinish}/>);
        click([0, 0]);
        click([0, 1]);   // not a knight move
        const path: Cell[] = [[0, 0]];
        for (let i = 1; i < 25; i++) {
            fireEvent.click(screen.getByTestId('tour-hint'));
            const next = warnsdorffHint(path, 5)!;
            path.push(next);
            click(next);
        }
        expect(onFinish).toHaveBeenCalledTimes(1);
        const [score, mistakes] = onFinish.mock.calls[0];
        expect(mistakes).toBe(1);
        expect(score === OPEN_TOUR_SCORE - 90 || score === CLOSED_TOUR_SCORE - 90).toBe(true);
    });

    it('a dead end is recognised (the hint is unavailable); a move can be taken back', () => {
        render(<KnightTourGame level={1} seed={1} onFinish={vi.fn()}/>);
        // A short route on 5×5 after which the knight has no moves (found by brute force).
        const deadEnd: Cell[] = [[0, 0], [1, 2], [2, 4], [4, 3], [3, 1], [1, 0], [0, 2], [2, 3], [0, 4]];
        for (const cell of deadEnd) click(cell);
        expect(screen.getByTestId('tour-stuck')).toHaveTextContent('dead end');
        expect(screen.getByTestId('tour-hint')).toBeDisabled();
        fireEvent.click(screen.getByTestId('tour-undo'));
        expect(screen.queryByTestId('tour-stuck')).toBeNull();
        expect(screen.getByTestId('tour-status')).toHaveTextContent('Squares visited: 8 of 25');
    });
});
