// Endgame trainer (task 14.4): exercise data, the perfect defender's reply, a missed win, mate against
// the optimum, a held draw; the engine's fallback reply when the tablebases are unavailable. The tables are mocked.

import {render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {Chess} from 'chess.js';
import {EndgamesPage, EndgameTrainerPage, EXERCISES} from '../EndgameTrainer';
import {trainerVerdict} from '../../../services/tablebase';
import {playMove} from '../../../test/boardMoves';

const cell = (name: string) => document.querySelector(`[data-square="${name}"]`) as HTMLElement;

function stubProbe(answer: (fen: string) => unknown) {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => ({
        ok: true, status: 200, json: async () => answer(JSON.parse(String(init?.body)).fen),
    } as Response));
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

function open(id: string) {
    return render(
        <MemoryRouter initialEntries={[`/learn/endgames/${id}`]}>
            <Routes><Route path="/learn/endgames/:exerciseId" element={<EndgameTrainerPage/>}/></Routes>
        </MemoryRouter>,
    );
}

afterEach(() => vi.unstubAllGlobals());

describe('exercise data', () => {
    it('36 legal positions, for mates — the optimum is within the limit', () => {
        expect(EXERCISES).toHaveLength(36);
        for (const e of EXERCISES) {
            const game = new Chess(e.fen);
            expect(game.isGameOver(), e.id).toBe(false);
            expect(game.turn()).toBe(e.side === 'white' ? 'w' : 'b');
            if (e.goal === 'mate') expect(e.optimum! <= e.limit, e.id).toBe(true);
        }
    });

    it('a list by goals', () => {
        render(<MemoryRouter><EndgamesPage/></MemoryRouter>);
        expect(screen.getAllByTestId(/^endgame-/)).toHaveLength(36);
        expect(screen.getByTestId('endgame-lucena')).toHaveTextContent('Lucena');
    });
});

describe('playing against the tables', () => {
    it('the player\'s move — the defender replies with the best move, the counter grows', async () => {
        const fetchMock = stubProbe(() => ({category: 'loss', dtm: -16, dtz: -16,
            best: {uci: 'e5e4', san: 'Ke4', category: 'win', dtm: 15, dtz: 15}}));
        open('kq_center');
        await playMove('b1', 'f1');
        expect(await screen.findByTestId('endgame-moves')).toHaveTextContent('Moves: 1 · optimum 9 · limit 17');
        expect(cell('e4').querySelector('img')?.getAttribute('alt')).toBe('bk');
        const body = JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body));
        expect(body.fen).toContain('8/8/8/4k3/8/8/8/K4Q2 b');
    });

    it('a move that lets the win slip — the task is not completed', async () => {
        stubProbe(() => ({category: 'draw', dtm: 0, dtz: 0, best: {uci: 'e5e4', san: 'Ke4', category: 'draw', dtm: 0, dtz: 0}}));
        open('kq_center');
        await playMove('b1', 'b8');
        expect(await screen.findByTestId('endgame-result')).toHaveTextContent('let the win slip');
    });

    it('defence: a move that loses — a failure', async () => {
        stubProbe(() => ({category: 'win', dtm: 9, dtz: 9, best: null}));
        open('kp_opposition_def');
        await playMove('e8', 'd7');
        expect(await screen.findByTestId('endgame-result')).toHaveTextContent('That move loses');
    });
});

describe('tablebases unavailable — the engine replies', () => {
    it('a disputed engine evaluation does not break the task, a note is visible', async () => {
        stubProbe(() => ({category: 'maybe-win', dtm: null, dtz: null, source: 'engine',
            best: {uci: 'e5e4', san: 'Ke4', category: null, dtm: null, dtz: null}}));
        open('kq_center');
        await playMove('b1', 'f1');
        expect(await screen.findByTestId('endgame-engine-fallback')).toHaveTextContent('The endgame tablebases are unavailable right now');
        expect(screen.queryByTestId('endgame-result')).toBeNull();
        expect(cell('e4').querySelector('img')?.getAttribute('alt')).toBe('bk');
    });

    it('verdict rules: for the tables — strict, for the engine — only a clear evaluation', () => {
        const probe = (category: string, source: 'tablebase' | 'engine') => ({category, dtm: null, dtz: null, best: null, source});
        expect(trainerVerdict(probe('maybe-loss', 'tablebase'), true)).toBe('winLost');
        expect(trainerVerdict(probe('maybe-loss', 'engine'), true)).toBe('continue');
        expect(trainerVerdict(probe('maybe-win', 'engine'), true)).toBe('continue');
        expect(trainerVerdict(probe('draw', 'engine'), true)).toBe('winLost');
        expect(trainerVerdict(probe('loss', 'engine'), true)).toBe('continue');
        expect(trainerVerdict(probe('maybe-win', 'tablebase'), false)).toBe('drawLost');
        expect(trainerVerdict(probe('maybe-win', 'engine'), false)).toBe('continue');
        expect(trainerVerdict(probe('win', 'engine'), false)).toBe('drawLost');
    });
});
