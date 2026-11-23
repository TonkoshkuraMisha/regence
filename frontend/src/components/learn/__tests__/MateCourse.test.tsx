// Mate patterns course (task 14.6): the list, a pattern (explanation → puzzles), a timed test.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setToken} from '../../../services/authToken';
import {MateConstructionPage, MateCoursePage, MateExamPage, mateProgressId} from '../MateCourse';

const OVERVIEW = {
    tasks: 10, exam_size: 10, exam_minutes: 10,
    constructions: [{code: 'back_rank_mate', available: 2}, {code: 'pillsbury_mate', available: 0}],
};
// Black deflects the rook from the back rank; Rd8+ Re8 Rxe8#.
const TASK = {
    id: 11, fen: '4r1k1/5ppp/8/8/8/8/3R1PPP/3R2K1 b - - 0 1', first_move: 'e8e2', rating: 1000,
    themes: ['back_rank_mate'], color: 'white', solution_length: 2, course: 'back_rank_mate', index: 0,
};

const cell = (name: string) => document.querySelector(`[data-square="${name}"]`) as HTMLElement;

/**
 * A move with two clicks. Not by dragging: the board subscribes to the piece release from an effect, and under CI load
 * the release came before the subscription — the move was lost, the test occasionally failed.
 */
async function play(from: string, to: string) {
    await act(async () => {
        fireEvent.click(cell(from));
    });
    await act(async () => {
        fireEvent.click(cell(to));
    });
}

function stub(routes: [RegExp, (init?: RequestInit) => unknown][]) {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
        const route = routes.find(([pattern]) => pattern.test(String(url)));
        if (!route) return {ok: true, status: 200, json: async () => []} as Response;
        return {ok: true, status: 200, json: async () => route[1](init)} as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

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

describe('Mating patterns course', () => {
    it('list: patterns with puzzles — links, without puzzles — "soon"', async () => {
        stub([[/course\/mates$/, () => OVERVIEW]]);
        renderAt('/learn/mates');
        expect(await screen.findByTestId('mates-item-back_rank_mate')).toHaveAttribute('href', '/learn/mates/back_rank_mate');
        expect(screen.getByTestId('mates-item-pillsbury_mate')).toHaveTextContent('soon');
        expect(screen.getByTestId('mates-exam-link')).toHaveTextContent('Final test (10 min)');
    });

    it('pattern: an explanation, then the puzzle is solved on the server and progress is saved', async () => {
        const fetchMock = stub([
            [/course\/mates$/, () => OVERVIEW],
            [/\/demo/, () => ({theme: 'back_rank_mate', examples: []})],
            [/course\/mates\/back_rank_mate\/0$/, () => TASK],
            [/\/11\/move$/, (init) => {
                const move = JSON.parse(String(init?.body)).move;
                return move === 'd2d8'
                    ? {correct: true, done: false, reply: 'e2e8', solution: null, result: null}
                    : {correct: true, done: true, reply: null, solution: null, result: {solved: true}};
            }],
            [/learn\/progress\//, () => ({})],
        ]);
        renderAt('/learn/mates/back_rank_mate');
        expect(await screen.findByTestId('mates-explain', {}, {timeout: 5000})).toBeInTheDocument();
        fireEvent.click(await screen.findByTestId('mates-start', {}, {timeout: 5000}));
        expect(await screen.findByTestId('course-puzzle', {}, {timeout: 5000})).toBeInTheDocument();
        expect(screen.getByText('White to play and mate.')).toBeInTheDocument();
        // Moves only after the opponent's moves on the board: under load their delay stretches.
        const occupied = (sq: string) => waitFor(() => expect(cell(sq).querySelector('img')).not.toBeNull(), {timeout: 5000});
        await occupied('e2');
        await play('d2', 'd8');
        await occupied('e8');
        await play('d8', 'e8');
        expect(await screen.findByTestId('course-solved', {}, {timeout: 5000})).toBeInTheDocument();
        const put = (fetchMock.mock.calls as unknown as [string, RequestInit][]).find(([url]) => url.includes('/learn/progress/'))!;
        expect(put[0]).toContain(mateProgressId('back_rank_mate'));
        expect(JSON.parse(String(put[1].body))).toMatchObject({step: 1, steps_total: 2, completed: false});
        expect(screen.getByTestId('mates-next')).toBeInTheDocument();
    }, 20_000);  // under load (coverage measurement, CI) the default 5 s was not enough

    it('after a wrong move the board is free: the right move can be played by hand', async () => {
        stub([
            [/course\/mates$/, () => OVERVIEW],
            [/\/demo/, () => ({theme: 'back_rank_mate', examples: []})],
            [/course\/mates\/back_rank_mate\/0$/, () => TASK],
            [/\/11\/move$/, () => ({correct: false, done: true, reply: null, solution: ['d2d8', 'e2e8', 'd8e8'], result: {solved: false}})],
            [/learn\/progress\//, () => ({})],
        ]);
        renderAt('/learn/mates/back_rank_mate');
        fireEvent.click(await screen.findByTestId('mates-start', {}, {timeout: 5000}));
        await waitFor(() => expect(cell('e2').querySelector('img')).not.toBeNull(), {timeout: 5000});
        await play('d2', 'd5');
        expect(await screen.findByTestId('course-failed', {}, {timeout: 5000})).toBeInTheDocument();
        expect(screen.queryByTestId('explorer-controls')).toBeNull();
        await play('d2', 'd8');  // the solution move from the arrow — on the board
        expect(cell('d8').querySelector('img')?.getAttribute('alt')).toBe('wr');
        expect(screen.getByTestId('explorer-back')).not.toBeDisabled();
    }, 20_000);

    it('without login the course asks to log in', () => {
        setToken(null);
        stub([]);
        renderAt('/learn/mates');
        expect(screen.getByTestId('mates-login')).toBeInTheDocument();
    });

    it('test: after a mistake the puzzle does not change — a solution review and "Next puzzle" (owner feedback 18.11)', async () => {
        stub([
            [/course\/mates\/exam$/, () => ({minutes: 10, tasks: [{theme: 'back_rank_mate', index: 0}, {theme: 'back_rank_mate', index: 1}]})],
            [/course\/mates\/back_rank_mate\/0$/, () => TASK],
            [/course\/mates\/back_rank_mate\/1$/, () => ({...TASK, id: 12, index: 1})],
            [/\/11\/move$/, () => ({correct: false, done: true, reply: null, solution: ['d2d8', 'e2e8', 'd8e8'], result: {solved: false}})],
            [/learn\/progress\//, () => ({})],
        ]);
        // Fake clock: the auto-advance pause is fast-forwarded rather than waiting a real second. The move is made with two clicks:
        // dragging listens to the window from the board effect, and the release may come before the subscription — the move is lost
        // (this is how the test occasionally failed in CI; with a fake clock it repeats every time).
        vi.useFakeTimers({shouldAdvanceTime: true});
        renderAt('/learn/mates/exam');
        fireEvent.click(screen.getByTestId('mates-exam-start'));
        await waitFor(() => expect(cell('e2').querySelector('img')).not.toBeNull(), {timeout: 5000});
        fireEvent.click(cell('d2'));
        fireEvent.click(cell('d5'));
        expect(await screen.findByTestId('course-failed', {}, {timeout: 5000})).toBeInTheDocument();
        // Fast-forwarded past the former auto-advance (SOLVED_PAUSE_MS) — the puzzle is the same, the number is the same.
        await act(async () => {
            await vi.advanceTimersByTimeAsync(2000);
        });
        expect(screen.getByTestId('mates-exam-status')).toHaveTextContent('Puzzle 1 of 2');
        // Review: the refutation of the played move and the whole solution, step by step on the board.
        expect(screen.getByTestId('replay-line-played')).toHaveTextContent(/Refutation of .*d5/);
        fireEvent.click(screen.getByTestId('replay-line-solution'));
        fireEvent.click(screen.getByTestId('replay-forward'));
        expect(cell('d8').querySelector('img')?.getAttribute('alt')).toBe('wr');

        fireEvent.click(screen.getByTestId('mates-exam-next'));
        await waitFor(() => expect(screen.getByTestId('mates-exam-status')).toHaveTextContent('Puzzle 2 of 2'));
    }, 20_000);

    it('test: the time and the puzzle number', async () => {
        stub([
            [/course\/mates\/exam$/, () => ({minutes: 10, tasks: [{theme: 'back_rank_mate', index: 1}]})],
            [/course\/mates\/back_rank_mate\/1$/, () => ({...TASK, index: 1})],
        ]);
        // Each clock call is one millisecond later: that way in CI the start of the countdown and the deadline fell into different
        // milliseconds, and "10:01" was shown instead of "10:00". The countdown and the deadline must run from one moment.
        let clock = 1_700_000_000_000;
        vi.spyOn(Date, 'now').mockImplementation(() => clock++);
        renderAt('/learn/mates/exam');
        fireEvent.click(screen.getByTestId('mates-exam-start'));
        expect(await screen.findByTestId('mates-exam-status')).toHaveTextContent('10:00');
        expect(screen.getByTestId('mates-exam-status')).toHaveTextContent('Puzzle 1 of 1');
    });
});
