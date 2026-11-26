// Master games (task 14.7): the list, the intro text, the mentor's comment, the "what would you play?" stop.

import {fireEvent, render, screen, within} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import game from '../../../content/classics/botvinnik-tal-1961.json';
import {ClassicGamePage, ClassicsPage} from '../ClassicsPage';
import {playMove} from '../../../test/boardMoves';
import {classicLink} from '../../../content/classics';


function renderAt(path: string) {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route path="/learn/classics" element={<ClassicsPage/>}/>
                <Route path="/learn/classics/:gameId" element={<ClassicGamePage/>}/>
            </Routes>
        </MemoryRouter>,
    );
}

afterEach(() => vi.unstubAllGlobals());

describe('Master games', () => {
    it('a list of fifty-five games', async () => {
        renderAt('/learn/classics');
        expect(await screen.findByTestId('classic-botvinnik-tal-1961')).toHaveTextContent('Botvinnik');
        expect(screen.getAllByTestId(/^classic-[a-z]/)).toHaveLength(55);
    });

    it('the intro text, then a stop before the key move and points for the master\'s move', async () => {
        renderAt('/learn/classics/botvinnik-tal-1961');
        expect(await screen.findByTestId('classic-intro')).toHaveTextContent('Nimzo-Indian Defence');
        const stop = game.stops[0];
        const moves = within(screen.getByTestId('classic-moves')).getAllByRole('button');
        fireEvent.click(moves[stop.ply - 1]);
        fireEvent.click(screen.getByRole('button', {name: 'Move forward'}));
        expect(screen.getByTestId('classic-stop')).toHaveTextContent('What would you play as White?');
        await playMove(stop.move.slice(0, 2), stop.move.slice(2, 4));
        expect(screen.getByTestId('classic-stop-score')).toHaveTextContent('Points: 100 of 100');
        fireEvent.click(screen.getByTestId('classic-stop-continue'));
        expect(screen.queryByTestId('classic-stop')).toBeNull();
        expect(screen.getByTestId('classic-stop-total')).toHaveTextContent('100 of 100');
    });

    it('the intro stays after the first move: the board never shifts under the eyes', async () => {
        renderAt('/learn/classics/botvinnik-tal-1961');
        const intro = await screen.findByTestId('classic-intro');
        fireEvent.click(screen.getByTestId('classic-stops-toggle'));
        fireEvent.click(screen.getByRole('button', {name: 'Move forward'}));
        expect(screen.getByTestId('classic-intro')).toBe(intro);
        // Beside the board (inside the column with the moves), not above it.
        expect(intro.parentElement).toContainElement(screen.getByTestId('classic-moves'));
    });

    it('without stops a move goes through at once', async () => {
        renderAt('/learn/classics/botvinnik-tal-1961');
        await screen.findByTestId('classic-intro');
        fireEvent.click(screen.getByTestId('classic-stops-toggle'));
        const moves = within(screen.getByTestId('classic-moves')).getAllByRole('button');
        fireEvent.click(moves[game.stops[0].ply - 1]);
        fireEvent.click(screen.getByRole('button', {name: 'Move forward'}));
        expect(screen.queryByTestId('classic-stop')).toBeNull();
    });

    it('a demonstration link (Big course "demo" step) opens the game without stops', async () => {
        renderAt(classicLink('botvinnik-tal-1961', {demo: true}));
        await screen.findByTestId('classic-intro');
        expect(screen.getByTestId('classic-stops-toggle')).not.toBeChecked();
        const moves = within(screen.getByTestId('classic-moves')).getAllByRole('button');
        fireEvent.click(moves[game.stops[0].ply - 1]);
        fireEvent.click(screen.getByRole('button', {name: 'Move forward'}));
        expect(screen.queryByTestId('classic-stop')).toBeNull();
    });
});
