// Ежедневная разминка (таск 22.2): план с отметками и серией, переходы в задачи по теме, тренажёр, дебюты, ошибки.

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

describe('ежедневная разминка', () => {
    it('план, серия, ссылки на тренажёр и повторение', async () => {
        vi.stubGlobal('fetch', vi.fn(async (url: unknown) => reply(url)));
        await act(async () => page());
        expect(screen.getByTestId('workout-status')).toHaveTextContent('Дней подряд: 3');
        expect(screen.getByTestId('workout-puzzles')).toHaveTextContent('Задачи на слабые темы: 2 из 5');
        expect(screen.getByRole('link', {name: 'Назови поле'})).toHaveAttribute('href', '/train/coord_name');
        expect(screen.getByRole('link', {name: 'Повторить позиций: 4'})).toHaveAttribute('href', '/repertoire/7/drill');
        expect(screen.getByTestId('workout-mistake')).toHaveTextContent('Сегодня ошибок для повторения нет.');
        await act(async () => fireEvent.click(screen.getByTestId('workout-theme-pin')));
        expect(screen.getByTestId('probe')).toHaveTextContent('{"train":{"theme":"pin","blind":false}}');
    });

    it('«Моя неделя»: партии, задачи, дни и совет по коду сервера', async () => {
        vi.stubGlobal('fetch', vi.fn(async (url: unknown) => reply(url)));
        await act(async () => page());
        expect(await screen.findByTestId('week-games')).toHaveTextContent('Партий за 7 дней: 5 (побед 3, ничьих 1, поражений 1)');
        expect(screen.getByTestId('week-games')).toHaveTextContent('+14');
        expect(screen.getByTestId('week-puzzles')).toHaveTextContent('решено 9 из 12');
        expect(screen.getByTestId('week-days')).toHaveTextContent('Дней с занятиями: 4 из 7');
        expect(screen.getByTestId('week-advice')).toHaveTextContent('Ровная неделя');
    });

    it('без входа — подсказка', () => {
        setToken(null);
        page();
        expect(screen.getByTestId('workout-login')).toBeInTheDocument();
    });
});
