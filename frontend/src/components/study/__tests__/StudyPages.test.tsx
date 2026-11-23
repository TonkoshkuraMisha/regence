// Joint review (task 17.3): the host's arrows, a question, the student's answer with a move, a lesson step in the school format.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setToken} from '../../../services/authToken';
import {lessonProblems, lessonStep, sessionLesson, StudyRoomPage} from '../StudyPages';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const BOARD = {fen: START, last_move: null, arrows: [], highlights: [], ghost: null};
const cell = (name: string) => document.querySelector(`[data-square="${name}"]`) as HTMLElement;

function room(extra: Record<string, unknown> = {}) {
    return {code: 'abc12345', host: 'coach', is_host: true, version: 3, board: BOARD, chat: [], question: null, participants: ['coach'], ...extra};
}

function stub(state: Record<string, unknown>) {
    const fetchMock = vi.fn(async () => ({ok: true, status: 200, json: async () => state} as Response));
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

const calls = (fetchMock: ReturnType<typeof stub>, method: string) =>
    (fetchMock.mock.calls as unknown as [string, RequestInit][]).filter(([, init]) => init?.method === method);

function open() {
    return render(<MemoryRouter initialEntries={['/study/abc12345']}><Routes><Route path="/study/:code" element={<StudyRoomPage/>}/></Routes></MemoryRouter>);
}

beforeEach(() => setToken('jwt'));
afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
});

describe('joint review', () => {
    it('the host: an arrow by two clicks in the chosen colour and a question with options', async () => {
        const fetchMock = stub(room());
        open();
        await screen.findByTestId('study-tools');
        fireEvent.click(screen.getByTestId('tool-arrow'));
        fireEvent.click(screen.getByRole('button', {name: 'Red'}));
        fireEvent.click(cell('e2'));
        await act(async () => fireEvent.click(cell('e4')));
        expect(JSON.parse(String(calls(fetchMock, 'PUT')[0][1].body)).arrows).toEqual([{from: 'e2', to: 'e4', color: 'red'}]);

        fireEvent.change(screen.getByTestId('question-prompt'), {target: {value: 'Which plan?'}});
        fireEvent.change(screen.getByTestId('question-options'), {target: {value: 'Attack\nDefence'}});
        fireEvent.change(screen.getByTestId('question-correct'), {target: {value: '2'}});
        await act(async () => fireEvent.click(screen.getByTestId('question-ask')));
        expect(JSON.parse(String(calls(fetchMock, 'POST').at(-1)![1].body))).toMatchObject({
            kind: 'choice', prompt: 'Which plan?', options: ['Attack', 'Defence'], correct: 1,
        });
        expect(screen.getByTestId('study-lesson')).toHaveTextContent('1 steps');
    });

    it('the student: an answer to a "find the move" question — by a move on their own board', async () => {
        const fetchMock = stub(room({is_host: false, question: {id: 'q', kind: 'move', prompt: 'Your move', deadline: Date.now() / 1000 + 60, revealed: false}}));
        open();
        expect(await screen.findByTestId('study-question')).toHaveTextContent('Your move');
        // A move with two clicks: dragging is checked by the PuzzleBoard tests, and here under full load it was occasionally lost.
        await act(async () => {
            fireEvent.click(cell('e2'));
        });
        await act(async () => {
            fireEvent.click(cell('e4'));
        });
        // The answer goes out asynchronously — under CI load the request might not have been sent yet: wait for it.
        await waitFor(() => expect(calls(fetchMock, 'POST')).toHaveLength(1));
        expect(JSON.parse(String(calls(fetchMock, 'POST')[0][1].body))).toEqual({answer: 'e2e4'});
    });

    it('a lesson from a session: without a question — not ready; with a question — it passes the school format check', () => {
        const step = lessonStep({...BOARD, arrows: [{from: 'e2', to: 'e4', color: 'green'}], highlights: [{square: 'e4', tone: 'light'}]}, 'Center');
        expect(lessonProblems(sessionLesson('abc', 'Review', [step]))).not.toEqual([]);
        const question = {type: 'find_move', fen: START, text: {en: 'Move?', uk: 'Move?'}, line: [{answers: ['e2e4']}]};
        expect(lessonProblems(sessionLesson('abc', 'Review', [step, question]))).toEqual([]);
    });
});
