// The game summary (task 11.5): the choice of the next opponent and the summary window.

import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {isSummaryKind, outcomeFor, recommendOpponent} from '../../../services/gameSummary';
import type {PoolOpponent} from '../../../services/gameSummary';
import {GameSummaryPanel} from '../GameSummaryPanel';
import {setToken} from '../../../services/authToken';

const POOL: PoolOpponent[] = [
    {kind: 'archetype', id: 'rusher', rating: 700},
    {kind: 'archetype', id: 'quiet', rating: 1000},
    {kind: 'historical', id: 'philidor', rating: 1850},
    {kind: 'historical', id: 'staunton', rating: 2000},
    {kind: 'historical', id: 'morphy', rating: 2150},
];

describe('recommendOpponent', () => {
    it('after a win — the nearest one noticeably stronger', () => {
        expect(recommendOpponent(POOL, {id: 'philidor', rating: 1850}, 'win')?.id).toBe('staunton');
    });

    it('after a loss — the nearest one noticeably weaker', () => {
        expect(recommendOpponent(POOL, {id: 'philidor', rating: 1850}, 'loss')?.id).toBe('quiet');
    });

    it('after a draw — another opponent of the same strength', () => {
        expect(recommendOpponent(POOL, {id: 'staunton', rating: 2000}, 'draw')?.id).not.toBe('staunton');
        expect(recommendOpponent(POOL, {id: 'staunton', rating: 2000}, 'draw')?.id).toBe('morphy');
    });

    it('from the edges — the nearest by strength; an empty pool — no one', () => {
        expect(recommendOpponent(POOL, {id: 'morphy', rating: 2150}, 'win')?.id).toBe('staunton');
        expect(recommendOpponent(POOL, {id: 'rusher', rating: 700}, 'loss')?.id).toBe('quiet');
        expect(recommendOpponent([], {id: 'x', rating: 1000}, 'win')).toBeNull();
    });

    it('the outcome from the player\'s point of view', () => {
        expect(outcomeFor('1-0', 'white')).toBe('win');
        expect(outcomeFor('1-0', 'black')).toBe('loss');
        expect(outcomeFor('0-1', 'black')).toBe('win');
        expect(outcomeFor('1/2-1/2', 'white')).toBe('draw');
        expect(isSummaryKind('seesaw')).toBe(true);
        expect(isSummaryKind('nonsense')).toBe(false);
    });
});

const REPORT = {
    white: {accuracy: 61.5}, black: {accuracy: 88.2},
    moves: [
        {ply: 1, move_number: 1, color: 'white', san: 'f3', coach: null},
        {ply: 2, move_number: 1, color: 'black', san: 'e5', coach: null},
        {ply: 3, move_number: 2, color: 'white', san: 'g4',
         coach: {comment: [{key: 'coach.verdict.blunder.v1', params: {move: 'g4'}}], arrows: [], highlights: []}},
        {ply: 4, move_number: 2, color: 'black', san: 'Qh4#', coach: null},
    ],
    summary: {
        kind: 'decisive_blunder', turning_point_ply: 3, lead_changes: 0, equal_share: 0.5,
        white: {best_ply: null, worst_ply: 3}, black: {best_ply: 4, worst_ply: null},
    },
};

beforeEach(() => setToken('jwt'));
afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
});

describe('GameSummaryPanel', () => {
    it('the review starts by itself; the game type, accuracy, the turning point with an explanation and a recommendation', async () => {
        const fetchMock = vi.fn(async () => ({ok: true, status: 200, json: async () => REPORT}) as Response);
        vi.stubGlobal('fetch', fetchMock);
        const onPlay = vi.fn();
        render(<GameSummaryPanel gameId={42} playerColor="white" recommendation={{name: 'Philidor', rating: 1850}}
                                 onPlayRecommended={onPlay}/>);
        expect(screen.getByText(/The coach is going through the game/)).toBeTruthy();
        await waitFor(() => expect(screen.getByTestId('summary-kind').textContent).toContain('Decided by one mistake'));
        const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(url).toContain('/analysis/game/42');
        expect(init.method).toBe('POST');
        expect(screen.getByTestId('summary-accuracy').textContent).toContain('61.5');
        const turning = screen.getByTestId('summary-moment-3');
        expect(turning.textContent).toContain('Turning point: 2. g4');
        expect(turning.textContent).toContain('blunder');
        // The worst move coincides with the turning point — it is not shown a second time.
        expect(screen.getAllByTestId(/summary-moment-/)).toHaveLength(1);
        expect(screen.getByTestId('summary-recommendation').textContent).toContain('Philidor (1850)');
        fireEvent.click(screen.getByTestId('summary-play'));
        expect(onPlay).toHaveBeenCalled();
    });

    it('as Black — its own key moves; without a recommendation there is no button', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => REPORT}) as Response));
        render(<GameSummaryPanel gameId={42} playerColor="black" recommendation={null} onPlayRecommended={vi.fn()}/>);
        await waitFor(() => expect(screen.getByTestId('summary-moment-4').textContent).toContain('2… Qh4#'));
        expect(screen.queryByTestId('summary-play')).toBeNull();
    });

    it('no network — the "no connection" message; a server refusal without a code — "could not analyse"', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => {
            throw new Error('offline');
        }));
        const {unmount} = render(<GameSummaryPanel gameId={42} playerColor="white" recommendation={null} onPlayRecommended={vi.fn()}/>);
        expect(await screen.findByText(/No connection to the server/)).toBeTruthy();
        unmount();

        vi.stubGlobal('fetch', vi.fn(async () => ({ok: false, status: 500, json: async () => ({})}) as Response));
        render(<GameSummaryPanel gameId={42} playerColor="white" recommendation={null} onPlayRecommended={vi.fn()}/>);
        expect(await screen.findByText(/Could not analyse the game/)).toBeTruthy();
    });
});
