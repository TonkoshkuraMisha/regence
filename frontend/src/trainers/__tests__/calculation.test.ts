// Calculation and attention (task 19.7): checks and captures, the exchange outcome, distances, the square rule, position evaluation.

import {describe, expect, it} from 'vitest';
import {Chess} from 'chess.js';
import {
    captureGain, checksAndCaptures, distanceQuestion, evalVerdict, exchangeVerdict, kingCatchesPawn, kingDistance, knightDistance,
    squareFen, squareQuestion,
} from '../calculation';

/**
 * An independent check of the square rule by brute-forcing the race: White has only a pawn (goes forward, from the 2nd — at once two
 * squares if the path is free), Black has a king (does not step under the pawn's attack). The king "catches up" if it takes the pawn or
 * a new queen (the White king is far away and does not protect) or steps in front of the pawn.
 */
function raceCatches(pawn: string, king: string, toMove: 'w' | 'b'): boolean {
    const files = 'abcdefgh';
    const f = files.indexOf(pawn[0]);
    const memo = new Map<string, boolean>();
    const search = (pr: number, kf: number, kr: number, white: boolean): boolean => {
        const key = `${pr}${kf}${kr}${white}`;
        if (memo.has(key)) return memo.get(key)!;
        let result: boolean;
        if (white) {
            const blocked = kf === f && kr === pr + 1;
            if (blocked) result = true;
            else {
                const next = pr === 2 && !(kf === f && kr === 4) ? 4 : pr + 1;
                result = search(next, kf, kr, false);
            }
        } else if (pr === 8) {
            result = Math.max(Math.abs(kf - f), Math.abs(kr - 8)) <= 1;  // attacks the queen
        } else if (Math.max(Math.abs(kf - f), Math.abs(kr - pr)) <= 1) {
            result = true;  // attacks the pawn
        } else {
            result = false;
            for (let df = -1; df <= 1 && !result; df++) {
                for (let dr = -1; dr <= 1 && !result; dr++) {
                    const nf = kf + df, nr = kr + dr;
                    if ((!df && !dr) || nf < 0 || nf > 7 || nr < 1 || nr > 8) continue;
                    if (nr === pr + 1 && Math.abs(nf - f) === 1) continue;  // under the pawn's attack
                    result = search(pr, nf, nr, true);
                }
            }
        }
        memo.set(key, result);
        return result;
    };
    return search(Number(pawn[1]), files.indexOf(king[0]), Number(king[1]), toMove === 'w');
}

describe('checks and captures', () => {
    it('for both sides, including the one that does not move', () => {
        // The Italian position, White to move: Kxe5 — a capture; Bb5 — not a check (the pawn d7 and the knight c6 block).
        const found = checksAndCaptures('r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3');
        expect(found.has('f3e5')).toBe(true);
        expect(found.has('f1b5')).toBe(false);
        // After 1.e4 e5 — no checks, no captures.
        expect(checksAndCaptures('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2').size).toBe(0);
        // White to move, but Black's checks are counted too: Qe2+ — a check for Black; Kxd2 — a capture for White.
        const both = checksAndCaptures('4k3/8/8/8/8/8/3q4/4K3 w - - 0 1');
        expect(both.has('e1d2')).toBe(true);
        expect(both.has('d2e2')).toBe(true);
        expect(both.has('d2a5')).toBe(true);    // Qa5+ — a check along the diagonal
        expect(both.has('d2d5')).toBe(false);   // Qd5 — neither a check nor a capture
    });
});

describe('exchange', () => {
    it('an unprotected piece — a win; one protected by a pawn — a loss; an equal exchange', () => {
        expect(captureGain('4k3/8/8/3n4/8/8/8/3QK3 w - - 0 1', 'd5')).toBe(300);
        expect(exchangeVerdict(captureGain('4k3/8/4p3/3n4/8/8/8/3QK3 w - - 0 1', 'd5'))).toBe('lose');   // Qxd5 exd5
        expect(exchangeVerdict(captureGain('4k3/8/4p3/3n4/8/2N5/8/4K3 w - - 0 1', 'd5'))).toBe('equal'); // Nxd5 exd5
    });

    it('x-ray: a rook behind a rook supports a capture', () => {
        // White: rooks d1, d2; Black: knight d5 protected by rook d8. Rxd5 Rxd5 Rxd5 — White wins the knight.
        expect(captureGain('3rk3/8/8/3n4/8/8/3R4/3RK3 w - - 0 1', 'd5')).toBe(300);
    });
});

describe('distances and the square rule', () => {
    it('knight: a1→b3 — 1, a1→h8 — 6, a1→b2 — 4; king — by Chebyshev', () => {
        expect(knightDistance('a1', 'b3')).toBe(1);
        expect(knightDistance('a1', 'h8')).toBe(6);
        expect(knightDistance('a1', 'b2')).toBe(4);
        expect(kingDistance('a1', 'h8')).toBe(7);
        for (let i = 0; i < 50; i++) {
            const q = distanceQuestion(3, i);
            expect(q.answer).toBeGreaterThanOrEqual(q.piece === 'k' ? 0 : 1);
        }
    });

    it('the square rule: a king in the square catches up; a pawn move shifts the square; a pawn from the 2nd moves two squares', () => {
        // A position from the owner's feedback 18.11: 1.f7 Ke7 2.f8=Q+ Kxf8 — catches up.
        expect(kingCatchesPawn('f6', 'd6', 'w')).toBe(true);
        expect(kingCatchesPawn('a4', 'e8', 'w')).toBe(true);    // 1.a5 Kd7 2.a6 Kc7 3.a7 Kb7 4.a8=Q+ Kxa8
        expect(kingCatchesPawn('a4', 'f8', 'w')).toBe(false);
        expect(kingCatchesPawn('a4', 'f8', 'b')).toBe(true);    // Ke7 — a step into the square
        expect(kingCatchesPawn('a2', 'g8', 'b')).toBe(true);    // a pawn from the 2nd — the square from the 3rd rank
        expect(kingCatchesPawn('a2', 'h8', 'b')).toBe(false);
        // Comparison with brute-forcing the race itself on all the positions that the trainer gives.
        for (let seed = 1; seed <= 6; seed++) {
            for (let i = 0; i < 40; i++) {
                const q = squareQuestion(seed, i);
                expect(q.answer, `${q.pawn} ${q.king} ${q.toMove}`).toBe(raceCatches(q.pawn, q.king, q.toMove));
            }
        }
        for (let i = 0; i < 30; i++) {
            const q = squareQuestion(5, i);
            expect(() => new Chess(squareFen(q))).not.toThrow();
        }
    });

    it('the evaluation: advantage ≥ 1.5, equality ≤ 0.6, between — we do not ask', () => {
        expect(evalVerdict(200)).toBe('white');
        expect(evalVerdict(-150)).toBe('black');
        expect(evalVerdict(40)).toBe('equal');
        expect(evalVerdict(100)).toBeNull();
    });
});
