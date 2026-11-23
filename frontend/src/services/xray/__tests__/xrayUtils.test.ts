// Board "X-ray" (task 12.1): calculations on known positions.

import {Chess} from 'chess.js';
import {describe, expect, it, vi} from 'vitest';
import {
    absolutePins, attackMap, captures, checks, exchangeGain, controlMap, defenses, destinationSafety, gameFor, hangingPieces, legalMoves,
    lineTactics, overloadedDefenders, pawnFlags, piecesOf, xrayFor,
} from '../xrayUtils';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

describe('square control', () => {
    it('starting position: the third rank is White\'s, the sixth is Black\'s, symmetrically', () => {
        const control = controlMap(piecesOf(START));
        expect(control.get('e3')).toEqual({white: 2, black: 0});
        expect(control.get('f3')).toEqual({white: 3, black: 0});
        expect(control.get('f6')).toEqual({white: 0, black: 3});
        expect(control.get('e4')).toEqual({white: 0, black: 0});
        const total = (color: 'white' | 'black') => [...control.values()].reduce((sum, c) => sum + c[color], 0);
        expect(total('white')).toBe(total('black'));
    });

    it('battery: a queen behind a rook hits the squares behind the rook', () => {
        const pieces = piecesOf('4k3/8/8/8/8/8/4R3/4Q1K1 w - - 0 1');
        const e7 = attackMap(pieces).get('e7') ?? [];
        expect(e7.map((a) => [a.from, a.xray])).toEqual(expect.arrayContaining([['e2', false], ['e1', true]]));
        expect(controlMap(pieces).get('e7')?.white).toBe(2);
    });

    it('without a battery: an opponent piece blocks the line', () => {
        const pieces = piecesOf('4k3/8/8/8/8/4n3/4R3/4Q1K1 w - - 0 1');
        expect(controlMap(pieces).get('e5')?.white).toBe(0);
    });
});

describe('pieces under attack and overload', () => {
    it('an unprotected piece and a piece attacked by a cheaper one', () => {
        // The knight d5 is unprotected and attacked by the pawn e6; the bishop c4 is protected, but attacked by the pawn b5.
        const pieces = piecesOf('4k3/8/4p3/1p1N4/2B5/8/3P4/4K3 w - - 0 1');
        expect(hangingPieces(pieces, 'w').sort()).toEqual(['c4', 'd5']);
        expect(hangingPieces(pieces, 'b')).toEqual(['b5']);
    });

    it('a protected piece attacked by an equal one — does not hang', () => {
        // The knight e3 is protected by the pawn d2 and attacked by the knight d5 — an exchange, not a win.
        const pieces = piecesOf('4k3/8/8/3n4/8/4N3/3P4/4K3 w - - 0 1');
        expect(hangingPieces(pieces, 'w')).toEqual([]);
    });

    it('an overloaded defender: one rook defends two attacked pieces', () => {
        // The rook d1 defends the knight d4 and the bishop b1; it is overloaded only when both pieces are attacked.
        const pieces = piecesOf('3rk3/8/8/8/3N4/8/8/1B1R2K1 b - - 0 1');
        const pieces2 = piecesOf('4k3/8/8/8/r2N4/8/8/rB1R2K1 b - - 0 1');
        expect(overloadedDefenders(pieces, 'w')).toEqual([]);
        expect(overloadedDefenders(pieces2, 'w')).toEqual([{defender: 'd1', duties: expect.arrayContaining(['d4', 'b1'])}]);
    });
});

describe('pins and x-rays', () => {
    it('an absolute pin by a bishop', () => {
        const lines = lineTactics(piecesOf('4k3/8/2n5/8/B7/8/8/4K3 w - - 0 1'), 'w');
        expect(lines).toEqual([{kind: 'pin', attacker: 'a4', front: 'c6', behind: 'e8', absolute: true}]);
    });

    it('a pin of the queen to the rook — relative', () => {
        const lines = lineTactics(piecesOf('r3k3/8/8/8/n7/8/8/R3K3 w - - 0 1'), 'w');
        expect(lines).toEqual([{kind: 'pin', attacker: 'a1', front: 'a4', behind: 'a8', absolute: false}]);
    });

    it('an x-ray: the king in front, the queen behind it', () => {
        const skewer = lineTactics(piecesOf('4q3/8/8/4k3/8/8/8/K3R3 w - - 0 1'), 'w');
        expect(skewer).toEqual([{kind: 'skewer', attacker: 'e1', front: 'e5', behind: 'e8', absolute: true}]);
        // A queen in front that is weaker than the attacker does not count: a rook against a queen behind a rook is not an x-ray.
        expect(lineTactics(piecesOf('4r3/8/8/4q3/8/8/8/K3Q2k w - - 0 1'), 'w')).toEqual([]);
    });

    it('your own piece on the line — neither a pin nor an attack', () => {
        expect(lineTactics(piecesOf('4k3/8/2n5/1P6/B7/8/8/4K3 w - - 0 1'), 'w')).toEqual([]);
    });
});

describe('moves, captures, defences, checks', () => {
    it('capture: an unprotected piece — a win, a protected equal one — an exchange', () => {
        const fen = '4k3/8/8/3n1b2/8/4N3/8/4K3 w - - 0 1';
        const list = captures(fen, 'w');
        expect(list).toEqual(expect.arrayContaining([
            {from: 'e3', to: 'd5', kind: 'winning'},
            {from: 'e3', to: 'f5', kind: 'winning'},
        ]));
        const defended = captures('4k3/8/4p3/3n4/8/4N3/8/4K3 w - - 0 1', 'w');
        expect(defended).toEqual([{from: 'e3', to: 'd5', kind: 'exchange'}]);
    });

    it('captures for the side that does not move', () => {
        expect(captures('4k3/8/8/3n4/8/4N3/8/4K3 w - - 0 1', 'b')).toEqual([{from: 'd5', to: 'e3', kind: 'winning'}]);
    });

    it('defences: pawns and pieces cover their own', () => {
        const list = defenses(piecesOf(START), 'w');
        expect(list).toContainEqual({from: 'e1', to: 'e2'});
        expect(list).toContainEqual({from: 'g1', to: 'e2'});
        expect(list.some((a) => a.to === 'e1')).toBe(false);
    });

    it('checks and mate', () => {
        const list = checks('6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1', 'w');
        expect(list).toEqual([{from: 'a1', to: 'a8', mate: true}]);
        expect(checks(START, 'w')).toEqual([]);
    });

    it('all moves of the starting position — 20, promotion — one arrow', () => {
        expect(legalMoves(START, 'w')).toHaveLength(20);
        expect(legalMoves('4k3/P7/8/8/8/8/8/4K3 w - - 0 1', 'w').filter((m) => m.from === 'a7')).toHaveLength(1);
    });

    it('an impossible position for the other side — empty, not an error', () => {
        // White gives check; if Black were to move — fine, but a White move while the Black king is in check is impossible.
        const fen = '4k3/4Q3/8/8/8/8/8/4K3 b - - 0 1';
        expect(gameFor(fen, 'w')).toBeNull();
        expect(legalMoves(fen, 'w')).toEqual([]);
    });
});

describe('pawns', () => {
    it('isolated and passed', () => {
        const flags = pawnFlags(piecesOf('4k3/p7/8/3P4/8/8/6PP/4K3 w - - 0 1'), 'w');
        expect(flags.isolated).toEqual(['d5']);
        expect(flags.passed.sort()).toEqual(['d5', 'g2', 'h2']);
        expect(pawnFlags(piecesOf('4k3/p7/8/3P4/8/8/6PP/4K3 w - - 0 1'), 'b').passed).toEqual(['a7']);
    });
});

describe('square safety for a piece', () => {
    it('knight: a square under a pawn — dangerous, a free one — safe', () => {
        const list = destinationSafety('4k3/8/8/8/3p4/8/8/4KN2 w - - 0 1', 'f1');
        const byTarget = Object.fromEntries(list.map((s) => [s.square, s.safe]));
        expect(byTarget.e3).toBe(false);
        expect(byTarget.g3).toBe(true);
        expect(byTarget.d2).toBe(true);
    });

    it('an empty square — nothing', () => {
        expect(destinationSafety(START, 'e4')).toEqual([]);
    });
});

describe('full x-ray', () => {
    it('collects everything; chess.js moves are generated once per calculation', () => {
        const fen = 'r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N1PN2/PP1B1PPP/R2QKB1R w KQ - 0 8';
        const spy = vi.spyOn(Chess.prototype, 'moves');
        const report = xrayFor(fen, 'w');
        xrayFor(fen, 'b');
        expect(spy).toHaveBeenCalledTimes(2);
        spy.mockRestore();
        expect(report.control.size).toBe(64);
        expect(report.moves.length).toBeGreaterThan(20);
    });

    it('recalculation on every move is unnoticeable', () => {
        // Separately ~3 ms; a rough bound — with a margin for a parallel run with coverage.
        const fen = 'r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N1PN2/PP1B1PPP/R2QKB1R w KQ - 0 8';
        const startedAt = performance.now();
        for (let i = 0; i < 20; i++) xrayFor(fen, i % 2 ? 'b' : 'w');
        expect((performance.now() - startedAt) / 20).toBeLessThan(50);
    });
});


describe('exchanges and pins (SEE)', () => {
    it('a defender pinned to the king does not defend', () => {
        // The bishop d5 is "protected" by the knight e3, but the knight is pinned by the rook e8 to the king e1.
        const pieces = piecesOf('4r2k/8/1n6/3B4/8/4N3/8/4K3 w - - 0 1');
        // The pinned knight itself also hangs: the rook attacks it, there is no defence.
        expect(hangingPieces(pieces, 'w').sort()).toEqual(['d5', 'e3']);
        expect(defenses(pieces, 'w')).toEqual([]);
    });

    it('a pinned piece defends along the pin line', () => {
        // The rook e3 is pinned by the rook e8, but defends the square e5 on the same line.
        const pieces = piecesOf('4r2k/8/3n4/4N3/8/4R3/8/4K3 w - - 0 1');
        expect(hangingPieces(pieces, 'w')).toEqual([]);
    });

    it('two attackers against one defender of the same value', () => {
        const pieces = piecesOf('4k3/8/1n3n2/3N4/8/2N5/8/4K3 w - - 0 1');
        expect(hangingPieces(pieces, 'w')).toEqual(['d5']);
        expect(captures('4k3/8/1n3n2/3N4/8/2N5/8/4K3 b - - 0 1', 'b').map((c) => c.kind)).toEqual(['winning', 'winning']);
    });

    it('capturing a protected pawn with the queen — not a win, a pinned defender — a win', () => {
        expect(captures('4k3/8/4p3/3p4/8/8/8/3QK3 w - - 0 1', 'w')).toEqual([{from: 'd1', to: 'd5', kind: 'exchange'}]);
        // The defender d5 (the pawn e6) is pinned by the rook e1 to the king e8: the queen capture wins the pawn.
        const pinned = '4k3/8/4p3/3p4/8/8/8/3QRK2 w - - 0 1';
        expect([...absolutePins(piecesOf(pinned)).keys()]).toEqual(['e6']);
        expect(captures(pinned, 'w')).toContainEqual({from: 'd1', to: 'd5', kind: 'winning'});
    });

    it('exchangeGain: the sides may not continue the exchange', () => {
        expect(exchangeGain(1, 9, [], [1])).toBe(-8);  // the queen takes a protected pawn
        expect(exchangeGain(3, 3, [], [3])).toBe(0);     // a knight for a knight
        expect(exchangeGain(3, 3, [3], [3])).toBe(3);    // two knights against one defender
        expect(exchangeGain(3, 3, [3], [])).toBe(3);
        expect(exchangeGain(5, 3, [], [1])).toBe(2);     // the knight takes a rook, the pawn takes the knight
    });
});

describe('x-ray', () => {
    it('a queen through an unprotected rook onto a knight; a protected rook — not an attack', () => {
        const lined = lineTactics(piecesOf('3nk3/8/8/8/3r4/8/8/3QK3 w - - 0 1'), 'w');
        expect(lined).toContainEqual({kind: 'skewer', attacker: 'd1', front: 'd4', behind: 'd8', absolute: false});
        const guarded = lineTactics(piecesOf('3nk3/8/8/4p3/3r4/8/8/3QK3 w - - 0 1'), 'w');
        expect(guarded.filter((l) => l.kind === 'skewer')).toEqual([]);
    });
});
