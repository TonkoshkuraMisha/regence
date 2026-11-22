// Диагностический экзамен, дополнительные пути: список тестов уровня, отказ сервера при старте и при сдаче,
// кнопка «назад к списку» посреди теста. Сеть — стаб fetch; таймеры — подменённые.

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

describe('диагностический экзамен: дополнительные пути', () => {
    it('в обзоре показаны тесты уровня; у сданного — «пересдать» и результат, у несданного — «начать»', async () => {
        stub();
        await act(async () => render(<MemoryRouter><ExamPage/></MemoryRouter>));
        expect(screen.getByTestId('exam-overall')).toBeInTheDocument();
        expect(screen.getByTestId('exam-test-level1')).toHaveTextContent('3 из 4');
        expect(screen.getByTestId('exam-start-level1')).toHaveTextContent('Пройти снова');
        expect(screen.getByTestId('exam-start-level2')).toHaveTextContent('Начать');
    });

    it('сервер отказал при старте — сообщение об ошибке, список остаётся', async () => {
        stub({questions: true});
        await act(async () => render(<MemoryRouter><ExamPage/></MemoryRouter>));
        await act(async () => fireEvent.click(screen.getByTestId('exam-start-level2')));
        expect(screen.getByRole('alert')).toBeInTheDocument();
        expect(screen.queryByTestId('exam-question')).toBeNull();
        expect(screen.getByTestId('exam-start-level2')).toBeInTheDocument();
    });

    it('сервер отказал при сдаче — сообщение об ошибке; повторное «не знаю» ничего не ломает', async () => {
        const calls = stub({submit: true});
        await act(async () => render(<MemoryRouter><ExamPage/></MemoryRouter>));
        await act(async () => fireEvent.click(screen.getByTestId('exam-start-level2')));
        await act(async () => fireEvent.click(screen.getByTestId('exam-skip')));
        await wait(EXAM_NEXT_MS);
        expect(screen.getByRole('alert')).toBeInTheDocument();
        expect(screen.queryByTestId('exam-result')).toBeNull();
        expect(calls.filter((u) => u.endsWith('/submit'))).toHaveLength(1);
    });

    it('«назад к списку» посреди теста возвращает обзор и позволяет начать заново', async () => {
        const calls = stub();
        await act(async () => render(<MemoryRouter><ExamPage/></MemoryRouter>));
        await act(async () => fireEvent.click(screen.getByTestId('exam-start-level2')));
        expect(screen.getByTestId('exam-question')).toBeInTheDocument();
        await act(async () => fireEvent.click(screen.getByRole('button', {name: 'Все тесты'})));
        expect(screen.queryByTestId('exam-question')).toBeNull();
        expect(screen.getByTestId('exam-start-level2')).toBeInTheDocument();
        await act(async () => fireEvent.click(screen.getByTestId('exam-start-level2')));
        expect(screen.getByTestId('exam-question')).toBeInTheDocument();
        expect(calls.filter((u) => u.endsWith('/level2/questions'))).toHaveLength(2);
    });
});
