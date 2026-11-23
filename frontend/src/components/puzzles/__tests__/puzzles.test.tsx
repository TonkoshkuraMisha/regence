// The puzzle page (task 13.3): solving with a server check, a mistake and showing the solution, a hint, the timed mode.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import PuzzlesPage, {solutionSan} from '../PuzzlesPage';
import {PuzzleBoard} from '../PuzzleBoard';
import {resetThemeRegistryCache} from '../../../services/themes';
import {setToken} from '../../../services/authToken';

// Black deflects the rook: ...Re2, then Rd8+ Re8 Rxe8#.
const PUZZLE = {
    id: 7, fen: '4r1k1/5ppp/8/8/8/8/3R1PPP/3R2K1 b - - 0 1', first_move: 'e8e2', rating: 1480,
    themes: ['back_rank_mate', 'mate_in_2'], color: 'white', solution_length: 2,
};
const PROFILE = {rating: 1500, games: 3, streak: 1, best: {'3': 4, '5': 0}, history: [
    {puzzle_id: 1, puzzle_rating: 1400, solved: true, hints_used: 0, rating_after: 1510, created_at: null},
    {puzzle_id: 2, puzzle_rating: 1600, solved: false, hints_used: 0, rating_after: 1500, created_at: null},
]};
const REGISTRY = {sections: ['F'], themes: [
    {code: 'back_rank_mate', section: 'F', parent: null, sources: ['D', 'L'], minimums: [25, 25, 20, 15]},
]};
const RESULT = {solved: true, rating_before: 1500, rating_after: 1512, delta: 12, streak: 2, themes: [], run: null};

type Handler = (url: string, init?: RequestInit) => unknown;

function stub(handler: Handler) {
    const calls: { url: string; body: unknown }[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = String(input);
        calls.push({url, body: init?.body ? JSON.parse(String(init.body)) : null});
        const body = url.includes('/themes') ? REGISTRY : url.endsWith('/puzzles/me') ? PROFILE : handler(url, init);
        return {ok: true, status: 200, json: async () => body} as Response;
    }));
    return calls;
}

function LocationProbe() {
    const location = useLocation();
    return <div data-testid="location">{JSON.stringify({path: location.pathname, state: location.state})}</div>;
}

function renderPage() {
    return render(
        <MemoryRouter initialEntries={['/puzzles']}>
            <Routes>
                <Route path="/puzzles" element={<PuzzlesPage/>}/>
                <Route path="/" element={<LocationProbe/>}/>
            </Routes>
        </MemoryRouter>,
    );
}

const square = (name: string) => document.querySelector(`[data-square="${name}"]`) as HTMLElement;

async function play(from: string, to: string) {
    await act(async () => {
        fireEvent.click(square(from));
    });
    await act(async () => {
        fireEvent.click(square(to));
    });
}

beforeEach(() => {
    setToken('jwt');
    vi.useFakeTimers({shouldAdvanceTime: true});
    resetThemeRegistryCache();
});
afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    localStorage.clear();
});

async function start() {
    renderPage();
    await act(async () => {
        fireEvent.click(await screen.findByTestId('puzzle-next'));
    });
    await act(async () => {
        await vi.advanceTimersByTimeAsync(600);
    });
}

describe('PuzzlesPage', () => {
    it('before the start — mode cards by group instead of an empty board; with a puzzle — tabs (owner plan 18.11)', async () => {
        stub((url) => (url.includes('/daily') || url.includes('/next') ? PUZZLE : {}));
        renderPage();
        const intro = await screen.findByTestId('puzzle-mode-rated');
        expect(intro).toHaveTextContent('By rating');
        expect(intro).toHaveTextContent('a solved one raises it');
        expect(intro).toContainElement(screen.getByTestId('puzzle-next'));  // "Start" — in the card of the chosen mode
        expect(document.querySelector('[data-square]')).toBeNull();
        expect(screen.queryByRole('tablist')).toBeNull();  // the tabs do not repeat the cards
        // The other modes are cards with a description; a click chooses the mode.
        expect(screen.getByTestId('puzzle-mode-timed')).toHaveTextContent('three mistakes');

        fireEvent.click(screen.getByTestId('puzzle-mode-daily'));
        await waitFor(() => expect(screen.getByTestId('puzzle-mode-info')).toHaveTextContent('One puzzle a day'));
        expect(screen.getAllByRole('tablist').map((list) => list.getAttribute('aria-label')))
            .toEqual(['Solve', 'Train', 'Your games']);
        expect(screen.getByTestId('puzzle-mode-daily')).toHaveAttribute('aria-selected', 'true');

        await act(async () => {
            await vi.advanceTimersByTimeAsync(600);
        });
        expect(screen.queryByTestId('puzzle-mode-cards')).toBeNull();
        expect(square('e2').querySelector('img')?.getAttribute('alt')).toBe('br');
    });

    it('the opponent\'s move, a server check of every move, the answer and the result', async () => {
        const calls = stub((url, init) => {
            if (url.includes('/next')) return PUZZLE;
            const move = JSON.parse(String(init?.body)).move;
            return move === 'd2d8'
                ? {correct: true, done: false, reply: 'e2e8', solution: null, result: null}
                : {correct: true, done: true, reply: null, solution: null, result: RESULT};
        });
        await start();
        expect(screen.getByTestId('puzzle-profile').textContent).toContain('1500');
        expect(square('e2').querySelector('img')?.getAttribute('alt')).toBe('br');
        expect(screen.getByTestId('puzzle-status').textContent).toContain('White');

        await play('d2', 'd8');
        await act(async () => {
            await vi.advanceTimersByTimeAsync(500);
        });
        expect(square('e8').querySelector('img')?.getAttribute('alt')).toBe('br');
        await play('d8', 'e8');

        expect(await screen.findByTestId('puzzle-outcome')).toHaveTextContent('Solved! Rating +12');
        expect(calls.filter((c) => c.url.includes('/move')).map((c) => c.body)).toEqual([{move: 'd2d8'}, {move: 'd8e8'}]);
        expect(screen.getByTestId('puzzle-themes').textContent).toContain('Back-rank mate');
        expect(screen.getByTestId('puzzle-chart')).toBeTruthy();
        // The rating scale: the bounds are rounded to tens with a margin above and below the points 1500 and 1510.
        expect(screen.getByTestId('puzzle-chart-scale').textContent).toBe('152015051490');
    });

    it('after the puzzle the board is free: the position can be played on and returned (owner decision 18.11)', async () => {
        stub((url) => (url.includes('/next') ? PUZZLE : {correct: true, done: true, reply: null, solution: null, result: RESULT}));
        await start();
        await play('d2', 'd8');
        expect(await screen.findByTestId('puzzle-outcome')).toHaveTextContent('Solved!');
        expect(screen.queryByTestId('explorer-controls')).toBeNull();
        // The puzzle is finished — a move for Black (covering with the rook) is made right on the board and starts the review.
        await play('e2', 'e8');
        expect(square('e8').querySelector('img')?.getAttribute('alt')).toBe('br');
        expect(screen.getByTestId('explorer-back')).not.toBeDisabled();
        await act(async () => {
            fireEvent.click(screen.getByTestId('explorer-reset'));
        });
        expect(square('e2').querySelector('img')?.getAttribute('alt')).toBe('br');
    });

    it('a wrong move: a mark, the result, the solution is shown on the board', async () => {
        stub((url) => url.includes('/next') ? PUZZLE : {
            correct: false, done: true, reply: null, solution: ['d2d8', 'e2e8', 'd8e8'],
            result: {...RESULT, solved: false, delta: -14, rating_after: 1486, streak: 0},
        });
        await start();
        await play('d2', 'd5');
        expect(await screen.findByTestId('puzzle-mark-wrong')).toBeTruthy();
        expect(screen.getByTestId('puzzle-outcome')).toHaveTextContent('Not this time. Rating -14');
        expect(screen.getByTestId('puzzle-solution').textContent).toBe('Solution: 2. ♖d8+ ♜e8 3. ♖xe8#');
        await act(async () => {
            await vi.advanceTimersByTimeAsync(3000);
        });
        expect(square('e8').querySelector('img')?.getAttribute('alt')).toBe('wr');
    });

    it('the hint highlights a piece, then a move; "Review with the mentor" passes the position on', async () => {
        let hints = 0;
        stub((url) => {
            if (url.includes('/next')) return PUZZLE;
            if (url.includes('/hint')) {
                hints += 1;
                return {from: 'd2', to: hints > 1 ? 'd8' : null, hints_used: hints};
            }
            return {solution: ['d2d8', 'e2e8', 'd8e8'], result: {...RESULT, solved: false, delta: -14}};
        });
        await start();
        await act(async () => {
            fireEvent.click(screen.getByTestId('puzzle-hint'));
        });
        expect(screen.getByTestId('puzzle-hint-d2')).toBeTruthy();
        expect(screen.getByTestId('puzzle-hint-text').textContent).toContain('highlighted piece');
        await act(async () => {
            fireEvent.click(screen.getByTestId('puzzle-hint'));
        });
        expect(screen.getByTestId('puzzle-hint-d8')).toBeTruthy();
        expect((screen.getByTestId('puzzle-hint') as HTMLButtonElement).disabled).toBe(true);

        await act(async () => {
            fireEvent.click(screen.getByTestId('puzzle-give-up'));
        });
        await act(async () => {
            fireEvent.click(screen.getByTestId('puzzle-analyze'));
        });
        const location = JSON.parse(screen.getByTestId('location').textContent ?? '{}');
        expect(location.path).toBe('/');
        expect(location.state.analyzeFen).toBe('6k1/5ppp/8/8/8/8/3RrPPP/3R2K1 w - - 1 2');
    });

    it('the theme choice goes into the request; the daily puzzle', async () => {
        const calls = stub((url) => ({...PUZZLE, daily: url.includes('/daily') || undefined}));
        renderPage();
        const select = await screen.findByTestId('puzzle-theme');
        await waitFor(() => expect(select.querySelectorAll('option').length).toBe(2));
        fireEvent.change(select, {target: {value: 'back_rank_mate'}});
        await act(async () => {
            fireEvent.click(screen.getByTestId('puzzle-next'));
        });
        expect(calls.some((c) => c.url.endsWith('/next?theme=back_rank_mate'))).toBe(true);
        await act(async () => {
            fireEvent.click(screen.getByTestId('puzzle-mode-daily'));
        });
        await waitFor(() => expect(screen.getByTestId('puzzle-info').textContent).toContain('puzzle of the day'));
    });

    it('"Save the game" (27.9): puzzles with a "draw" goal without a theme choice', async () => {
        const calls = stub(() => ({...PUZZLE, goal: 'draw', themes: ['perpetual_check']}));
        renderPage();
        await screen.findByTestId('puzzle-theme');
        await act(async () => {
            fireEvent.click(screen.getByTestId('puzzle-mode-save'));
        });
        await waitFor(() => expect(calls.some((c) => c.url.endsWith('/train?goal=draw'))).toBe(true));
        expect(screen.getByTestId('save-intro')).toHaveTextContent('Find the draw');
        await waitFor(() => expect(screen.getByTestId('puzzle-next')).not.toBeDisabled());  // the opponent's move is played
        await act(async () => {
            fireEvent.click(screen.getByTestId('puzzle-next'));
        });
        expect(calls.filter((c) => c.url.endsWith('/train?goal=draw')).length).toBe(2);
    });

    it('timed mode: a timer, the score from the server, a record', async () => {
        const run = {run_id: 'r1', minutes: 3, solved: 0, mistakes: 0, seconds_left: 180, over: false};
        const calls = stub((url) => {
            if (url.includes('/timed/leaders')) {
                const me = {place: 25, username: 'TestPlayer', score: 2, me: true};
                return {rows: [{place: 1, username: 'Anna', score: 9, me: false}], me};
            }
            if (url.includes('/timed/start')) return run;
            if (url.includes('/timed/next')) return {...PUZZLE, run};
            if (url.includes('/timed/finish')) return {score: 1, mistakes: 0, minutes: 3, best: 4, new_record: false};
            return {correct: true, done: true, reply: null, solution: null,
                    result: {...RESULT, delta: 0, run: {...run, solved: 1, over: true}}};
        });
        renderPage();
        await act(async () => {
            fireEvent.click(await screen.findByTestId('puzzle-mode-timed'));
        });
        expect(screen.getByTestId('puzzle-timed-setup').textContent).toContain('record: 4');
        // The leaderboard: the top and one's own row below the top.
        expect(await screen.findByText('Anna')).toBeInTheDocument();
        expect(screen.getAllByTestId('leader-row').map((row) => row.textContent)).toEqual(['1Anna9', '25TestPlayer2']);
        await act(async () => {
            fireEvent.click(screen.getByTestId('puzzle-timed-3'));
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(600);
        });
        expect(screen.getByTestId('puzzle-run').textContent).toContain('3:00'.slice(0, 1));
        // Themes are not hinted in the run.
        expect(screen.queryByTestId('puzzle-themes')).toBeNull();
        await play('d2', 'd8');
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1000);
        });
        expect(await screen.findByTestId('puzzle-timed-result')).toHaveTextContent('Run over: 1 solved, record 4');
        expect(calls.some((c) => c.url.includes('/timed/finish'))).toBe(true);
    });

    it('a server error is shown', async () => {
        vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
            const url = String(input);
            if (url.includes('/next')) {
                return {ok: false, status: 404, json: async () => ({detail: {code: 'no_puzzles_available', params: {}}})} as Response;
            }
            return {ok: true, status: 200, json: async () => (url.includes('/themes') ? REGISTRY : PROFILE)} as Response;
        }));
        renderPage();
        await act(async () => {
            fireEvent.click(await screen.findByTestId('puzzle-next'));
        });
        expect(await screen.findByRole('alert')).toHaveTextContent('No suitable puzzles right now');
    });
});

describe('PuzzleBoard', () => {
    it('promotion — a piece choice', () => {
        const onMove = vi.fn();
        render(<PuzzleBoard fen="8/P7/8/8/8/8/k7/4K3 w - - 0 1" orientation="white" interactive onMove={onMove}/>);
        fireEvent.click(square('a7'));
        fireEvent.click(square('a8'));
        fireEvent.click(screen.getByTestId('puzzle-promote-n'));
        expect(onMove).toHaveBeenCalledWith('a7a8n');
    });

    it('not your turn and a non-interactive board — no moves', () => {
        const onMove = vi.fn();
        render(<PuzzleBoard fen="8/P7/8/8/8/8/k7/4K3 w - - 0 1" orientation="black" interactive={false} onMove={onMove}/>);
        fireEvent.click(square('a7'));
        fireEvent.click(square('a8'));
        expect(onMove).not.toHaveBeenCalled();
        const order = Array.from(document.querySelectorAll('[data-square]')).map((el) => el.getAttribute('data-square'));
        expect(order[0]).toBe('h1');
    });
});

describe('solutionSan', () => {
    it('move numbering from White and from Black', () => {
        expect(solutionSan('4r1k1/5ppp/8/8/8/8/3R1PPP/3R2K1 b - - 0 1', ['e8e2', 'd2d8'])).toBe('1… ♜e2 2. ♖d8+');
        expect(solutionSan('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', ['e2e4', 'e7e5', 'g1f3']))
            .toBe('1. e4 e5 2. ♘f3');
        expect(solutionSan('8/P7/8/8/8/8/k7/4K3 w - - 0 1', ['a7a8n'])).toBe('1. a8=♘');
    });
});

describe('"Candidates" (27.9)', () => {
    async function startWithCandidates() {
        renderPage();
        fireEvent.click(await screen.findByTestId('candidates-toggle'));
        await act(async () => {
            fireEvent.click(await screen.findByTestId('puzzle-next'));
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(600);
        });
    }

    it('clicks mark candidates and do not move; the right move among them — marked', async () => {
        const calls = stub((url, init) => {
            if (url.includes('/next')) return PUZZLE;
            const move = JSON.parse(String(init?.body)).move;
            return move === 'd2d8'
                ? {correct: true, done: false, reply: 'e2e8', solution: null, result: null}
                : {correct: true, done: true, reply: null, solution: null, result: RESULT};
        });
        await startWithCandidates();
        expect(screen.getByTestId('candidates-ready')).toBeDisabled();
        await play('d2', 'd8');
        await play('g1', 'f1');
        expect(calls.some((c) => c.url.includes('/move'))).toBe(false);  // these are marks, not moves
        expect(screen.getByTestId('candidates-panel')).toHaveTextContent('2 marked');
        await act(async () => fireEvent.click(screen.getByTestId('candidates-ready')));
        await play('d2', 'd8');
        await act(async () => {
            await vi.advanceTimersByTimeAsync(500);
        });
        await play('d8', 'e8');
        expect(await screen.findByTestId('candidates-verdict')).toHaveTextContent('was among your candidates');
    });

    it('a wrong first move: the best move is taken from the solution, it was not among the candidates', async () => {
        stub((url) => (url.includes('/next') ? PUZZLE
            : {correct: false, done: true, reply: null, solution: ['d2d8', 'e2e8', 'd8e8'], result: {...RESULT, solved: false, delta: -10}}));
        await startWithCandidates();
        await play('g1', 'f1');
        await play('h2', 'h3');
        await act(async () => fireEvent.click(screen.getByTestId('candidates-ready')));
        await play('h2', 'h3');
        expect(await screen.findByTestId('candidates-verdict')).toHaveTextContent('was not among your candidates');
    });
});
