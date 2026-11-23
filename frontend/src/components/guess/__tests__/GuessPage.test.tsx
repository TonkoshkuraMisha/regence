// "Guess the master's move" (task 14.3): a position with game context, the player's move, points and the master's move, a series, the session summary.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {GuessPage} from '../GuessPage';
import {understanding} from '../../../services/guess';

const POSITION = {
    id: 5, game_id: 42, ply: 8, fen: 'rn1qkbnr/ppp2p1p/3p2p1/4p3/2B1P1b1/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 0 5',
    side: 'white', move_number: 5, difficulty: 1500, series_id: 7, series_index: 0, series_length: 2,
    white: 'Legal', black: 'Saint Brie', event: 'Paris', date: '1750',
    previous: ['e4', 'e5', 'Nf3', 'd6', 'Bc4', 'Bg4', 'Nc3', 'g6'], first_previous_ply: 0, last_move: 'g7g6',
};
const ANSWER = {
    score: 100, loss_cp: 0, master_move: 'f3e5', master_san: 'Nxe5',
    lines: [{uci: 'f3e5', san: 'Nxe5', cp: 300}, {uci: 'h2h3', san: 'h3', cp: 50}],
    comment: [], arrows: [], themes: ['fork', 'unknown_code'], next_id: 6,
};

const cell = (name: string) => document.querySelector(`[data-square="${name}"]`) as HTMLElement;

// A move with two clicks: this test is about the page scenario, dragging is checked by the PuzzleBoard tests. Dragging here
// (a mocked elementsFromPoint and window listeners from an effect) was occasionally lost under full load.
async function play(from: string, to: string) {
    await act(async () => {
        fireEvent.click(cell(from));
    });
    await act(async () => {
        fireEvent.click(cell(to));
    });
}

function stub(routes: Record<string, (init?: RequestInit) => unknown>) {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
        const key = Object.keys(routes).find((path) => String(url).includes(path));
        if (!key) return {ok: false, status: 404, json: async () => ({})} as Response;
        return {ok: true, status: 200, json: async () => routes[key](init)} as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

function renderPage(path = '/guess') {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route path="/guess" element={<GuessPage/>}/>
                <Route path="/guess/:positionId" element={<GuessPage/>}/>
            </Routes>
        </MemoryRouter>,
    );
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('Guess the master\'s move', () => {
    it('whole game (?whole=1): the game\'s moments in order, at the end — the score for the game', async () => {
        const fetchMock = stub({
            // Answers go before positions: the stub takes the first address that is contained in the request.
            '/position/5/answer': () => ({...ANSWER, score: 80, next_id: null}),
            '/position/9/answer': () => ({...ANSWER, score: 100, next_id: null}),
            '/guess/game/42/quiz': () => ({questions: [{id: 'winner', options: ['white', 'black', 'draw']}], score: 1, total: 1, results: {winner: true}, correct: {winner: 'white'}}),
            '/guess/game/42': () => ({positions: [{id: 5, ply: 8, series_id: 7}, {id: 9, ply: 20, series_id: null}]}),
            '/guess/position/9': () => ({...POSITION, id: 9, ply: 20, series_id: null}),
            '/guess/position/5': () => POSITION,
        });
        render(<MemoryRouter initialEntries={['/guess/5?whole=1']}><Routes>
            <Route path="/guess/:positionId" element={<GuessPage/>}/><Route path="/guess" element={<GuessPage/>}/>
        </Routes></MemoryRouter>);
        expect(await screen.findByTestId('guess-whole-progress')).toHaveTextContent('Moment 1 of 2 in this game');
        expect(screen.queryByTestId('guess-series')).toBeNull();  // instead of the series counter — the game counter
        await play('f3', 'e5');
        await act(async () => fireEvent.click(await screen.findByTestId('guess-next')));
        expect(await screen.findByTestId('guess-whole-progress')).toHaveTextContent('Moment 2 of 2');
        await play('f3', 'e5');
        await act(async () => fireEvent.click(await screen.findByTestId('guess-next')));
        expect(screen.getByTestId('guess-whole-done')).toHaveTextContent('Game finished: 180 of 200 points.');
        expect(screen.getByTestId('guess-whole-level')).toHaveTextContent('Your result is 90% of the masters’ score — at the masters’ level');
        expect(fetchMock.mock.calls.filter(([u]) => String(u).endsWith('/guess/game/42'))).toHaveLength(1);
        // Questions after the game: shown in the summary, the answers go off for checking.
        fireEvent.click(await screen.findByTestId('quiz-winner-white'));
        fireEvent.click(screen.getByTestId('guess-quiz-check'));
        expect(await screen.findByTestId('guess-quiz-score')).toHaveTextContent('1 of 1');
    });

    it('choice from options: positions are requested with candidates, the answer is a button', async () => {
        const candidates = [{uci: 'h2h3', san: 'h3'}, {uci: 'f3e5', san: 'Nxe5'}, {uci: 'c3d5', san: 'Nd5'}];
        const fetchMock = stub({
            'candidates=true': () => ({position: {...POSITION, candidates}}),
            '/guess/next': () => ({position: POSITION}),
            '/position/5/answer': () => ANSWER,
        });
        renderPage();
        expect(await screen.findByTestId('guess-players')).toBeInTheDocument();
        expect(screen.queryByTestId('guess-choices')).toBeNull();  // in the normal mode there are no options
        await act(async () => fireEvent.click(screen.getByTestId('guess-choices-toggle')));
        expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/guess/next?series=false&candidates=true'))).toBe(true);
        expect(await screen.findByTestId('guess-choices')).toHaveTextContent('One of these is the master’s move');
        await act(async () => fireEvent.click(screen.getByTestId('guess-choice-f3e5')));
        expect(await screen.findByTestId('guess-score')).toHaveTextContent('100');
        const post = (fetchMock.mock.calls as unknown as [string, RequestInit][]).find(([, init]) => init?.method === 'POST')!;
        expect(JSON.parse(String(post[1].body))).toEqual({move: 'f3e5', attempt: 1, hints: 0});
        expect(screen.queryByTestId('guess-choices')).toBeNull();  // after the answer there are no buttons
    });

    it('a position with game context, a move — points, the master\'s move and the series continues', async () => {
        const fetchMock = stub({'/guess/next': () => ({position: POSITION}), '/position/5/answer': () => ANSWER});
        renderPage();

        expect(await screen.findByTestId('guess-players')).toHaveTextContent('Legal — Saint Brie, Paris 1750');
        expect(screen.getByText('White to move')).toBeInTheDocument();
        expect(screen.getByTestId('guess-series')).toHaveTextContent('Move 1 of 2 in this game');

        await play('f3', 'e5');
        // First wait for the answer (the request goes out asynchronously — under CI load it might not have been sent yet), then check the body.
        expect(await screen.findByTestId('guess-score')).toHaveTextContent('100');
        const post = (fetchMock.mock.calls as unknown as [string, RequestInit][]).find(([, init]) => init?.method === 'POST')!;
        expect(JSON.parse(String(post[1].body))).toEqual({move: 'f3e5', attempt: 1, hints: 0});
        expect(screen.getByText('Just like the master!')).toBeInTheDocument();
        expect(screen.getByText('Master\'s move: Nxe5')).toBeInTheDocument();
        expect(screen.getByTestId('guess-themes')).toHaveTextContent('Themes:Fork');  // an unknown code is not shown
        expect(screen.getByRole('button', {name: /Continue the game/})).toBeInTheDocument();
        expect(screen.getByTestId('guess-session')).toHaveTextContent('Points: 100 of 100 · understanding 100%');
    });

    it('three attempts: a mistake — "once more" without a summary, a hint is taken, the second attempt carries the number and hints', async () => {
        let calls = 0;
        const fetchMock = stub({
            '/guess/next': () => ({position: POSITION}),
            '/position/5/hint': () => ({comment: [], arrows: []}),
            '/position/5/answer': () => (++calls === 1 ? {retry: true, attempts_left: 2, loss_cp: 200} : ANSWER),
        });
        renderPage();
        await screen.findByTestId('guess-players');
        expect(screen.getByTestId('guess-attempt')).toHaveTextContent('Attempt 1 of 3');
        await play('h2', 'h3');
        expect(await screen.findByTestId('guess-retry')).toBeInTheDocument();
        expect(screen.getByTestId('guess-attempt')).toHaveTextContent('Attempt 2 of 3');
        expect(screen.queryByTestId('guess-answer')).toBeNull();
        fireEvent.click(screen.getByTestId('guess-hint'));
        await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/position/5/hint?step=1'))).toBe(true));
        await play('f3', 'e5');
        expect(await screen.findByTestId('guess-score')).toHaveTextContent('100');
        const posts = (fetchMock.mock.calls as unknown as [string, RequestInit][]).filter(([, init]) => init?.method === 'POST');
        expect(JSON.parse(String(posts[1][1].body))).toEqual({move: 'f3e5', attempt: 2, hints: 1});
    });

    it('after the answer the board is free: the master\'s move can be played and continued, the answer is already counted', async () => {
        const fetchMock = stub({'/guess/next': () => ({position: POSITION}), '/position/5/answer': () => ({...ANSWER, score: 0})});
        renderPage();
        await screen.findByTestId('guess-players');
        await play('h2', 'h3');
        expect(await screen.findByTestId('guess-score')).toHaveTextContent('0');
        expect(screen.queryByTestId('explorer-controls')).toBeNull();
        await play('f3', 'e5');  // the master's move played after the answer is analysis, not a second answer
        expect(cell('e5').querySelector('img')?.getAttribute('alt')).toBe('wn');
        expect(screen.getByTestId('explorer-back')).not.toBeDisabled();
        expect((fetchMock.mock.calls as unknown as [string, RequestInit][]).filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
    });

    it('positions are not selected yet — a clear message', async () => {
        stub({'/guess/next': () => ({position: null})});
        renderPage();
        expect(await screen.findByTestId('guess-empty')).toHaveTextContent('No positions are ready yet');
    });

    it('a specific position by link from the game viewer', async () => {
        const fetchMock = stub({'/guess/position/5': () => POSITION});
        renderPage('/guess/5');
        expect(await screen.findByTestId('guess-players')).toBeInTheDocument();
        expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toMatch(/\/guess\/position\/5$/);
    });

    it('understanding accuracy — the average score', () => {
        expect(understanding([])).toBeNull();
        expect(understanding([100, 80, 0])).toBe(60);
    });
});
