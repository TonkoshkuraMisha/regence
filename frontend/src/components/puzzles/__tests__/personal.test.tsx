// "My mistakes" (task 13.5): a position from the player's game, an answer with one move, repetition at intervals.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import PuzzlesPage from '../PuzzlesPage';
import {resetThemeRegistryCache} from '../../../services/themes';
import {setToken} from '../../../services/authToken';

// After 3. Qh5 Black played 3...Nf6?? — the strong move was 3...g6.
const VIEW = {
    id: 3, game_id: 41, ply: 6, fen: 'r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3',
    previous_move: 'd1h5', color: 'black', themes: [], attempts: 0, solved_streak: 0,
    opponent: 'morphy', opponent_is_bot: true, played_at: '2026-11-10T18:30:00+00:00',
};
const SUMMARY = {due: 2, active: 3, mastered: 1, next_due_at: null};
const tomorrow = () => new Date(Date.now() + 86_400_000).toISOString();

function stub(answer: unknown, nextAvailable = true) {
    const calls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        calls.push(url);
        if (url.endsWith('/personal/next') && !nextAvailable) {
            return {ok: false, status: 404, json: async () => ({detail: {code: 'no_puzzles_available', params: {}}})} as Response;
        }
        const body = url.endsWith('/personal') ? SUMMARY
            : url.endsWith('/personal/next') ? VIEW
                : url.includes('/answer') ? answer
                    : url.includes('/themes') ? {sections: [], themes: []}
                        : {rating: 1500, games: 0, streak: 0, best: {'3': 0, '5': 0}, history: []};
        return {ok: true, status: 200, json: async () => body} as Response;
    }));
    return calls;
}

function Probe() {
    return <div data-testid="location">{useLocation().pathname}</div>;
}

async function open() {
    render(
        <MemoryRouter initialEntries={['/puzzles']}>
            <Routes>
                <Route path="/puzzles" element={<PuzzlesPage/>}/>
                <Route path="/game/:id" element={<Probe/>}/>
            </Routes>
        </MemoryRouter>,
    );
    await act(async () => {
        fireEvent.click(await screen.findByTestId('puzzle-mode-personal'));
    });
}

const square = (name: string) => document.querySelector(`[data-square="${name}"]`) as HTMLElement;

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

describe('My mistakes', () => {
    it('a position from the game: the right move, a repeat in 3 days, what was played', async () => {
        stub({correct: true, solution: 'g7g6', played: 'g8f6', done: false, solved_streak: 1,
              next_due_at: new Date(Date.now() + 3 * 86_400_000).toISOString()});
        await open();
        expect(screen.getByTestId('personal-summary').textContent).toBe('To review now: 2 · in progress: 3 · mastered: 1');
        expect(screen.getByTestId('puzzle-status').textContent).toContain('This happened in your game');
        // The opponent's move from the game is highlighted, the board is for Black.
        const order = Array.from(document.querySelectorAll('[data-square]')).map((el) => el.getAttribute('data-square'));
        expect(order[0]).toBe('h1');
        await act(async () => {
            fireEvent.click(square('g7'));
        });
        await act(async () => {
            fireEvent.click(square('g6'));
        });
        expect(await screen.findByTestId('personal-result')).toHaveTextContent('Correct! We will come back to it in 3 d.');
        expect(screen.getByTestId('personal-played').textContent).toBe('In the game you played 3… ♞f6; the strong move was 3… g6.');
        // Where the mistake is from, and a review on the board (task B.3).
        expect(screen.getByTestId('personal-from').textContent).toBe('Game against Morphy, 10 Nov 2026');
        fireEvent.click(screen.getByTestId('replay-line-played'));
        expect(screen.getByTestId('replay-step').textContent).toBe('Move 0 of 1');
        fireEvent.click(screen.getByTestId('replay-forward'));
        expect(square('f6').querySelector('img')?.getAttribute('alt')).toBe('bn');
        fireEvent.click(screen.getByTestId('replay-line-best'));
        expect(square('g8').querySelector('img')?.getAttribute('alt')).toBe('bn');
        await act(async () => {
            fireEvent.click(screen.getByTestId('personal-open-game'));
        });
        expect(screen.getByTestId('location').textContent).toBe('/game/41');
    });

    it('a wrong move: the right one is shown on the board, a repeat tomorrow', async () => {
        stub({correct: false, solution: 'g7g6', played: 'g8f6', done: false, solved_streak: 0, next_due_at: tomorrow()});
        await open();
        await act(async () => {
            fireEvent.click(square('d8'));
        });
        await act(async () => {
            fireEvent.click(square('e7'));
        });
        expect(await screen.findByTestId('personal-result')).toHaveTextContent('Not this move. We will come back to it in 1 d.');
        await act(async () => {
            await vi.advanceTimersByTimeAsync(2000);
        });
        expect(square('g6').querySelector('img')?.getAttribute('alt')).toBe('bp');
        expect(square('d8').querySelector('img')?.getAttribute('alt')).toBe('bq');
    });

    it('mastered after two solutions in a row; empty — when the next one is', async () => {
        stub({correct: true, solution: 'g7g6', played: 'g8f6', done: true, solved_streak: 2, next_due_at: null});
        await open();
        await act(async () => {
            fireEvent.click(square('g7'));
        });
        await act(async () => {
            fireEvent.click(square('g6'));
        });
        expect(await screen.findByTestId('personal-result')).toHaveTextContent('Solved twice in a row — mastered.');
    });

    it('nothing to review', async () => {
        stub(null, false);
        await open();
        expect(await screen.findByTestId('personal-empty')).toHaveTextContent('All puzzles for today are done');
    });
});
