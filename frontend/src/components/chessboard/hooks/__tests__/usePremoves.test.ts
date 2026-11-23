// Premove chain (task B.2): the position after the premoves — pieces are rearranged without checking the rules.

import {Chess} from 'chess.js';
import {describe, expect, it} from 'vitest';
import {applyPremoves} from '../usePremoves';

describe('applyPremoves', () => {
    it('chain: knight f3, then g5 — the piece is taken from the square after the first premove', () => {
        const view = applyPremoves(new Chess(), [{from: 'g1', to: 'f3'}, {from: 'f3', to: 'g5'}]);
        expect(view.get('g5' as never)).toMatchObject({type: 'n', color: 'w'});
        expect(view.get('g1' as never)).toBeFalsy();
        expect(view.get('f3' as never)).toBeFalsy();
    });

    it('castling moves the rook, promotion puts the chosen piece', () => {
        const castle = applyPremoves(new Chess('4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1'), [{from: 'e1', to: 'c1'}]);
        expect(castle.get('d1' as never)).toMatchObject({type: 'r'});
        expect(castle.get('a1' as never)).toBeFalsy();
        const promote = applyPremoves(new Chess('4k3/P7/8/8/8/8/8/4K3 w - - 0 1'), [{from: 'a7', to: 'a8', promotion: 'n'}]);
        expect(promote.get('a8' as never)).toMatchObject({type: 'n', color: 'w'});
    });

    it('a premove from an empty square is skipped, the original game is not changed', () => {
        const game = new Chess();
        const view = applyPremoves(game, [{from: 'e4', to: 'e5'}]);
        expect(view.fen()).toBe(game.fen());
    });
});
