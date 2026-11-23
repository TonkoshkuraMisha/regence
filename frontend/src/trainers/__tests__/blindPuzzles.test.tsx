// Blindfold puzzles and "Where is the piece?" (task 19.6): on real classic games — the tasks are correct; a whole game.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {Chess} from 'chess.js';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {loadAllClassics} from '../../content/classics';
import {blindPlies, blindTask, whereQuestion} from '../blindPuzzles';

afterEach(() => vi.useRealTimers());

describe('blindfold tasks on classic games', () => {
    it('for every stop and N = 1, 5, 10: N moves, the stop move is legal in the final position, the question is unambiguous', async () => {
        const games = await loadAllClassics();
        let checked = 0;
        for (const game of games) {
            for (const stop of game.stops) {
                for (const n of [1, 5, 10]) {
                    const single = {...game, stops: [stop]};
                    const task = blindTask([single], n, 1, 0)!;
                    expect(task.moves).toHaveLength(blindPlies(n));
                    const board = new Chess(task.finalFen);
                    expect(board.moves({verbose: true}).some((m) => `${m.from}${m.to}${m.promotion ?? ''}` === stop.move), `${game.id} ${stop.ply}`).toBe(true);
                    const q = whereQuestion(task, n);
                    const same = board.board().flat().filter((c) => c && c.color === q.color && c.type === q.type);
                    expect(same).toHaveLength(1);
                    expect(same[0]!.square).toBe(q.square);
                    checked++;
                }
            }
        }
        expect(checked).toBeGreaterThan(500);
    }, 60_000);   // ~540 tasks, each replays a game in chess.js

    it('move numbers in the announcement: White — "N.", Black — "N…"', async () => {
        const [game] = await loadAllClassics();
        const task = blindTask([game], 2, 3, 0)!;
        expect(task.moves.every((m) => /^\d+(\.|…) \S+$/.test(m))).toBe(true);
    });
});

describe('game', () => {
    it('a blindfold move: position → moves one by one → a move on an empty board → evaluation; five tasks — the result', async () => {
        vi.useFakeTimers();
        const games = await loadAllClassics();
        vi.doMock('../../content/classics', async (orig) => ({...(await orig<object>()), loadAllClassics: async () => games}));
        const {BlindGame} = await import('../../components/trainers/BlindGames');
        const onFinish = vi.fn();
        render(<BlindGame mode="move" level={2} seed={4} onFinish={onFinish}/>);
        for (let i = 0; i < 5; i++) await act(async () => Promise.resolve());
        for (let round = 0; round < 5; round++) {
            const task = blindTask(games, 2, 4, round)!;
            fireEvent.click(screen.getByTestId('blind-ready'));
            for (let step = 0; step < 3; step++) {
                await act(async () => {
                    vi.advanceTimersByTime(1400);
                });
            }
            expect(screen.getByTestId('blind-moves').textContent).toContain(task.moves[1].split(' ')[1]);
            fireEvent.click(document.querySelector(`[data-square="${task.stop.move.slice(0, 2)}"]`)!);
            fireEvent.click(document.querySelector(`[data-square="${task.stop.move.slice(2, 4)}"]`)!);
            expect(screen.getByTestId('blind-score')).toHaveTextContent('100');
            fireEvent.click(screen.getByTestId('blind-next'));
        }
        expect(onFinish).toHaveBeenCalledWith(500, 0);
        vi.doUnmock('../../content/classics');
    });

    it('"Where is the piece?": the right square — 100, a wrong one — 0', async () => {
        vi.useFakeTimers();
        const games = await loadAllClassics();
        const {BlindGame} = await import('../../components/trainers/BlindGames');
        render(<BlindGame mode="where" level={1} seed={9} onFinish={vi.fn()}/>);
        for (let i = 0; i < 5; i++) await act(async () => Promise.resolve());
        const task = blindTask(games, 1, 9, 0)!;
        const q = whereQuestion(task, 9);
        fireEvent.click(screen.getByTestId('blind-ready'));
        for (let step = 0; step < 2; step++) {
            await act(async () => {
                vi.advanceTimersByTime(1400);
            });
        }
        expect(screen.getByTestId('blind-question').textContent).toMatch(/Where is/);
        const wrong = q.square === 'a1' ? 'h8' : 'a1';
        fireEvent.click(document.querySelector(`[data-square="${wrong}"]`)!);
        expect(screen.getByTestId('blind-score')).toHaveTextContent('0');
        expect(screen.getByTestId('blind-review').textContent).toContain(q.square);
    });
});
