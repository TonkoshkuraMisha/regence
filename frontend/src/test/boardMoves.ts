// --- FILE: frontend/src/test/boardMoves.ts ---
// A move on the board in page tests: two clicks — on your own piece and on the square. Not dragging: the boards subscribe to
// the piece release from an effect, and under CI load the release sometimes came before the subscription — the move was lost, the test
// failed randomly. Dragging itself is checked by the PuzzleBoard tests (puzzleMoves.test.tsx) and the main board.

import {act, fireEvent} from '@testing-library/react';

/** A board square by the square name (data-square). */
export function boardCell(square: string): HTMLElement {
    const element = document.querySelector(`[data-square="${square}"]`);
    if (!(element instanceof HTMLElement)) throw new Error(`no square ${square}`);
    return element;
}

/** Make a move from → to with two clicks (each in an act, so that React has time to render the selection). */
export async function playMove(from: string, to: string): Promise<void> {
    await act(async () => {
        fireEvent.click(boardCell(from));
    });
    await act(async () => {
        fireEvent.click(boardCell(to));
    });
}
