// Archive viewer of a finished Fischer random game (task 21.3): stepping through the positions the server replayed, the engine
// evaluation (curve, score, largest swings), a refusal for a game of another variant. Pure helpers: score text and swings.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {Chess960Archive, formatScore, swingsOf} from '../Chess960Archive';

const START = 'bbqnnrkr/pppppppp/8/8/8/8/PPPPPPPP/BBQNNRKR w HAha - 0 1';
const AFTER_E4 = 'bbqnnrkr/pppppppp/8/8/4P3/8/PPPP1PPP/BBQNNRKR b HAha e3 0 1';
const AFTER_E5 = 'bbqnnrkr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/BBQNNRKR w HAha e6 0 2';
const RECORD = {game_id: 7, start_fen: START, fens: [START, AFTER_E4, AFTER_E5], moves: ['e2e4', 'e7e5'], sans: ['e4', 'e5'],
    result: '1-0'};

function stub(handlers: Record<string, () => {ok: boolean; status?: number; body: unknown}>) {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
        const path = String(url).split('/api/v1/chess960')[1];
        const reply = handlers[path]();
        return {ok: reply.ok, status: reply.status ?? 200, json: async () => reply.body, text: async () => JSON.stringify(reply.body)} as Response;
    }));
}

const page = () => render(
    <MemoryRouter initialEntries={['/play/960/game/7']}>
        <Routes><Route path="/play/960/game/:gameId" element={<Chess960Archive/>}/></Routes>
    </MemoryRouter>,
);

afterEach(() => vi.unstubAllGlobals());

describe('Fischer game archive', () => {
    it('formats scores and finds the largest swings of the side that moved', () => {
        expect(formatScore(35)).toBe('+0.35');
        expect(formatScore(-120)).toBe('-1.20');
        expect(formatScore(10000)).toBe('+M');
        expect(formatScore(-10000)).toBe('-M');
        // White drops 3 pawns on ply 0, Black drops 2 pawns on ply 1, then nothing notable.
        expect(swingsOf([100, -200, 0, 10])).toEqual([{ply: 0, loss: 300}, {ply: 1, loss: 200}]);
        expect(swingsOf([0, 50, 40])).toEqual([]);
    });

    it('opens on the final position and steps with the buttons', async () => {
        stub({'/archive/7': () => ({ok: true, body: RECORD})});
        page();
        expect(await screen.findByTestId('c960a-position')).toHaveTextContent('Move 2 of 2');
        expect(screen.getByTestId('c960a-moves')).toHaveTextContent('1. e4 e5');
        fireEvent.click(screen.getByTestId('c960a-first'));
        expect(screen.getByTestId('c960a-position')).toHaveTextContent('Move 0 of 2');
        fireEvent.click(screen.getByTestId('c960a-next'));
        expect(screen.getByTestId('c960a-position')).toHaveTextContent('Move 1 of 2');
        fireEvent.keyDown(window, {key: 'ArrowRight'});
        fireEvent.keyDown(window, {key: 'ArrowRight'});  // does not go past the last position
        expect(screen.getByTestId('c960a-position')).toHaveTextContent('Move 2 of 2');
        fireEvent.click(screen.getByTestId('c960a-last'));
        fireEvent.click(screen.getByTestId('c960a-prev'));
        expect(screen.getByTestId('c960a-position')).toHaveTextContent('Move 1 of 2');
    });

    it('shows the engine curve, the score of the current position and the swings', async () => {
        stub({
            '/archive/7': () => ({ok: true, body: RECORD}),
            '/archive/7/analysis': () => ({ok: true, body: {game_id: 7, scores: [20, 30, 400], complete: true}}),
        });
        page();
        await screen.findByTestId('c960a-position');
        await act(async () => fireEvent.click(screen.getByTestId('c960a-analyse')));
        expect(await screen.findByTestId('c960a-curve')).toBeInTheDocument();
        expect(screen.getByTestId('c960a-score')).toHaveTextContent('+4.00');
        const swing = screen.getByTestId('c960a-swings').querySelector('button')!;
        expect(swing).toHaveTextContent('Move 1: e5 lost about 3.7 pawns');
        fireEvent.click(swing);
        expect(screen.getByTestId('c960a-position')).toHaveTextContent('Move 2 of 2');
    });

    it('refuses a game that is not Fischer random', async () => {
        stub({'/archive/7': () => ({ok: false, status: 400, body: {detail: {code: 'not_chess960_game', message: 'x'}}})});
        page();
        expect(await screen.findByRole('alert')).toHaveTextContent('This game is not Fischer random chess');
    });
});
