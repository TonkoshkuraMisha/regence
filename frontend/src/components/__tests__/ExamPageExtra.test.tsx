// The diagnostic exam, additional paths: the list of level tests, a server refusal at the start and at submission,
// the "back to the list" button in the middle of a test. The network is a fetch stub; timers are replaced.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {EXAM_NEXT_MS, ExamPage} from '../ExamPage';
import {setToken} from '../../services/authToken';

const SUMMARY = {
    tests: ['F'], level_tests: ['level1', 'level2'], overall: null, level: null, passed: 0, of: 10,
    results: {level1: {correct: 3, total: 4, estimate: 1100, level: 'fourth', at: null}},
};
const MATE1 = '6k1/5ppp/p7/8/8/8/5PPP/3Q2K1 w - - 0 2';
const QUESTIONS = [{id: 2, fen: MATE1, color: 'white', previous_move: 'a7a6'}];
const GRADED = {correct: 0, total: 1, estimate: 900, level: 'fifth', points: 0, max_points: 1, review: [
    {id: 2, answer: '0000', correct: false, solution: 'd1d8', solution_san: 'Qd8#', rating: 1600, points: 0, max_points: 1},
]};

type Failing = { questions?: boolean; submit?: boolean };

function stub(failing: Failing = {}) {
    const calls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
        const u = String(url);
        calls.push(u);
        if ((failing.questions && u.endsWith('/questions')) || (failing.submit && u.endsWith('/submit'))) {
            return {ok: false, status: 500, json: async () => ({detail: {code: 'internal_error'}})} as Response;
        }
        const body = u.endsWith('/questions') ? {section: 'F', questions: QUESTIONS, time_limit_s: null}
            : u.endsWith('/submit') ? GRADED : SUMMARY;
        return {ok: true, json: async () => body} as Response;
    }));
    return calls;
}

const wait = (ms: number) => act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
});

beforeEach(() => {
    vi.useFakeTimers();
    setToken('jwt');
});
afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    setToken(null);
});

describe('diagnostic exam: additional paths', () => {
    it('the overview shows the level tests; a passed one has "retake" and the result, a not passed one has "start"', async () => {
        stub();
        await act(async () => render(<MemoryRouter><ExamPage/></MemoryRouter>));
        expect(screen.getByTestId('exam-overall')).toBeInTheDocument();
        expect(screen.getByTestId('exam-test-level1')).toHaveTextContent('3 of 4');
        expect(screen.getByTestId('exam-start-level1')).toHaveTextContent('Retake');
        expect(screen.getByTestId('exam-start-level2')).toHaveTextContent('Start');
    });

    it('the server refused at the start — an error message, the list stays', async () => {
        stub({questions: true});
        await act(async () => render(<MemoryRouter><ExamPage/></MemoryRouter>));
        await act(async () => fireEvent.click(screen.getByTestId('exam-start-level2')));
        expect(screen.getByRole('alert')).toBeInTheDocument();
        expect(screen.queryByTestId('exam-question')).toBeNull();
        expect(screen.getByTestId('exam-start-level2')).toBeInTheDocument();
    });

    it('the server refused at submission — an error message; a repeated "don\'t know" changes nothing', async () => {
        const calls = stub({submit: true});
        await act(async () => render(<MemoryRouter><ExamPage/></MemoryRouter>));
        await act(async () => fireEvent.click(screen.getByTestId('exam-start-level2')));
        await act(async () => fireEvent.click(screen.getByTestId('exam-skip')));
        await wait(EXAM_NEXT_MS);
        expect(screen.getByRole('alert')).toBeInTheDocument();
        expect(screen.queryByTestId('exam-result')).toBeNull();
        expect(calls.filter((u) => u.endsWith('/submit'))).toHaveLength(1);
    });

    it('"back to the list" in the middle of a test shows the overview and lets you start again', async () => {
        const calls = stub();
        await act(async () => render(<MemoryRouter><ExamPage/></MemoryRouter>));
        await act(async () => fireEvent.click(screen.getByTestId('exam-start-level2')));
        expect(screen.getByTestId('exam-question')).toBeInTheDocument();
        await act(async () => fireEvent.click(screen.getByRole('button', {name: 'All tests'})));
        expect(screen.queryByTestId('exam-question')).toBeNull();
        expect(screen.getByTestId('exam-start-level2')).toBeInTheDocument();
        await act(async () => fireEvent.click(screen.getByTestId('exam-start-level2')));
        expect(screen.getByTestId('exam-question')).toBeInTheDocument();
        expect(calls.filter((u) => u.endsWith('/level2/questions'))).toHaveLength(2);
    });
});
