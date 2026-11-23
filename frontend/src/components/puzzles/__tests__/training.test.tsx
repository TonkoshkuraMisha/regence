// Motif training (task 13.4): a list of themes with progress, a theme card, a show on the board, training, sets.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import PuzzlesPage from '../PuzzlesPage';
import {DemoViewer} from '../TrainingPanel';
import {resetThemeRegistryCache} from '../../../services/themes';
import {setToken} from '../../../services/authToken';

const OVERVIEW = {window: 10, pass: 8, themes: [
    {code: 'fork', section: 'A', stage: 2, recent: '1101', solved: 14, mastered: false, available: [30, 40, 20, 10], ready: true},
    {code: 'fork_knight', section: 'A', stage: 1, recent: '', solved: 0, mastered: false, available: [12, 3, 0, 0], ready: false},
    {code: 'pin', section: 'B', stage: 4, recent: '', solved: 60, mastered: true, available: [25, 25, 20, 15], ready: true},
    {code: 'lucena', section: 'J', stage: 1, recent: '', solved: 0, mastered: false, available: [0, 0, 0, 0], ready: false},
]};
const PUZZLE = {
    id: 9, fen: 'r2q2k1/ppp3pp/8/4N3/8/8/PPP2PPP/R2QK2R b KQ - 0 1', first_move: 'g8h8', rating: 950,
    themes: ['fork', 'fork_knight'], color: 'white', solution_length: 1, stage: 1,
};

function stub(extra: (url: string) => unknown = () => null) {
    const calls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        calls.push(url);
        let body = extra(url);
        if (body === null) {
            if (url.includes('/training')) body = OVERVIEW;
            else if (url.includes('/demo')) body = {theme: 'fork', examples: [
                {fen: PUZZLE.fen, moves: ['g8h8', 'e5f7'], color: 'white'},
                {fen: PUZZLE.fen, moves: ['g8f8', 'e5d7'], color: 'white'},
            ]};
            else if (url.includes('/train')) body = PUZZLE;
            else if (url.includes('/themes')) body = {sections: ['A'], themes: []};
            else body = {rating: 1500, games: 0, streak: 0, best: {'3': 0, '5': 0}, history: []};
        }
        return {ok: true, status: 200, json: async () => body} as Response;
    }));
    return calls;
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

async function openThemes() {
    render(<MemoryRouter><PuzzlesPage/></MemoryRouter>);
    await act(async () => {
        fireEvent.click(await screen.findByTestId('puzzle-mode-themes'));
    });
    return screen.findByTestId('training-panel');
}

describe('"Motifs" mode', () => {
    it('themes by section with progress; a theme without puzzles is dimmed', async () => {
        stub();
        await openThemes();
        expect(screen.getByTestId('training-section-A').textContent).toContain('Double attack');
        expect(screen.getByTestId('training-theme-fork').textContent).toContain('stage 2 · 3/8');
        expect(screen.getByTestId('training-theme-pin').textContent).toContain('mastered');
        expect(screen.getByTestId('training-theme-lucena').className).toContain('opacity-50');
    });

    it('theme card: an explanation, a show on the board, training with progress', async () => {
        const calls = stub((url) => (url.includes('/move')
            ? {correct: true, done: true, reply: null, solution: null, result: {
                solved: true, rating_before: 1500, rating_after: 1508, delta: 8, streak: 1, themes: ['fork'], run: null,
                training: {theme: 'fork', stage: 2, recent: '11011', mastered: false, advanced: false, window: 10, pass: 8},
            }}
            : null));
        await openThemes();
        fireEvent.click(screen.getByTestId('training-theme-fork'));
        const card = screen.getByTestId('theme-card');
        expect(card.textContent).toContain('Fork');
        expect(card.textContent).toContain('A fork is when one piece attacks two of the opponent');
        expect(card.textContent).toContain('Stage 2 — practice: solved cleanly 3 of the last 10, 8 needed to move on.');

        await act(async () => {
            fireEvent.click(screen.getByTestId('theme-demo'));
        });
        expect(screen.getByTestId('demo-viewer')).toBeTruthy();

        await act(async () => {
            fireEvent.click(screen.getByTestId('theme-train'));
        });
        expect(calls.some((u) => u.endsWith('/train?theme=fork'))).toBe(true);
        expect(screen.getByTestId('training-target').textContent).toContain('Fork');
        expect(screen.getByTestId('puzzle-info').textContent).toContain('stage 1');
        await act(async () => {
            await vi.advanceTimersByTimeAsync(600);
        });
        await act(async () => {
            fireEvent.click(document.querySelector('[data-square="e5"]') as HTMLElement);
        });
        await act(async () => {
            fireEvent.click(document.querySelector('[data-square="f7"]') as HTMLElement);
        });
        expect(await screen.findByTestId('training-progress')).toHaveTextContent('Stage 2: solved cleanly 4 of the last 10 (need 8).');

        await act(async () => {
            fireEvent.click(screen.getByTestId('training-back'));
        });
        expect(await screen.findByTestId('training-panel')).toBeTruthy();
    });

    it('the mixed set "without the theme name" hides the themes until the solution ends', async () => {
        const calls = stub((url) => (url.includes('/train?') ? {...PUZZLE, themes: [], stage: null} : null));
        await openThemes();
        fireEvent.click(screen.getByTestId('training-blind'));
        await act(async () => {
            fireEvent.click(screen.getByTestId('training-mixed-A'));
        });
        expect(calls.some((u) => u.endsWith('/train?section=A&blind=true'))).toBe(true);
        expect(screen.getByTestId('training-target').textContent).toContain('Mixed: Double attack · Without the theme name');
        expect(screen.queryByTestId('puzzle-themes')).toBeNull();
    });

    it('the puzzle goal (27.8) goes into the training request', async () => {
        const calls = stub((url) => (url.includes('/train?') ? {...PUZZLE, stage: null} : null));
        await openThemes();
        fireEvent.change(screen.getByTestId('training-goal'), {target: {value: 'mate'}});
        await act(async () => {
            fireEvent.click(screen.getByTestId('training-mixed-A'));
        });
        expect(calls.some((u) => u.endsWith('/train?section=A&goal=mate'))).toBe(true);
    });

    it('moving to the next stage and mastering the theme', async () => {
        stub((url) => (url.includes('/move')
            ? {correct: true, done: true, reply: null, solution: null, result: {
                solved: true, rating_before: 1500, rating_after: 1508, delta: 8, streak: 1, themes: [], run: null,
                training: {theme: 'fork', stage: 3, recent: '', mastered: false, advanced: true, window: 10, pass: 8},
            }}
            : null));
        await openThemes();
        fireEvent.click(screen.getByTestId('training-theme-fork'));
        await act(async () => {
            fireEvent.click(screen.getByTestId('theme-train'));
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(600);
        });
        await act(async () => {
            fireEvent.click(document.querySelector('[data-square="e5"]') as HTMLElement);
        });
        await act(async () => {
            fireEvent.click(document.querySelector('[data-square="f7"]') as HTMLElement);
        });
        await waitFor(() => expect(screen.getByTestId('training-progress').textContent).toBe('Stage passed! Now stage 3.'));
    });
});

describe('DemoViewer', () => {
    it('moves step by step and switching examples', () => {
        render(<DemoViewer examples={[
            {fen: PUZZLE.fen, moves: ['g8h8', 'e5f7'], color: 'white'},
            {fen: PUZZLE.fen, moves: ['g8f8'], color: 'white'},
        ]}/>);
        expect(screen.getByTestId('demo-caption').textContent).toBe('The starting position · move 0 of 2');
        fireEvent.click(screen.getByTestId('demo-next'));
        expect(screen.getByTestId('demo-caption').textContent).toContain('The opponent\'s move');
        fireEvent.click(screen.getByTestId('demo-next'));
        expect(screen.getByTestId('demo-caption').textContent).toContain('The solution move');
        expect(document.querySelector('[data-square="f7"] img')?.getAttribute('alt')).toBe('wn');
        expect((screen.getByTestId('demo-next') as HTMLButtonElement).disabled).toBe(true);
        fireEvent.click(screen.getByTestId('demo-prev'));
        expect(screen.getByTestId('demo-caption').textContent).toContain('move 1 of 2');
        fireEvent.click(screen.getByTestId('demo-other'));
        expect(screen.getByTestId('demo-caption').textContent).toBe('The starting position · move 0 of 1');
    });
});
