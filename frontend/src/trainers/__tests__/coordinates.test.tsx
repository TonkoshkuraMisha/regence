// Coordinate trainers (task 19.2): square colour, diagonals, seeded questions, settings encoding, a timed game.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {
    ALL_SQUARES, COORD_TRAINERS, coordQuestion, isCorrect, levelToOptions, optionsToLevel, sameDiagonal, squareColor,
} from '../coordinates';
import {CoordinateGame} from '../../components/trainers/CoordinateGames';

afterEach(() => vi.useRealTimers());

describe('coordinates: logic', () => {
    it('square colour: a1 and h8 are dark, h1 and a8 are light; in equal numbers', () => {
        expect([squareColor('a1'), squareColor('h8'), squareColor('h1'), squareColor('a8'), squareColor('e4'), squareColor('d4')])
            .toEqual(['dark', 'dark', 'light', 'light', 'light', 'dark']);
        expect(ALL_SQUARES.filter((s) => squareColor(s) === 'dark')).toHaveLength(32);
    });

    it('diagonals', () => {
        expect(sameDiagonal('a1', 'h8')).toBe(true);
        expect(sameDiagonal('c1', 'h6')).toBe(true);
        expect(sameDiagonal('e4', 'e5')).toBe(false);
        expect(sameDiagonal('e4', 'e4')).toBe(false);
    });

    it('settings ↔ level 1–8 without loss', () => {
        const levels = new Set<number>();
        for (const side of ['white', 'black'] as const) {
            for (const coordinates of [true, false]) {
                for (const seconds of [30, 60] as const) {
                    const level = optionsToLevel({side, coordinates, seconds});
                    levels.add(level);
                    expect(levelToOptions(level)).toEqual({side, coordinates, seconds});
                }
            }
        }
        expect([...levels].sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    });

    it('seeded questions are repeatable and always solvable: exactly one right option', () => {
        for (const trainer of COORD_TRAINERS) {
            for (let i = 0; i < 200; i++) {
                const q = coordQuestion(trainer, 42, i);
                expect(coordQuestion(trainer, 42, i)).toEqual(q);
                if (trainer === 'coord_name' || trainer === 'coord_diagonal') {
                    expect(q.options).toHaveLength(4);
                    expect(new Set(q.options).size).toBe(4);
                    expect(q.options.filter((o) => isCorrect(q, o))).toHaveLength(1);
                }
                if (trainer === 'coord_diagonal') {
                    expect(q.options.filter((o) => sameDiagonal(q.square, o))).toEqual([q.answer]);
                }
                if (trainer === 'coord_color') expect(q.answer).toBe(squareColor(q.square));
            }
        }
    });
});

describe('coordinates: game', () => {
    it('"Find the square": a right click — a point, a wrong one — a mistake; by time — the result', () => {
        vi.useFakeTimers();
        const onFinish = vi.fn();
        render(<CoordinateGame trainer="coord_find" level={1} seed={7} onFinish={onFinish}/>);
        const first = coordQuestion('coord_find', 7, 0).square;
        fireEvent.click(document.querySelector(`[data-square="${first}"]`)!);
        const second = coordQuestion('coord_find', 7, 1).square;
        const wrong = second === 'a1' ? 'h8' : 'a1';
        fireEvent.click(document.querySelector(`[data-square="${wrong}"]`)!);
        expect(screen.getByTestId('coord-score')).toHaveTextContent('Right: 1 · mistakes: 1');
        act(() => vi.advanceTimersByTime(31_000));
        expect(onFinish).toHaveBeenCalledWith(1, 1);
    });

    it('"Square colour" — by buttons; "Name the square" — by options; the coordinates can be hidden', () => {
        const onFinish = vi.fn();
        const {unmount} = render(<CoordinateGame trainer="coord_color" level={1} seed={3} onFinish={onFinish}/>);
        const q = coordQuestion('coord_color', 3, 0);
        fireEvent.click(screen.getByTestId(`coord-${q.answer}`));
        expect(screen.getByTestId('coord-score')).toHaveTextContent('Right: 1');
        unmount();
        render(<CoordinateGame trainer="coord_name" level={3} seed={3} onFinish={onFinish}/>);
        const name = coordQuestion('coord_name', 3, 0);
        expect(screen.getByTestId('coord-board').querySelector(`[data-square="${name.square}"] [data-testid="coord-highlight"]`)).not.toBeNull();
        expect(screen.getByTestId('coord-board').textContent).toBe('');   // level 3: without coordinates
        fireEvent.click(screen.getByTestId(`coord-option-${name.answer}`));
        expect(screen.getByTestId('coord-score')).toHaveTextContent('Right: 1');
    });

    it('for Black the board is flipped', () => {
        render(<CoordinateGame trainer="coord_find" level={2} seed={1} onFinish={vi.fn()}/>);
        const squares = Array.from(screen.getByTestId('coord-board').querySelectorAll('[data-square]')).map((el) => el.getAttribute('data-square'));
        expect(squares[0]).toBe('h1');
        expect(squares[63]).toBe('a8');
    });
});
