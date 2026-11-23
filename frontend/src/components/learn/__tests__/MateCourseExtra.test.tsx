// Mate patterns course, extra paths: the best test result in the list, demonstration examples, "show the
// solution", a server refusal on a move and on submission, the end of the puzzle set, the result of the timed test and of the last puzzle.
// The network is a fetch stub by address; moves are two clicks, as in MateCourse.test.tsx.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setToken} from '../../../services/authToken';
import {MateConstructionPage, MateCoursePage, MateExamPage} from '../MateCourse';

const TASK = {
    id: 11, fen: '4r1k1/5ppp/8/8/8/8/3R1PPP/3R2K1 b - - 0 1', first_move: 'e8e2', rating: 1000,
    themes: ['back_rank_mate'], color: 'white', solution_length: 2, course: 'back_rank_mate', index: 0,
};
const ONE_TASK_OVERVIEW = {tasks: 1, exam_size: 1, exam_minutes: 10, constructions: [{code: 'back_rank_mate', available: 1}]};
const cell = (name: string) => document.querySelector(`[data-square="${name}"]`) as HTMLElement;

async function play(from: string, to: string) {
    await act(async () => {
        fireEvent.click(cell(from));
    });
    await act(async () => {
        fireEvent.click(cell(to));
    });
}

type Reply = { ok?: boolean; body: unknown };
type Route = [RegExp, (init?: RequestInit) => Reply | unknown];

/** A reply like {ok:false, body} is a server refusal; anything else is a successful reply with that body. */
function stub(routes: Route[]) {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({url: String(url), init});
        const route = routes.find(([pattern]) => pattern.test(String(url)));
        const raw = route ? route[1](init) : [];
        const failed = typeof raw === 'object' && raw !== null && 'ok' in raw && (raw as Reply).ok === false;
        return {
            ok: !failed, status: failed ? 500 : 200,
            json: async () => (failed ? (raw as Reply).body : raw),
        } as Response;
    }));
    return calls;
}

const waitForRook = () => waitFor(() => expect(cell('e2').querySelector('img')).not.toBeNull(), {timeout: 5000});

function renderAt(path: string) {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route path="/learn/mates" element={<MateCoursePage/>}/>
                <Route path="/learn/mates/exam" element={<MateExamPage/>}/>
                <Route path="/learn/mates/:theme" element={<MateConstructionPage/>}/>
            </Routes>
        </MemoryRouter>,
    );
}

beforeEach(() => setToken('jwt'));
afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
    setToken(null);
    vi.unstubAllGlobals();
});

describe('mate course: list and pattern', () => {
    it('the best result of the final test is visible in the list', async () => {
        stub([
            [/course\/mates$/, () => ONE_TASK_OVERVIEW],
            [/learn\/progress$/, () => [{lesson_id: 'mates-exam', step: 0, steps_total: 1, completed: true, exam_score: 7, exam_total: 10}]],
        ]);
        renderAt('/learn/mates');
        expect(await screen.findByTestId('mates-exam-link')).toBeInTheDocument();
        await waitFor(() => expect(screen.getByText(/7/, {selector: 'p'})).toBeInTheDocument());
    });

    it('a course overview failure — an error message', async () => {
        stub([[/course\/mates$/, () => ({ok: false, body: {detail: {code: 'internal_error'}}})]]);
        renderAt('/learn/mates');
        expect(await screen.findByRole('alert')).toBeInTheDocument();
    });

    it('demonstration examples are shown before the puzzles', async () => {
        stub([
            [/course\/mates$/, () => ONE_TASK_OVERVIEW],
            [/\/demo/, () => ({theme: 'back_rank_mate', examples: [{fen: '6k1/5ppp/8/8/8/8/8/3R2K1 w - - 0 1', moves: ['d1d8'], color: 'white'}]})],
        ]);
        renderAt('/learn/mates/back_rank_mate');
        expect(await screen.findByRole('heading', {level: 2})).toBeInTheDocument();
        expect(screen.getByTestId('mates-start')).toBeInTheDocument();
    });

    it('"Show solution" counts a failure and draws an arrow; the end of the set — the pattern summary', async () => {
        const calls = stub([
            [/course\/mates$/, () => ONE_TASK_OVERVIEW],
            [/\/demo/, () => ({theme: 'back_rank_mate', examples: []})],
            [/course\/mates\/back_rank_mate\/0$/, () => TASK],
            [/\/11\/give-up$/, () => ({solution: ['d2d8', 'e2e8', 'd8e8'], result: {solved: false}})],
            [/learn\/progress\//, () => ({})],
        ]);
        renderAt('/learn/mates/back_rank_mate');
        fireEvent.click(await screen.findByTestId('mates-start', {}, {timeout: 5000}));
        await waitForRook();
        fireEvent.click(await screen.findByRole('button', {name: 'Show solution'}));
        expect(await screen.findByTestId('course-failed')).toBeInTheDocument();
        expect(calls.some((c) => c.url.endsWith('/11/give-up'))).toBe(true);
        // The only puzzle of the set — the pattern is closed.
        expect(await screen.findByTestId('mates-finished')).toBeInTheDocument();
        const put = calls.find((c) => c.url.includes('/learn/progress/'))!;
        expect(JSON.parse(String(put.init?.body))).toMatchObject({completed: true, steps_total: 1});
    }, 20_000);

    it('a server refusal on "Show solution" and on a move — a message, the puzzle is not lost', async () => {
        stub([
            [/course\/mates$/, () => ONE_TASK_OVERVIEW],
            [/\/demo/, () => ({theme: 'back_rank_mate', examples: []})],
            [/course\/mates\/back_rank_mate\/0$/, () => TASK],
            [/\/11\/give-up$/, () => ({ok: false, body: {detail: {code: 'internal_error'}}})],
            [/\/11\/move$/, () => ({ok: false, body: {detail: {code: 'internal_error'}}})],
        ]);
        renderAt('/learn/mates/back_rank_mate');
        fireEvent.click(await screen.findByTestId('mates-start', {}, {timeout: 5000}));
        await waitForRook();
        await play('d2', 'd8');
        expect(await screen.findByRole('alert')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', {name: 'Show solution'}));
        await waitFor(() => expect(screen.getAllByRole('alert').length).toBeGreaterThan(0));
        expect(screen.queryByTestId('course-failed')).toBeNull();
    }, 20_000);
});

describe('mate course: final test', () => {
    it('a plan loading failure — an error message', async () => {
        stub([[/course\/mates\/exam$/, () => ({ok: false, body: {detail: {code: 'internal_error'}}})]]);
        renderAt('/learn/mates/exam');
        fireEvent.click(screen.getByTestId('mates-exam-start'));
        expect(await screen.findByRole('alert')).toBeInTheDocument();
    });

    it('time is up — the result is shown, the result is saved once', async () => {
        const calls = stub([
            // Two seconds instead of ten minutes: the deadline is computed by the client from the server reply.
            [/course\/mates\/exam$/, () => ({minutes: 0.02, tasks: [{theme: 'back_rank_mate', index: 0}]})],
            [/course\/mates\/back_rank_mate\/0$/, () => TASK],
            [/learn\/progress\//, () => ({})],
        ]);
        renderAt('/learn/mates/exam');
        fireEvent.click(screen.getByTestId('mates-exam-start'));
        expect(await screen.findByTestId('mates-exam-result', {}, {timeout: 6000})).toHaveTextContent('0');
        await waitFor(() => expect(calls.filter((c) => c.url.includes('/learn/progress/'))).toHaveLength(1));
        const put = calls.find((c) => c.url.includes('/learn/progress/'))!;
        expect(JSON.parse(String(put.init?.body))).toMatchObject({exam_score: 0, exam_total: 1, completed: true});
    }, 20_000);

    it('the last puzzle is solved — the result with points and a retake', async () => {
        stub([
            [/course\/mates\/exam$/, () => ({minutes: 10, tasks: [{theme: 'back_rank_mate', index: 0}]})],
            [/course\/mates\/back_rank_mate\/0$/, () => TASK],
            [/\/11\/move$/, (init) => (JSON.parse(String(init?.body)).move === 'd2d8'
                ? {correct: true, done: false, reply: 'e2e8', solution: null, result: null}
                : {correct: true, done: true, reply: null, solution: null, result: {solved: true}})],
            [/learn\/progress\//, () => ({})],
        ]);
        renderAt('/learn/mates/exam');
        fireEvent.click(screen.getByTestId('mates-exam-start'));
        await waitForRook();
        await play('d2', 'd8');
        await waitFor(() => expect(cell('e8').querySelector('img')?.getAttribute('alt')).toBe('br'), {timeout: 5000});
        await play('d8', 'e8');
        expect(await screen.findByTestId('mates-exam-result', {}, {timeout: 5000})).toHaveTextContent('1');
        expect(screen.getByTestId('mates-exam-start')).toBeInTheDocument();
    }, 20_000);
});
