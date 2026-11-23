// Training programmes (task 22.3): a list with progress, weeks and sessions, the "session done" mark.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ProgramPage, ProgramsPage} from '../ProgramsPage';
import {setToken} from '../../services/authToken';

function stub(progress: unknown[]) {
    const calls: [string, RequestInit | undefined][] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
        calls.push([String(url), init]);
        const body = init?.method === 'PUT' ? {lesson_id: 'program-to_1200', step: 2, steps_total: 40, completed: false} : progress;
        return {ok: true, json: async () => body} as Response;
    }));
    return calls;
}

const page = (path: string) => render(
    <MemoryRouter initialEntries={[path]}>
        <Routes>
            <Route path="/programs" element={<ProgramsPage/>}/>
            <Route path="/programs/:programId" element={<ProgramPage/>}/>
        </Routes>
    </MemoryRouter>,
);

beforeEach(() => setToken('jwt'));
afterEach(() => {
    vi.unstubAllGlobals();
    setToken(null);
});

describe('training programmes', () => {
    it('a list with progress', async () => {
        stub([{lesson_id: 'program-club', step: 4, steps_total: 40, completed: false}]);
        await act(async () => page('/programs'));
        expect(screen.getByTestId('program-club')).toHaveTextContent('Sessions done: 5 of 40');
        expect(screen.getByTestId('program-first_steps')).toHaveTextContent('Sessions done: 0 of 40');
    });

    it('the sessions of a programme and the mark of the current one', async () => {
        const calls = stub([{lesson_id: 'program-to_1200', step: 1, steps_total: 40, completed: false}]);
        await act(async () => page('/programs/to_1200'));
        expect(screen.getByTestId('program-progress')).toHaveTextContent('Sessions done: 2 of 40');
        expect(screen.getByTestId('session-0')).toHaveTextContent('Double attack');
        expect(screen.getByTestId('session-2')).toHaveTextContent('Trainer');
        await act(async () => fireEvent.click(screen.getByTestId('session-done')));
        const put = calls.find(([, init]) => init?.method === 'PUT')!;
        expect(put[0]).toContain('/learn/progress/program-to_1200');
        expect(JSON.parse(String(put[1]!.body))).toEqual({step: 2, steps_total: 40, completed: false});
        expect(screen.getByTestId('program-progress')).toHaveTextContent('Sessions done: 3 of 40');
    });

    it('auto-credit: consecutive completed sessions are counted by themselves, ticks at the exercises (owner plan 18.11)', async () => {
        const calls: [string, RequestInit | undefined][] = [];
        vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
            calls.push([String(url), init]);
            const body = String(url).includes('/learn/course-progress')
                ? {lessons: ['tactics-double-attack'], themes: ['fork', 'double_attack'], trainers: ['double_strike'], exams: {}}
                : init?.method === 'PUT' ? {} : [];
            return {ok: true, json: async () => body} as Response;
        }));
        await act(async () => page('/programs/to_1200'));
        // Sessions 1–3 are closed by facts, the fourth (warm-up) is not checked — the count stopped on it.
        expect(screen.getByTestId('program-progress')).toHaveTextContent('Sessions done: 3 of 40');
        const put = calls.find(([, init]) => init?.method === 'PUT')!;
        expect(JSON.parse(String(put[1]!.body))).toEqual({step: 2, steps_total: 40, completed: false});
        expect(screen.getByTestId('activity-done-0-0')).toBeInTheDocument();
        expect(screen.getByTestId('session-3')).toContainElement(screen.getByTestId('session-done'));
    });

    it('no such programme', () => {
        stub([]);
        page('/programs/nope');
        expect(screen.getByText('There is no such programme.')).toBeInTheDocument();
    });
});
