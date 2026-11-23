// The big course (task 27.6): levels, branches, empty modules are visible only in the skeleton; auto-credit of modules by completed
// steps (task 6 of the 18.11 plan) and a manual "module passed" mark for modules without checkable steps.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {SupercoursePage} from '../SupercoursePage';
import {setToken} from '../../../services/authToken';

// All course modules are filled in; to check the "skeleton" mode, module T3.2 is replaced with an empty one, and E3.1 has steps in progress.
vi.mock('../../../content/supercourse', async (importOriginal) => {
    const original = await importOriginal<typeof import('../../../content/supercourse')>();
    return {
        ...original,
        COURSE: original.COURSE.map((m) => (m.code === 'T3.2' ? {...m, steps: []}
            : m.code === 'E3.1' ? {...m, steps: [], draft: m.steps} : m)),
    };
});

beforeEach(() => setToken('jwt'));
afterEach(() => {
    vi.unstubAllGlobals();
    setToken(null);
});

describe('The big course', () => {
    it('level 1, the skeleton and a module mark', async () => {
        const calls: [string, RequestInit | undefined][] = [];
        vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
            calls.push([String(url), init]);
            const body = init?.method === 'PUT' ? {lesson_id: 'course-o1-3', step: 0, steps_total: 1, completed: true}
                : String(url).includes('/course-progress') ? {
                    // Auto-credit: T1.1 — the lesson and three fork themes are done; for T1.4 only the lesson is done.
                    lessons: ['tactics-double-attack', 'tactics-skewer'], themes: ['fork', 'fork_knight', 'fork_pawn'],
                    trainers: [], exams: {}}
                : String(url).includes('/exam') ? {results: {level0: {estimate: 900}, level1: {estimate: 950}}}
                : String(url).includes('/puzzles/training') ? {window: 10, pass: 8, themes: [
                    {code: 'fork', section: 'A', stage: 1, recent: '', solved: 0, mastered: false, available: [30, 30, 30, 30], ready: true},
                    {code: 'pin', section: 'B', stage: 1, recent: '', solved: 0, mastered: false, available: [0, 0, 0, 0], ready: false}]}
                    : [{lesson_id: 'course-t1-2', step: 0, steps_total: 1, completed: true}];
            return {ok: true, json: async () => body} as Response;
        }));
        await act(async () => render(<MemoryRouter><SupercoursePage/></MemoryRouter>));
        expect(screen.getByTestId('course-module-T0.0')).toHaveTextContent('Board, pieces and captures');
        // The level 0 exam is passed (≥ 800), level 1 is not (< 1000).
        expect(screen.getByTestId('course-exam-target-0')).toHaveTextContent('Level passed');
        await act(async () => fireEvent.click(screen.getByTestId('course-level-1')));
        // T1.2 was marked manually earlier, T1.1 is closed by auto-credit, T1.4 is not (the theme is not passed).
        expect(screen.getByTestId('course-level-1')).toHaveTextContent('2/');
        expect(screen.getByTestId('course-step-done-T1.1-1')).toBeTruthy();
        expect(screen.getByTestId('course-step-done-T1.4-0')).toBeTruthy();
        expect(screen.queryByTestId('course-step-done-T1.4-1')).toBeNull();
        // Modules with checkable steps have no manual mark.
        expect(screen.queryByTestId('course-done-T1.1')).toBeNull();
        expect(screen.queryByTestId('course-done-T1.4')).toBeNull();
        await act(async () => fireEvent.click(screen.getByTestId('course-level-3')));
        expect(screen.queryByTestId('course-module-T3.2')).toBeNull();  // a module without steps is hidden
        expect(screen.queryByTestId('course-module-E3.1')).toBeNull();  // a draft is not visible to the player
        expect(screen.queryByTestId('course-coverage')).toBeNull();
        fireEvent.click(screen.getByTestId('course-skeleton'));
        expect(screen.getByTestId('course-module-T3.2')).toHaveTextContent('coming soon');
        // Skeleton for the author: steps in progress are marked, coverage by levels and branches.
        expect(screen.getByTestId('course-draft-E3.1')).toHaveTextContent('draft');
        expect(screen.getByTestId('course-module-E3.1')).not.toHaveTextContent('coming soon');
        expect(screen.getByTestId('coverage-3-E')).toHaveTextContent('1 draft');
        expect(screen.getByTestId('coverage-3-T')).toHaveTextContent('1 empty');
        await act(async () => fireEvent.click(screen.getByTestId('course-level-1')));
        expect(screen.getByTestId('course-exam-target-1')).toHaveTextContent('at least 1000');
        expect(screen.getByTestId('course-step-empty-pin')).toHaveTextContent('no puzzles yet');  // T1.2: the theme has no puzzles
        // A module made only of a repertoire has nothing to check — the player marks it themselves.
        await act(async () => fireEvent.click(screen.getByTestId('course-done-O1.3')));
        const put = calls.find(([, init]) => init?.method === 'PUT')!;
        expect(put[0]).toContain('/learn/progress/course-o1-3');
        expect(screen.queryByTestId('course-done-O1.3')).toBeNull();
    });

    it('a ?level=N&module=CODE link from the game summary opens the level and highlights the module', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, json: async () => []}) as unknown as Response));
        await act(async () => render(<MemoryRouter initialEntries={['/learn/course?level=1&module=T1.1']}><SupercoursePage/></MemoryRouter>));
        expect(screen.getByTestId('course-level-1').getAttribute('aria-selected')).toBe('true');
        expect(screen.getByTestId('course-module-T1.1').getAttribute('aria-current')).toBe('true');
        expect(screen.getByTestId('course-module-T1.2').getAttribute('aria-current')).toBeNull();
    });
});