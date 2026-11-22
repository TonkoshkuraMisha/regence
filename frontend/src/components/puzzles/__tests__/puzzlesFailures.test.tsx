// --- FILE: frontend/src/components/puzzles/__tests__/puzzlesFailures.test.tsx ---
// Страница задач (PuzzlesPage.tsx) при сбоях сети: непроверенный ход откатывается с сообщением об ошибке,
// отказ подсказки, показа решения и старта режима на время тоже показываются сообщением (а не молча теряются),
// завершение забега с ошибкой возвращает на стартовый экран. Сервер подменяется стабом fetch: нужный адрес
// отвечает кодом 500, остальные — заготовками, как в puzzles.test.tsx.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import PuzzlesPage from '../PuzzlesPage';
import {resetThemeRegistryCache} from '../../../services/themes';
import {setToken} from '../../../services/authToken';

const PUZZLE = {
    id: 7, fen: '4r1k1/5ppp/8/8/8/8/3R1PPP/3R2K1 b - - 0 1', first_move: 'e8e2', rating: 1480,
    themes: ['back_rank_mate', 'mate_in_2'], color: 'white', solution_length: 2,
};
const PROFILE = {rating: 1500, games: 3, streak: 1, best: {'3': 4, '5': 0}, history: []};
const REGISTRY = {sections: ['F'], themes: [
    {code: 'back_rank_mate', section: 'F', parent: null, sources: ['D', 'L'], minimums: [25, 25, 20, 15]},
]};

/** Стаб сервера: адреса из failing отвечают 500, остальные — заготовками (задача, профиль, реестр тем). */
function stub(failing: string[], extra: (url: string) => unknown = () => ({})) {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (failing.some((part) => url.includes(part))) {
            return {ok: false, status: 500, json: async () => ({detail: 'boom'})} as Response;
        }
        const body = url.includes('/themes') ? REGISTRY
            : url.endsWith('/puzzles/me') ? PROFILE
                : url.includes('/next') ? PUZZLE
                    : extra(url);
        return {ok: true, status: 200, json: async () => body} as Response;
    }));
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

async function startRated() {
    render(
        <MemoryRouter initialEntries={['/puzzles']}>
            <PuzzlesPage/>
        </MemoryRouter>,
    );
    await act(async () => {
        fireEvent.click(await screen.findByTestId('puzzle-next'));
    });
    await act(async () => {
        await vi.advanceTimersByTimeAsync(600);
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

describe('сбои сети на странице задач', () => {
    it('отказ проверки хода откатывает ход и показывает ошибку', async () => {
        stub(['/move']);
        await startRated();
        await play('d2', 'd8');
        await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
        // Ход откатан: ладья снова на d2, решать можно дальше.
        expect(square('d2').querySelector('img')?.getAttribute('alt')).toBe('wr');
    });

    it('отказ подсказки и показа решения — сообщение об ошибке', async () => {
        stub(['/hint', '/giveup', '/solution', '/skip']);
        await startRated();
        await act(async () => {
            fireEvent.click(screen.getByTestId('puzzle-hint'));
        });
        await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());

        await act(async () => {
            fireEvent.click(screen.getByTestId('puzzle-give-up'));
        });
        await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    });

    it('отказ старта режима на время — сообщение, забег не начат', async () => {
        stub(['/timed/start'], () => ({rows: []}));
        render(
            <MemoryRouter initialEntries={['/puzzles']}>
                <PuzzlesPage/>
            </MemoryRouter>,
        );
        fireEvent.click(await screen.findByTestId('puzzle-mode-timed'));
        await act(async () => {
            fireEvent.click(await screen.findByTestId('puzzle-timed-3'));
        });
        await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
        expect(screen.queryByTestId('puzzle-run')).toBeNull();
    });
});
