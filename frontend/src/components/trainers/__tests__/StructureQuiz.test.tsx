// "Recognise the structure" (task 27.9): questions from the server, the answer is highlighted, a link to the game, the result after the last one.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {StructureQuiz} from '../StructureQuiz';

afterEach(() => vi.unstubAllGlobals());

const QUESTIONS = [
    {fen: '6k1/pp3ppp/4p3/8/3P4/8/PP3PPP/6K1 w - - 0 1', answer: 'isolated_pawn',
        options: ['carlsbad', 'isolated_pawn', 'saw', 'hedgehog'], game_id: null, ply: null},
    {fen: '6k1/pp1q1ppp/4p3/3pP3/3P4/8/PP3PPP/6K1 w - - 0 1', answer: 'french_chain',
        options: ['french_chain', 'symmetry', 'spanish', 'wedge'], game_id: 42, ply: 20},
];

describe('Name the structure', () => {
    it('two questions: a right and a wrong answer, a link to the game, the result', async () => {
        const fetchMock = vi.fn(async () => ({ok: true, json: async () => ({questions: QUESTIONS})}) as Response);
        vi.stubGlobal('fetch', fetchMock);
        const onFinish = vi.fn();
        await act(async () => render(<MemoryRouter><StructureQuiz seed={3} onFinish={onFinish}/></MemoryRouter>));
        expect(String(fetchMock.mock.calls[0])).toContain('/library/structure-quiz?count=10&seed=3');
        fireEvent.click(screen.getByTestId('quiz-option-isolated_pawn'));
        expect(screen.queryByTestId('structure-game-link')).toBeNull();  // a skeleton — without a game
        fireEvent.click(screen.getByTestId('quiz-next'));
        fireEvent.click(screen.getByTestId('quiz-option-wedge'));
        expect(screen.getByTestId('quiz-option-french_chain').className).toContain('emerald');
        expect(screen.getByTestId('structure-game-link')).toHaveAttribute('href', '/library/game/42');
        fireEvent.click(screen.getByTestId('quiz-next'));
        expect(onFinish).toHaveBeenCalledWith(10, 1);
    });
});

describe('free board after the answer (owner decision 18.11)', () => {
    it('before the answer the pieces do not move; after — the position can be played out and returned', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, json: async () => ({questions: QUESTIONS})}) as Response));
        await act(async () => render(<MemoryRouter><StructureQuiz seed={3} onFinish={vi.fn()}/></MemoryRouter>));
        const cell = (sq: string) => document.querySelector(`[data-square="${sq}"]`) as HTMLElement;
        fireEvent.click(cell('d4'));
        fireEvent.click(cell('d5'));
        expect(cell('d5').querySelector('img')).toBeNull();  // before the answer — only a show

        fireEvent.click(screen.getByTestId('quiz-option-carlsbad'));
        await act(async () => {
            fireEvent.click(cell('d4'));
        });
        await act(async () => {
            fireEvent.click(cell('d5'));
        });
        expect(cell('d5').querySelector('img')?.getAttribute('alt')).toBe('wp');
        expect(screen.getByTestId('explorer-controls')).toBeTruthy();

        fireEvent.click(screen.getByTestId('quiz-next'));  // the next question — a question position again
        expect(screen.queryByTestId('explorer-controls')).toBeNull();
    });
});

describe('Find the plan (27.9)', () => {
    it('options are the structures\' plans, after the answer — the structure name', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, json: async () => ({questions: QUESTIONS})}) as Response));
        await act(async () => render(<MemoryRouter><StructureQuiz seed={3} onFinish={vi.fn()} variant="plan"/></MemoryRouter>));
        expect(screen.getByText('Which plan fits this position?')).toBeInTheDocument();
        expect(screen.getByTestId('quiz-option-isolated_pawn')).toHaveTextContent('With the isolani');
        expect(screen.getByTestId('quiz-option-isolated_pawn')).not.toHaveTextContent('Isolated queen’s pawn');
        fireEvent.click(screen.getByTestId('quiz-option-carlsbad'));
        expect(screen.getByTestId('plan-verdict')).toHaveTextContent('Structure: Isolated queen’s pawn.');
    });
});
