// The opening explorer (task 16.2): moves with statistics, the name, masters' games, links by library marks (27.5);
// a click on a move plays it.

import {act, fireEvent, render, screen, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {ToolsPage} from '../tools/ToolsPage';
import {libraryMarks, shares} from '../../services/openingExplorer';
import type {ExplorerGame} from '../../services/openingExplorer';

const START = {
    fen: 'start', opening: null,
    moves: [
        {uci: 'e2e4', san: 'e4', games: 10, white_wins: 5, draws: 3, black_wins: 2, opening: {eco: 'B00', name: "King's Pawn Game"}},
        {uci: 'd2d4', san: 'd4', games: 4, white_wins: 1, draws: 2, black_wins: 1, opening: null},
    ],
    games: [
        {id: 77, white: 'Morphy, Paul', black: 'Anderssen, Adolf', year: '1858', result: '1-0', eco: 'C60', source: 'archive'},
        {id: 5, white: 'Steinitz, Wilhelm', black: 'Zukertort, Johannes', year: '1886', result: '0-1', eco: 'C50',
         source: 'library', annotated: true, structure: 'carlsbad', themes: ['pin', 'fork']},
        {id: 6, white: 'Lasker, Emanuel', black: 'Tarrasch, Siegbert', year: '1908', result: '1-0', eco: 'C67',
         source: 'library', annotated: false, structure: 'carlsbad', themes: ['unknown_theme']},
    ],
};
const AFTER_E4 = {fen: 'x', opening: {eco: 'B00', name: "King's Pawn Game"}, moves: [], games: []};

function stub() {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
        const moves = JSON.parse(String(init?.body)).moves as string[];
        return {ok: true, status: 200, json: async () => (moves.length ? AFTER_E4 : START)} as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe('opening explorer', () => {
    it('result shares sum to 100', () => {
        expect(shares({games: 3, white_wins: 1, draws: 1, black_wins: 1})).toEqual([33, 34, 33]);
        expect(shares({games: 0, white_wins: 0, draws: 0, black_wins: 0})).toEqual([0, 0, 0]);
    });

    it('library marks: each once, in the filter order, archive games and unknown codes skipped', () => {
        const games = START.games as ExplorerGame[];
        expect(libraryMarks(games)).toEqual({structures: ['carlsbad'], themes: ['fork', 'pin']});
        expect(libraryMarks([{...games[0], structure: 'saw', themes: ['fork']}])).toEqual({structures: [], themes: []});
    });

    it('moves, masters\' games and a move by a click on the row', async () => {
        const fetchMock = stub();
        render(<MemoryRouter><ToolsPage/></MemoryRouter>);
        const table = await screen.findByTestId('explorer-moves');
        expect(within(table).getAllByRole('row')).toHaveLength(3);
        expect(screen.getByLabelText('White wins 50%, draws 30%, Black wins 20%')).toBeInTheDocument();
        expect(screen.getByTestId('explorer-games')).toHaveTextContent('Morphy, Paul — Anderssen, Adolf');
        expect(screen.getByRole('link', {name: /Morphy/})).toHaveAttribute('href', '/game/77');
        // A library game (8b) leads to the library and is marked with explanations.
        const fromLibrary = screen.getByTestId('explorer-game-library-5');
        expect(fromLibrary).toHaveAttribute('href', '/library/game/5');
        expect(fromLibrary).toHaveTextContent('with explanations');
        // Marks of the library games lead to the library search with that mark (27.5).
        expect(screen.getByTestId('explorer-structure-carlsbad')).toHaveAttribute('href', '/library?structure=carlsbad');
        expect(screen.getByTestId('explorer-theme-fork')).toHaveAttribute('href', '/library?theme=fork');
        expect(screen.getByTestId('explorer-theme-pin')).toBeInTheDocument();
        await act(async () => fireEvent.click(screen.getByRole('button', {name: 'e4'})));
        expect(await screen.findByTestId('explorer-opening')).toHaveTextContent("B00 · King's Pawn Game");
        expect(screen.getByTestId('explorer-empty')).toBeInTheDocument();
        expect(screen.getByTestId('tools-line')).toHaveTextContent('1. e4');
        expect(JSON.parse(String(fetchMock.mock.calls.at(-1)![1]!.body))).toEqual({moves: ['e2e4']});
    });

    it('during a game with a person — the server message', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({
            ok: false, status: 409, json: async () => ({detail: {code: 'engine_locked_in_game'}}),
        } as Response)));
        render(<MemoryRouter><ToolsPage/></MemoryRouter>);
        expect(await screen.findByRole('alert')).toBeInTheDocument();
    });
});
