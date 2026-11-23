// Games with odds (task 21.1): material-odds positions are legal and lack the needed piece, time odds, who gives the odds.

import {Chess} from 'chess.js';
import {describe, expect, it} from 'vitest';
import {giverColor, hasGiver, inviteOddsFields, ODDS, oddsFen, oddsTimes} from '../odds';

describe('odds', () => {
    it('material odds: the position is legal, the piece is gone, castling with the removed rook is lost', () => {
        expect(oddsFen('knight', 'white')).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/R1BQKBNR w KQkq - 0 1');
        expect(oddsFen('rook', 'black')).toBe('1nbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQk - 0 1');
        expect(oddsFen('queen', 'black')).toBe('rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
        expect(oddsFen('pawn', 'black')).toBe('rnbqkbnr/ppppp1pp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
        for (const kind of ODDS) {
            for (const giver of ['white', 'black'] as const) {
                const fen = oddsFen(kind, giver);
                if (fen) expect(new Chess(fen).moves().length).toBeGreaterThan(0);
            }
        }
        expect(oddsFen('time', 'white')).toBeNull();
        expect(oddsFen('hourglass', 'white')).toBeNull();
    });

    it('"two moves in a row": the receiver has already played e4+d4 (e5+d5), the giver is to move, the position is legal', () => {
        const whiteGives = new Chess(oddsFen('tempo', 'white')!);
        expect(whiteGives.turn()).toBe('w');
        expect(whiteGives.get('e5')?.type).toBe('p');
        expect(whiteGives.get('d5')?.type).toBe('p');
        const blackGives = new Chess(oddsFen('tempo', 'black')!);
        expect(blackGives.turn()).toBe('b');
        expect(blackGives.get('e4')?.type).toBe('p');
        expect(blackGives.get('d4')?.type).toBe('p');
        expect(hasGiver('tempo')).toBe(true);
    });

    it('time odds - a third of the clock, at least a minute; who gives the odds', () => {
        expect(oddsTimes('time', 'white', 300_000, 300_000)).toEqual({white: 100_000, black: 300_000});
        expect(oddsTimes('time', 'black', 120_000, 120_000)).toEqual({white: 120_000, black: 60_000});
        expect(oddsTimes('knight', 'white', 300_000, 300_000)).toEqual({white: 300_000, black: 300_000});
        expect(giverColor('me', 'black')).toBe('black');
        expect(giverColor('opponent', 'black')).toBe('white');
    });
});

describe('a game with odds over the network (21.1)', () => {
    it('the client board is restored from the server PGN with SetUp/FEN headers', () => {
        const fen = oddsFen('queen', 'white')!;
        const start = new Chess();
        start.loadPgn(`[SetUp "1"]\n[FEN "${fen}"]`);
        expect(start.fen()).toBe(fen);
        const played = new Chess();
        played.loadPgn(`[SetUp "1"]\n[FEN "${fen}"]\n\n1. e4 e5`);
        expect(played.history()).toEqual(['e4', 'e5']);
        expect(inviteOddsFields({kind: 'queen', giver: 'me'})).toEqual({odds_kind: 'queen', odds_giver: 'creator'});
        expect(inviteOddsFields({kind: 'hourglass', giver: 'me'}).odds_kind).toBe('hourglass');
        expect(inviteOddsFields({kind: 'none', giver: 'me'}).odds_kind).toBe('');
    });

    it('"hourglass" and "no odds" have no giver', () => {
        expect(hasGiver('hourglass')).toBe(false);
        expect(hasGiver('none')).toBe(false);
        expect(hasGiver('time')).toBe(true);
    });
});
