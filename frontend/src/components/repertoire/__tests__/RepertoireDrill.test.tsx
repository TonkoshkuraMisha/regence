// Repertoire review (task 20.2): cards (right, a mistake → a repeat at the end of the session without changing the schedule, the result),
// the "Learn new" mode (the show first), "Play against the repertoire" (the opponent's reply, leaving the lines, the end of a line).

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setToken} from '../../../services/authToken';
import type {DrillCard, Repertoire} from '../../../services/repertoire';
import {RepertoireDrillPage} from '../RepertoireDrill';

const ROOT = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -';
const AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -';
const AFTER_D4 = 'rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq -';

const REP: Repertoire = {
    id: 7, name: 'Caro', color: 'black', starter: null, root: ROOT,
    moves: [
        {position: ROOT, uci: 'e2e4', san: 'e4', child: AFTER_E4, comment: '', mine: false},
        {position: AFTER_E4, uci: 'c7c6', san: 'c6', child: 'x', comment: 'solid', mine: true},
        {position: ROOT, uci: 'd2d4', san: 'd4', child: AFTER_D4, comment: '', mine: false},
        {position: AFTER_D4, uci: 'd7d5', san: 'd5', child: 'y', comment: '', mine: true},
    ],
};

const STATS = {total: 2, new: 2, learning: 0, learned: 0, due: 0, new_left: 10};
const CARDS: DrillCard[] = [
    {position: AFTER_E4, line: ['e2e4'], fen: `${AFTER_E4} 0 1`, answers: [{uci: 'c7c6', san: 'c6', comment: 'solid'}], status: 'new'},
    {position: AFTER_D4, line: ['d2d4'], fen: `${AFTER_D4} 0 1`, answers: [{uci: 'd7d5', san: 'd5', comment: ''}], status: 'new'},
];

type Body = Record<string, unknown>;

function stub(opponent: (moves: string[]) => string | null = () => 'e2e4') {
    const answers: Body[] = [];
    const mock = vi.fn(async (url: string, init?: RequestInit) => {
        const u = String(url);
        const body = init?.body ? JSON.parse(String(init.body)) as Body : {};
        let reply: unknown = REP;
        if (u.includes('/drill?')) reply = {stats: STATS, cards: CARDS};
        else if (u.endsWith('/drill/answer')) {
            answers.push(body);
            const card = CARDS.find((c) => c.position === body.position)!;
            reply = {correct: card.answers[0].uci === body.uci, answers: card.answers, status: 'learning', due_at: null, stats: STATS};
        } else if (u.endsWith('/opponent')) {
            const move = opponent(body.moves as string[]);
            reply = {reply: move, san: move};
        }
        return {ok: true, json: async () => reply} as Response;
    });
    vi.stubGlobal('fetch', mock);
    return answers;
}

const page = () => render(
    <MemoryRouter initialEntries={['/repertoire/7/drill']}>
        <Routes>
            <Route path="/repertoire/:repertoireId/drill" element={<RepertoireDrillPage/>}/>
        </Routes>
    </MemoryRouter>,
);
const move = async (from: string, to: string) => {
    fireEvent.click(document.querySelector(`[data-square="${from}"]`)!);
    await act(async () => fireEvent.click(document.querySelector(`[data-square="${to}"]`)!));
};

beforeEach(() => setToken('jwt'));
afterEach(() => {
    vi.unstubAllGlobals();
    setToken(null);
});

describe('repertoire review', () => {
    it('right, a mistake, a repeat of the mistake at the end of the session, the result', async () => {
        const answers = stub();
        await act(async () => page());
        expect(screen.getByTestId('drill-stats')).toHaveTextContent('new 2');
        expect(screen.getByTestId('drill-prompt')).toHaveTextContent('Your move in this position?');
        await move('c7', 'c6');
        expect(screen.getByTestId('drill-prompt')).toHaveTextContent('Correct!');
        expect(screen.getByText('solid', {exact: false})).toBeInTheDocument();
        fireEvent.click(screen.getByTestId('drill-next'));

        await move('e7', 'e5');
        expect(screen.getByTestId('drill-prompt')).toHaveTextContent('Not this move. In your repertoire: d5.');
        fireEvent.click(screen.getByTestId('drill-next'));
        expect(screen.getByTestId('drill-prompt')).toHaveTextContent('Once more');
        await move('d7', 'd5');
        fireEvent.click(screen.getByTestId('drill-next'));

        expect(screen.getByTestId('drill-done')).toHaveTextContent('1 correct, 1 mistakes');
        expect(answers.map((a) => [a.uci, a.retry])).toEqual([['c7c6', false], ['e7e5', false], ['d7d5', true]]);
    });

    it('"Learn new": the show first, then the check', async () => {
        stub();
        await act(async () => page());
        await act(async () => fireEvent.click(screen.getByTestId('drill-tab-learn')));
        expect(screen.getByTestId('drill-prompt')).toHaveTextContent('shown by the arrow');
        fireEvent.click(screen.getByTestId('drill-check'));
        expect(screen.getByTestId('drill-prompt')).toHaveTextContent('Your move in this position?');
    });

    it('play against the repertoire: the opponent moves first, leaving the lines, the end of a line', async () => {
        stub((moves) => (moves.length === 0 ? 'e2e4' : null));
        await act(async () => page());
        await act(async () => fireEvent.click(screen.getByTestId('drill-tab-play')));
        expect(screen.getByTestId('drill-play-line')).toHaveTextContent('1. e4');
        await move('e7', 'e5');
        expect(screen.getByTestId('drill-play-status')).toHaveTextContent('Here you play: c6');
        fireEvent.click(screen.getByTestId('drill-play-retry'));
        await move('c7', 'c6');
        expect(screen.getByTestId('drill-play-status')).toHaveTextContent('The line is complete');
    });
});
