// Board puzzles (task 19.4): all 92 queen solutions, independence and domination, a knight's tour.

import {describe, expect, it} from 'vitest';
import {
    PLACEMENT_PUZZLES, allQueenSolutions, attacks, conflicts, isClosedTour, isSolved, isTour, knightMoves, placementPuzzle,
    solutionKey, tourSize, uncovered, warnsdorffHint,
} from '../boardPuzzles';
import type {Cell} from '../boardPuzzles';

const puzzle = (id: string) => PLACEMENT_PUZZLES.find((p) => p.id === id)!;

describe('placements', () => {
    it('queens: 92 solutions on 8×8, all pass the check and differ; on 4×4 — two', () => {
        const solutions = allQueenSolutions(8);
        expect(solutions).toHaveLength(92);
        expect(new Set(solutions.map(solutionKey)).size).toBe(92);
        for (const s of solutions) expect(isSolved(puzzle('queens8'), s)).toBe(true);
        expect(allQueenSolutions(4)).toHaveLength(2);
        expect(allQueenSolutions(6)).toHaveLength(4);
    });

    it('a conflict highlights both pieces; an incomplete placement is not a solution', () => {
        const cells: Cell[] = [[0, 0], [3, 3], [1, 6]];
        expect([...conflicts('Q', cells, 8)].sort()).toEqual(['0,0', '3,3']);
        expect(isSolved(puzzle('queens8'), allQueenSolutions(8)[0].slice(0, 7))).toBe(false);
    });

    it('8 rooks, 14 bishops, 32 knights — known solutions', () => {
        expect(isSolved(puzzle('rooks8'), Array.from({length: 8}, (_, i) => [i, i] as Cell))).toBe(true);
        const bishops: Cell[] = [...Array.from({length: 8}, (_, x) => [x, 0] as Cell), ...Array.from({length: 6}, (_, x) => [x + 1, 7] as Cell)];
        expect(isSolved(puzzle('bishops14'), bishops)).toBe(true);
        const knights: Cell[] = [];
        for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) if ((x + y) % 2 === 0) knights.push([x, y]);
        expect(isSolved(puzzle('knights32'), knights)).toBe(true);
    });

    it('domination: 5 queens and 12 knights — known solutions; without one — none', () => {
        const queens: Cell[] = [[0, 0], [1, 0], [5, 1], [0, 4], [4, 5]];   // found by brute force
        expect(uncovered('Q', queens, 8)).toEqual([]);
        expect(isSolved(puzzle('queens5dom'), queens)).toBe(true);
        expect(isSolved(puzzle('queens5dom'), queens.slice(0, 4))).toBe(false);
        // 12 knights controlling the whole board (found by brute force).
        const knights: Cell[] = [[1, 2], [5, 1], [2, 6], [6, 5], [2, 2], [5, 2], [2, 5], [5, 5], [4, 2], [2, 3], [5, 4], [3, 5]];
        expect(uncovered('N', knights, 8)).toEqual([]);
        expect(isSolved(puzzle('knights12'), knights)).toBe(true);
    });

    it('lines stop at occupied squares; levels in order', () => {
        expect(attacks('R', [0, 0], 8, new Set(['0,2'])).map(String)).toContain('0,2');
        expect(attacks('R', [0, 0], 8, new Set(['0,2'])).map(String)).not.toContain('0,3');
        expect(placementPuzzle(1).id).toBe('queens4');
        expect(placementPuzzle(99).id).toBe(PLACEMENT_PUZZLES[PLACEMENT_PUZZLES.length - 1].id);
    });
});

describe('knight\'s tour', () => {
    function warnsdorffTour(size: number, start: Cell): Cell[] {
        const path: Cell[] = [start];
        while (path.length < size * size) {
            const next = warnsdorffHint(path, size);
            if (!next) break;
            path.push(next);
        }
        return path;
    }

    it('Warnsdorff\'s rule completes 5×5 (from a corner), 6×6 and 8×8 entirely', () => {
        for (const size of [5, 6, 8]) {
            const tour = warnsdorffTour(size, [0, 0]);
            expect(isTour(tour, size), `${size}`).toBe(true);
        }
    });

    it('tour check: a repeated square and a non-knight move — not a tour; closedness', () => {
        const tour = warnsdorffTour(6, [0, 0]);
        expect(isTour([...tour.slice(0, -1), tour[0]], 6)).toBe(false);
        expect(isTour([[0, 0], [1, 1]], 2)).toBe(false);
        // A closed tour on 6×6 exists: we check the function on a known one (the last move returns to the start).
        expect(isClosedTour(tour, 6)).toBe(knightMoves(tour[tour.length - 1], 6, new Set()).some((c) => c[0] === 0 && c[1] === 0));
        expect(tourSize(1)).toBe(5);
        expect(tourSize(3)).toBe(8);
    });
});
