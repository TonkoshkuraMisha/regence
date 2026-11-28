// "Plan in this position" (task 27.9): the seeded attempt over the prepared set and the whole quiz in the component.

import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {Chess} from 'chess.js';
import {PositionPlanQuiz} from '../PositionPlanQuiz';
import {PLAN_CODES, PLAN_ROUNDS, POSITION_PLANS, planAttempt} from '../../../trainers/positionPlans';
import {en} from '../../../i18n/messages/en';
import {uk} from '../../../i18n/messages/uk';

describe('position plan attempt', () => {
    it('is the same for the same seed, different positions, the master plan among the options', () => {
        const attempt = planAttempt(5);
        expect(planAttempt(5)).toEqual(attempt);
        expect(attempt).toHaveLength(PLAN_ROUNDS);
        expect(new Set(attempt.map((q) => q.question.id)).size).toBe(PLAN_ROUNDS);
        for (const shown of attempt) {
            expect(shown.options[shown.answer]).toBe(shown.question.options[0]);
            expect(shown.options).toHaveLength(shown.question.options.length);
        }
    });

    it('does not ask the same plan twice in a row', () => {
        for (const seed of [1, 2, 3, 4]) {
            const plans = planAttempt(seed).map((q) => q.question.options[0].plan);
            plans.slice(1).forEach((plan, i) => expect(plan).not.toBe(plans[i]));
        }
    });

    it('every plan has a name in both catalogues and every first move is legal', () => {
        for (const code of PLAN_CODES) {
            expect(en.positionPlans[code]).toBeTruthy();
            expect(uk.positionPlans[code]).toBeTruthy();
        }
        for (const question of POSITION_PLANS) {
            for (const option of question.options) {
                expect(PLAN_CODES).toContain(option.plan);
                expect(() => new Chess(question.fen).move({from: option.move.slice(0, 2), to: option.move.slice(2, 4)})).not.toThrow();
            }
        }
    });
});

describe('PositionPlanQuiz', () => {
    it('right answers - 100 points; the game and the evaluations are shown after each answer', () => {
        const onFinish = vi.fn();
        render(<PositionPlanQuiz seed={7} onFinish={onFinish}/>);
        for (const shown of planAttempt(7)) {
            fireEvent.click(screen.getByTestId(`plan-option-${shown.answer}`));
            expect(screen.getByTestId('plan-game').textContent).toContain(shown.question.white);
            expect(screen.getByTestId(`plan-score-${shown.answer}`)).toBeTruthy();
            fireEvent.click(screen.getByTestId('quiz-next'));
        }
        expect(onFinish).toHaveBeenCalledWith(100, 0);
    });

    it('a wrong answer counts as a mistake and names the master plan', () => {
        render(<PositionPlanQuiz seed={3} onFinish={vi.fn()}/>);
        const shown = planAttempt(3)[0];
        const wrong = shown.answer === 0 ? 1 : 0;
        fireEvent.click(screen.getByTestId(`plan-option-${wrong}`));
        expect(screen.getByTestId('quiz-score').textContent).toContain('1');
        expect(screen.getByTestId('plan-verdict').textContent).toContain(en.positionPlans[shown.question.options[0].plan]);
    });

    it('the game can be stepped through on the board', () => {
        render(<PositionPlanQuiz seed={3} onFinish={vi.fn()}/>);
        const shown = planAttempt(3)[0];
        fireEvent.click(screen.getByTestId(`plan-option-${shown.answer}`));
        fireEvent.click(screen.getByTestId('plan-game-step'));
        fireEvent.click(screen.getByTestId('plan-game-step'));
        expect(screen.getByTestId('plan-game-step')).toBeTruthy();
    });
});
