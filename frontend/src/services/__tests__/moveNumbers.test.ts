// --- FILE: frontend/src/services/__tests__/moveNumbers.test.ts ---
// Move records with numbers (services/moveNumbers.ts): from the starting position and from a custom position where Black moves first.

import {describe, expect, it} from 'vitest';
import {numberedMoves} from '../moveNumbers';

describe('moves with numbers', () => {
    it('from the starting position — the number at White\'s move', () => {
        expect(numberedMoves(['e4', 'c6', 'd4'])).toEqual(['1. e4', 'c6', '2. d4']);
        expect(numberedMoves([])).toEqual([]);
    });

    it('from a custom position — the number from the FEN, the first Black move with an ellipsis', () => {
        const blackToMove = '6k1/5ppp/8/8/8/8/5PPP/6K1 b - - 0 12';
        expect(numberedMoves(['Kf8', 'Kf1', 'Ke7'], blackToMove)).toEqual(['12… Kf8', '13. Kf1', 'Ke7']);
        const whiteToMove = '6k1/5ppp/8/8/8/8/5PPP/6K1 w - - 0 30';
        expect(numberedMoves(['Kf1', 'Kf8'], whiteToMove)).toEqual(['30. Kf1', 'Kf8']);
    });
});
