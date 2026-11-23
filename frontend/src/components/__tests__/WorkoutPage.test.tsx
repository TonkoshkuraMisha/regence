// The daily workout (task 22.2): a plan with marks and a streak, jumps to puzzles by theme, the trainer, openings, mistakes.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {WorkoutPage} from '../WorkoutPage';
import type {WorkoutPlan} from '../../services/workout';
import {setToken} from '../../services/authToken';

const WEEK = {
    since: '2026-11-15T00:00:00Z', games: {total: 5, wins: 3, draws: 1, losses: 1, rating_delta: 14},
    puzzles: {attempts: 12, solved: 9}, days_active: 4, streak: 3, advice: 'keep_going',
};
const reply = (url: unknown) => ({ok: true, json: async () => (String(url).endsWith('/workout/week') ? WEEK : PLAN)}) as Response;

const PLAN: WorkoutPlan = {
    date: '2026-11-16', complete: false, streak: 3,
    steps: [
        {kind: 'puzzles', themes: ['pin', 'fork'], target: 5, done: 2},
        {kind: 'trainer', trainer: 'coord_name', done: true},
        {kind: 'repertoire', due: 4, repertoire_id: 7, done: false},
        {kind: 'mistake', due: 0, done: true},
    ],
};

function PuzzlesProbe() {
    const location = useLocation();
    return <p data-testid="probe">{JSON.stringify(location.state)}</p>;
}

const page = () => render(
    <MemoryRouter initialEntries={['/workout']}>
        <Routes>
            <Route path="/workout" element={<WorkoutPage/>}/>
            <Route path="/puzzles" element={<PuzzlesProbe/>}/>
        </Routes>
    </MemoryRouter>,
);

beforeEach(() => setToken('jwt'));
afterEach(() => {
    vi.unstubAllGlobals();
    setToken(null);
});

describe('daily workout', () => {
    it('the plan, the streak, links to the trainer and to the review', async () => {
        vi.stubGlobal('fetch', vi.fn(async (url: unknown) => reply(url)));
        await act(async () => page());
        expect(screen.getByTestId('workout-status')).toHaveTextContent('Days in a row: 3');
        expect(screen.getByTestId('workout-puzzles')).toHaveTextContent('Puzzles on weak themes: 2 of 5');
        expect(screen.getByRole('link', {name: 'Name the square'})).toHaveAttribute('href', '/train/coord_name');
        expect(screen.getByRole('link', {name: 'Review 4 positions'})).toHaveAttribute('href', '/repertoire/7/drill');
        expect(screen.getByTestId('workout-mistake')).toHaveTextContent('No mistakes to repeat today.');
        await act(async () => fireEvent.click(screen.getByTestId('workout-theme-pin')));
        expect(screen.getByTestId('probe')).toHaveTextContent('{"train":{"theme":"pin","blind":false}}');
    });

    it('"My week": games, puzzles, days and advice by the server code', async () => {
        vi.stubGlobal('fetch', vi.fn(async (url: unknown) => reply(url)));
        await act(async () => page());
        expect(await screen.findByTestId('week-games')).toHaveTextContent('Games over the last 7 days: 5 (3 won, 1 drawn, 1 lost)');
        expect(screen.getByTestId('week-games')).toHaveTextContent('+14');
        expect(screen.getByTestId('week-puzzles')).toHaveTextContent('Puzzles: 9 solved of 12');
        expect(screen.getByTestId('week-days')).toHaveTextContent('Active days: 4 of 7');
        expect(screen.getByTestId('week-advice')).toHaveTextContent('A steady week');
    });

    it('without a login — a hint', () => {
        setToken(null);
        page();
        expect(screen.getByTestId('workout-login')).toBeInTheDocument();
    });
});
