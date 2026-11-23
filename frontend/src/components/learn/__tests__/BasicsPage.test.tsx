// Alphabet course (task 14.5): the section list, the "stars" level with a rating, no stepping under attack, the "what is on the board" question.

import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, describe, expect, it} from 'vitest';
import {BasicsPage, BasicsSectionPage} from '../BasicsPage';
import {playMove} from '../../../test/boardMoves';


function renderAt(path: string) {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route path="/learn/basics" element={<BasicsPage/>}/>
                <Route path="/learn/basics/:sectionId" element={<BasicsSectionPage/>}/>
            </Routes>
        </MemoryRouter>,
    );
}

afterEach(() => {
    localStorage.clear();
});

describe('The basics', () => {
    it('eight sections', () => {
        renderAt('/learn/basics');
        expect(screen.getAllByTestId(/^basics-section-/)).toHaveLength(8);
        expect(screen.getByTestId('basics-section-knight')).toHaveTextContent('Knight');
    });

    it('the rook collects a star in the minimum number of moves — three stars and the next level', async () => {
        renderAt('/learn/basics/rook');
        expect(screen.getByTestId('board-star-a5')).toBeInTheDocument();
        expect(screen.getByTestId('basics-moves')).toHaveTextContent('Moves: 0 · possible in 1');
        await playMove('a1', 'a5');
        expect(screen.queryByTestId('board-star-a5')).toBeNull();
        expect(screen.getByLabelText('Rating: 3 of 3')).toBeInTheDocument();
        fireEvent.click(screen.getByTestId('basics-next'));
        expect(screen.getByText('Level 2 of 7')).toBeInTheDocument();
    });

    it('stepping under attack is not allowed', async () => {
        renderAt('/learn/basics/rook');
        fireEvent.click(screen.getByRole('button', {name: '7'}));
        await playMove('a1', 'a3');
        expect(screen.getByTestId('basics-feedback')).toHaveTextContent('The opponent attacks that square');
        expect(screen.getByTestId('basics-moves')).toHaveTextContent('Moves: 0');
    });

    it('the "what is on the board" question: a wrong answer — a hint, the right one — an explanation', () => {
        renderAt('/learn/basics/special');
        fireEvent.click(screen.getByRole('button', {name: '7'}));
        fireEvent.click(screen.getByTestId('basics-answer-mate'));
        expect(screen.getByTestId('basics-feedback')).toHaveTextContent('Not quite');
        fireEvent.click(screen.getByTestId('basics-answer-stalemate'));
        expect(screen.getByTestId('basics-feedback')).toHaveTextContent('that is stalemate, a draw');
    });
});
