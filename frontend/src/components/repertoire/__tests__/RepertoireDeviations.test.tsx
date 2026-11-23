// Deviations from the repertoire in a game (task 20.3): texts by kind, "Train" sets a card and leads to
// training, "Add an answer" opens the editor on the line with the opponent's move; the editor reads ?line=.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setToken} from '../../../services/authToken';
import {moveLabel} from '../../../services/repertoire';
import type {Deviation} from '../../../services/repertoire';
import {RepertoireDeviations} from '../RepertoireDeviations';
import {legalPrefix, RepertoireEditorPage} from '../RepertoirePages';

vi.mock('../../OpeningExplorer', () => ({OpeningExplorer: () => null}));

const LEFT: Deviation = {repertoire_id: 3, name: 'Spanish', starter: null, kind: 'you_left', ply: 5, played: 'Bc4',
    played_uci: 'f1c4', expected: ['Bb5'], line: ['e2e4', 'e7e5', 'g1f3', 'b8c6'], position: 'P'};
const NEW: Deviation = {repertoire_id: 4, name: '', starter: 'caro_kann', kind: 'opponent_new', ply: 2, played: 'e6',
    played_uci: 'e7e6', expected: ['c6'], line: ['e2e4'], position: 'Q'};

function stub(results: Deviation[]) {
    const mock = vi.fn(async (url: string) => ({
        ok: true,
        json: async () => (String(url).includes('/deviations') ? {color: 'white', results}
            : String(url).endsWith('/focus') ? {ok: true}
                : {id: 3, name: 'Spanish', color: 'white', starter: null, root: 'R', moves: []}),
    }) as Response);
    vi.stubGlobal('fetch', mock);
    return mock;
}

const view = () => render(
    <MemoryRouter initialEntries={['/game/9']}>
        <Routes>
            <Route path="/game/:gameId" element={<RepertoireDeviations gameId="9"/>}/>
            <Route path="/repertoire/:repertoireId/drill" element={<p>drill page</p>}/>
        </Routes>
    </MemoryRouter>,
);

beforeEach(() => setToken('jwt'));
afterEach(() => {
    vi.unstubAllGlobals();
    setToken(null);
});

describe('repertoire deviations', () => {
    it('the move number and the legal start of the line', () => {
        expect([moveLabel(5), moveLabel(2)]).toEqual(['3.', '1…']);
        expect(legalPrefix(['e2e4', 'e7e5', 'e2e4', 'g1f3'])).toEqual(['e2e4', 'e7e5']);
    });

    it('your own move is wrong: the text and "Train"', async () => {
        const mock = stub([LEFT, NEW]);
        await act(async () => view());
        expect(screen.getByTestId('deviation-3')).toHaveTextContent('Move 3. Bc4: you left “Spanish” — your move here is Bb5.');
        expect(screen.getByTestId('deviation-4')).toHaveTextContent('does not have');
        expect(screen.getByTestId('deviation-add-4')).toHaveAttribute('href', '/repertoire/4?line=e2e4,e7e6');
        await act(async () => fireEvent.click(screen.getByTestId('deviation-train-3')));
        expect(mock.mock.calls.some(([u]) => String(u).endsWith('/repertoires/3/drill/focus'))).toBe(true);
        expect(screen.getByText('drill page')).toBeInTheDocument();
    });

    it('without login and without results there is no block', async () => {
        stub([]);
        const {container} = await act(async () => view());
        expect(container).toBeEmptyDOMElement();
        setToken(null);
        const fetchMock = stub([LEFT]);
        await act(async () => view());
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('the editor opens on a line from the address', async () => {
        stub([]);
        await act(async () => render(
            <MemoryRouter initialEntries={['/repertoire/3?line=e2e4,e7e5,zz']}>
                <Routes><Route path="/repertoire/:repertoireId" element={<RepertoireEditorPage/>}/></Routes>
            </MemoryRouter>,
        ));
        expect(screen.getByTestId('repertoire-line')).toHaveTextContent('1. e4 e5');
    });
});
