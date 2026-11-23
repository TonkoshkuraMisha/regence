// Calculation and attention (task 19.7): whole quizzes (the right answer — by the same logic as generation), "Checks and captures".

import {act, fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {ChecksGame, QUIZ_ROUNDS, QuizGame} from '../CalcGames';
import type {QuizKind} from '../CalcGames';
import {loadAllClassics} from '../../../content/classics';
import {positionPool} from '../../../trainers/memory';
import {
    checksAndCaptures, checksPosition, compareQuestion, distanceQuestion, evalQuestion, exchangeQuestion, squareFen, squareQuestion,
} from '../../../trainers/calculation';
import {Chess} from 'chess.js';

async function settle() {
    for (let i = 0; i < 5; i++) await act(async () => Promise.resolve());
}

describe('calculation quizzes', () => {
    it.each(['calc_exchange', 'calc_distance', 'calc_square', 'calc_eval', 'calc_compare'] as QuizKind[])('%s: right answers — 100 points', async (kind) => {
        const games = await loadAllClassics();
        const pool = positionPool(games, []);
        const onFinish = vi.fn();
        render(<QuizGame kind={kind} seed={8} onFinish={onFinish}/>);
        await settle();
        for (let i = 0; i < QUIZ_ROUNDS; i++) {
            const answer = kind === 'calc_exchange' ? exchangeQuestion(pool, 8 * 97 + i)!.answer
                : kind === 'calc_distance' ? String(distanceQuestion(8, i).answer)
                    : kind === 'calc_square' ? (squareQuestion(8, i).answer ? 'yes' : 'no')
                        : kind === 'calc_compare' ? compareQuestion(games, 8 * 71 + i)!.best
                            : evalQuestion(games, 8 * 53 + i)!.answer;
            fireEvent.click(screen.getByTestId(`quiz-option-${answer}`));
            fireEvent.click(screen.getByTestId('quiz-next'));
        }
        expect(onFinish).toHaveBeenCalledWith(100, 0);
    }, 30_000);

    it('a wrong answer — an error, the right one is highlighted', async () => {
        render(<QuizGame kind="calc_square" seed={2} onFinish={vi.fn()}/>);
        await settle();
        const right = squareQuestion(2, 0).answer ? 'yes' : 'no';
        const wrong = right === 'yes' ? 'no' : 'yes';
        fireEvent.click(screen.getByTestId(`quiz-option-${wrong}`));
        expect(screen.getByTestId('quiz-score')).toHaveTextContent('Right: 0 · mistakes: 1');
        expect(screen.getByTestId(`quiz-option-${right}`).className).toContain('emerald');
    });

    it('after the answer the position can be played out on the board (a pawn-and-king race)', async () => {
        render(<QuizGame kind="calc_square" seed={2} onFinish={vi.fn()}/>);
        await settle();
        expect(screen.queryByTestId('explorer-controls')).toBeNull();  // before the answer the board is closed
        fireEvent.click(screen.getByTestId('quiz-option-yes'));
        expect(screen.getByTestId('explorer-back')).toBeDisabled();
        const move = new Chess(squareFen(squareQuestion(2, 0))).moves({verbose: true})[0];
        fireEvent.click(document.querySelector(`[data-square="${move.from}"]`)!);
        fireEvent.click(document.querySelector(`[data-square="${move.to}"]`)!);
        expect(screen.getByTestId('explorer-back')).not.toBeDisabled();
        fireEvent.click(screen.getByTestId('explorer-back'));
        expect(screen.getByTestId('explorer-back')).toBeDisabled();
    });
});

describe('checks and captures', () => {
    it('all right marks — 100 per position; an extra one — minus; review by colours', async () => {
        const games = await loadAllClassics();
        const pool = positionPool(games, []);
        const onFinish = vi.fn();
        render(<ChecksGame seed={6} onFinish={onFinish}/>);
        await settle();
        for (let round = 0; round < 3; round++) {
            const fen = checksPosition(pool, 6 * 13 + round * 101)!;
            for (const uci of checksAndCaptures(fen)) {
                fireEvent.click(document.querySelector(`[data-square="${uci.slice(0, 2)}"]`)!);
                fireEvent.click(document.querySelector(`[data-square="${uci.slice(2, 4)}"]`)!);
            }
            fireEvent.click(screen.getByTestId('checks-done'));
            expect(screen.getByTestId('checks-review')).toHaveTextContent('missed: 0');
            fireEvent.click(screen.getByTestId('checks-next'));
        }
        expect(onFinish).toHaveBeenCalledWith(300, 0);
    }, 30_000);
});

describe('"Compare two moves" (27.9)', () => {
    it('a master move against a weaker line by a pawn and more, review after the answer', async () => {
        const games = await loadAllClassics();
        for (let seed = 0; seed < 40; seed++) {
            const q = compareQuestion(games, seed)!;
            expect(q.bestCp - q.otherCp).toBeGreaterThanOrEqual(100);
            expect(new Set(q.options)).toEqual(new Set([q.best, q.other]));
        }
        render(<QuizGame kind="calc_compare" seed={3} onFinish={vi.fn()}/>);
        await settle();
        const q = compareQuestion(games, 3 * 71)!;
        fireEvent.click(screen.getByTestId(`quiz-option-${q.other}`));
        expect(screen.getByTestId('quiz-explain')).toHaveTextContent('is stronger');
        expect(screen.getByTestId(`quiz-option-${q.best}`).className).toContain('emerald');
    }, 30_000);
});
