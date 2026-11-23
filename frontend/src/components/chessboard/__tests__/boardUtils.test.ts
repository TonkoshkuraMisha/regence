// --- FILE: frontend/src/components/chessboard/__tests__/boardUtils.test.ts ---

import {describe, expect, it} from 'vitest';
import {Chess} from 'chess.js';
import {
    calculateMaterialBalance, cloneChessInstance, customStartFen, fittedBoardSize, MIN_BOARD_SIZE, pairHalfMoves, prevIndexHelper,
    STANDARD_START_FEN, validateFen,
} from '../boardUtils';
import {DEFAULT_TIME_CONTROL, TIME_CONTROLS} from '../../../config/timeControls';

describe('calculateMaterialBalance', () => {
    it('is even in the starting position', () => {
        const balance = calculateMaterialBalance(new Chess().board());
        expect(balance.whiteAdvantage).toBe(0);
        expect(balance.blackAdvantage).toBe(0);
        expect(balance.whiteCapturedSymbols).toEqual([]);
    });

    it('counts a captured piece for the capturing side', () => {
        const game = new Chess();
        ['e4', 'd5', 'exd5'].forEach((m) => game.move(m));
        const balance = calculateMaterialBalance(game.board());
        expect(balance.whiteAdvantage).toBe(1);
        expect(balance.whiteCapturedSymbols).toEqual(['♟']);
    });
});

describe('cloneChessInstance', () => {
    it('keeps move history and is independent of the source', () => {
        const game = new Chess();
        ['e4', 'e5', 'Nf3'].forEach((m) => game.move(m));
        const copy = cloneChessInstance(game);
        expect(copy.history()).toEqual(['e4', 'e5', 'Nf3']);
        copy.move('Nc6');
        expect(game.history()).toHaveLength(3);
    });
});

describe('prevIndexHelper', () => {
    it('maps the live view (-1) to the last move', () => {
        expect(prevIndexHelper(-1, 10)).toBe(9);
        expect(prevIndexHelper(4, 10)).toBe(4);
    });
});

describe('time controls', () => {
    it('groups popular presets into bullet/blitz/rapid/classical with the default among them', () => {
        expect(TIME_CONTROLS.map((g) => g.category)).toEqual(['bullet', 'blitz', 'rapid', 'classical']);
        const options = TIME_CONTROLS.flatMap((g) => g.options);
        expect(options).toContain(DEFAULT_TIME_CONTROL);
        options.forEach((opt) => expect(opt.category).toBe(
            TIME_CONTROLS.find((g) => g.options.includes(opt))?.category
        ));
    });
});

describe('a game from an arbitrary start position', () => {
    const BLACK_TO_MOVE = '6k1/5ppp/8/8/8/8/5PPP/3R2K1 b - - 0 40';

    it('customStartFen tells a custom position from the ordinary setup', () => {
        expect(customStartFen(new Chess())).toBeNull();
        expect(customStartFen(new Chess(STANDARD_START_FEN))).toBeNull();
        expect(customStartFen(new Chess(BLACK_TO_MOVE))).toBe(BLACK_TO_MOVE);
    });

    it('a game clone from a position keeps the start position and the moves', () => {
        const game = new Chess(BLACK_TO_MOVE);
        game.move('Kf8');
        const copy = cloneChessInstance(game);

        expect(copy.fen()).toBe(game.fen());
        expect(customStartFen(copy)).toBe(BLACK_TO_MOVE);
        copy.undo();
        expect(copy.fen()).toBe(BLACK_TO_MOVE);
    });

    it('validateFen rejects junk, impossible and finished positions', () => {
        expect(validateFen(BLACK_TO_MOVE)).toBeNull();
        expect(validateFen(`  ${BLACK_TO_MOVE}  `)).toBeNull();
        expect(validateFen('not a fen')).toMatch(/Invalid position/);
        expect(validateFen('8/8/8/8/8/8/8/8 w - - 0 1')).toMatch(/Invalid position/);
        expect(validateFen('k7/7Q/1K6/8/8/8/8/8 b - - 0 1')).toBeNull();
        expect(validateFen('k7/Q7/1K6/8/8/8/8/8 b - - 0 1')).toMatch(/already over/);  // mate
    });

    it('pairHalfMoves: an ordinary game', () => {
        const pairs = pairHalfMoves([{san: 'e4'}, {san: 'e5'}, {san: 'Nf3'}]);
        expect(pairs).toEqual([
            {moveNumber: 1, whiteSan: 'e4', whiteIdx: 0, blackSan: 'e5', blackIdx: 1},
            {moveNumber: 2, whiteSan: 'Nf3', whiteIdx: 2},
        ]);
    });

    it('pairHalfMoves: a game starting with Black\'s move on move 40', () => {
        const pairs = pairHalfMoves([{san: 'Kf8'}, {san: 'Rd8+'}, {san: 'Ke7'}], BLACK_TO_MOVE);
        expect(pairs).toEqual([
            {moveNumber: 40, whiteIdx: -1, blackSan: 'Kf8', blackIdx: 0},
            {moveNumber: 41, whiteSan: 'Rd8+', whiteIdx: 1, blackSan: 'Ke7', blackIdx: 2},
        ]);
    });

    it('pairHalfMoves: without moves and with a White move not from the first move', () => {
        expect(pairHalfMoves([], BLACK_TO_MOVE)).toEqual([]);
        expect(pairHalfMoves([{san: 'Qa7#'}], 'k7/7Q/1K6/8/8/8/8/8 w - - 0 57')).toEqual([
            {moveNumber: 57, whiteSan: 'Qa7#', whiteIdx: 0},
        ]);
    });
});

describe('time control: the group matches the rating category on the server', () => {
    // The same rule as src/services/rating.py: the duration estimate is the base + 40 moves × the increment.
    const serverCategory = (baseMinutes: number, incSeconds: number) => {
        const estimatedSeconds = baseMinutes * 60 + 40 * incSeconds;
        if (estimatedSeconds < 180) return 'bullet';
        if (estimatedSeconds < 480) return 'blitz';
        if (estimatedSeconds < 1500) return 'rapid';
        return 'classical';
    };

    it.each(TIME_CONTROLS.flatMap((group) => group.options.map((option) => [option.id, group.category, option] as const)))(
        '%s lies in the group of the category in which the rating will change',
        (_id, groupCategory, option) => {
            expect(option.category).toBe(groupCategory);
            expect(serverCategory(option.base, option.inc)).toBe(groupCategory);
        },
    );
});

describe('fittedBoardSize — the board by the window', () => {
    it('without a saved size — the largest that fits', () => {
        expect(fittedBoardSize(null, 640)).toBe(640);
        expect(fittedBoardSize('junk', 640)).toBe(640);
    });
    it('a saved size — but not larger than the window; the window grew — the board returns to the saved one', () => {
        expect(fittedBoardSize('560', 400)).toBe(400);
        expect(fittedBoardSize('560', 900)).toBe(560);
    });
    it('a too small saved size is not used', () => {
        expect(fittedBoardSize(String(MIN_BOARD_SIZE - 1), 640)).toBe(640);
    });
});
