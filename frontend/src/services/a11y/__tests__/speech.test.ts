// Accessibility (task 26.3): a move, a square and a position in words in both languages; moving focus with arrows.

import {Chess} from 'chess.js';
import {describe, expect, it} from 'vitest';
import {makeI18n} from '../../../i18n';
import {moveWords, positionWords, squareLabel, stepSquare} from '../speech';
import type {Translate, VerboseMove} from '../speech';

const en = makeI18n('en').t as Translate;

function lastMove(...sans: string[]): VerboseMove {
    const game = new Chess();
    sans.forEach((san) => game.move(san));
    return game.history({verbose: true}).at(-1) as VerboseMove;
}

describe('moves in words', () => {
    it('an ordinary move, a capture with check, castling', () => {
        expect(moveWords(lastMove('Nf3'), en)).toBe('White: knight g1 to f3');
        expect(moveWords(lastMove('e4', 'd5', 'exd5'), en)).toBe('White: pawn e4 takes d5');
        expect(moveWords(lastMove('e4', 'f5', 'Qh5+'), en)).toBe('White: queen d1 to h5, check');
        expect(moveWords(lastMove('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Nf6', 'O-O'), en)).toBe('White: castles kingside');
        expect(moveWords(lastMove('f3', 'e5', 'g4', 'Qh4#'), en)).toBe('Black: queen d8 to h4, checkmate');
    });

    it('en passant and promotion', () => {
        expect(moveWords(lastMove('e4', 'a6', 'e5', 'd5', 'exd6'), en)).toBe('White: pawn e5 takes d6, en passant');
        const game = new Chess('8/P6k/8/8/8/8/8/K7 w - - 0 1');
        game.move('a8=Q');
        expect(moveWords(game.history({verbose: true})[0] as VerboseMove, en)).toBe('White: pawn a7 to a8, promotes to a queen');
    });
});

describe('squares and position', () => {
    it('a square label; in a blindfold game the piece is not named', () => {
        expect(squareLabel('e4', {type: 'n', color: 'w'}, en)).toBe('e4, white knight');
        expect(squareLabel('e4', null, en)).toBe('e4, empty');
        expect(squareLabel('e4', {type: 'n', color: 'w'}, en, true)).toBe('e4');
    });

    it('the position by sides, from the king to the pawns', () => {
        const board = new Chess('4k3/8/8/8/8/8/1P2P3/4K2R w K - 0 1').board();
        expect(positionWords(board, en)).toBe('White: king on e1; rook on h1; pawn on b2, e2. Black: king on e8.');
    });

    it('arrows go by the screen: on a flipped board the directions change; at the edge — stays in place', () => {
        expect(stepSquare('e4', 'ArrowUp', false)).toBe('e5');
        expect(stepSquare('e4', 'ArrowRight', false)).toBe('f4');
        expect(stepSquare('e4', 'ArrowUp', true)).toBe('e3');
        expect(stepSquare('e4', 'ArrowRight', true)).toBe('d4');
        expect(stepSquare('h8', 'ArrowUp', false)).toBe('h8');
        expect(stepSquare('a1', 'ArrowLeft', false)).toBe('a1');
    });
});
