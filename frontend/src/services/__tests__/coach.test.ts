// --- FILE: frontend/src/services/__tests__/coach.test.ts ---
// A mentor comment from the server → text in the player's language; unknown keys and wrong arrows are dropped.

import {describe, expect, it} from 'vitest';
import {makeI18n} from '../../i18n';
import {coachArrows, coachHighlights, coachSentences, coachText} from '../coach';

const COMMENT = {
    comment: [
        {key: 'coach.verdict.mistake.v1', params: {move: '♗c4'}},
        {key: 'coach.best.fork.v1', params: {move: '♘xf7', attacker: '♘f7', target1: '♛d8', target2: '♜h8'}},
    ],
    arrows: [
        {from: 'e5', to: 'f7', kind: 'best' as const},
        {from: 'f7', to: 'd8', kind: 'idea' as const},
        {from: 'f7', to: 'i9', kind: 'idea' as const},
        {from: 'a1', to: 'a2', kind: 'nonsense' as never},
    ],
    highlights: [{square: 'd8', kind: 'target'}, {square: 'x0', kind: 'target'}],
};

describe('mentor comment', () => {
    it('the text in both languages', () => {
        expect(coachText(COMMENT, makeI18n('uk').t))
            .toBe('♗c4 — помилка. Сильніше ♘xf7 з вилкою: ♘f7 нападає на ♛d8 і ♜h8.');
        expect(coachText(COMMENT, makeI18n('en').t))
            .toBe('♗c4 is a mistake. Stronger was ♘xf7 with a fork: ♘f7 attacks ♛d8 and ♜h8.');
    });

    it('unknown keys and junk are skipped, an empty comment — an empty text', () => {
        expect(coachSentences({comment: [{key: 'coach.unknown.v1'}, {key: 5 as never}]})).toEqual([]);
        expect(coachText(null, makeI18n('en').t)).toBe('');
        expect(coachSentences({comment: [{key: 'coach.best.generic.v2', params: {move: 'e4', junk: {} as never}}]}))
            .toEqual([{key: 'coach.best.generic.v2', params: {move: 'e4'}}]);
    });

    it('arrows and highlights — only valid fields and kinds', () => {
        expect(coachArrows(COMMENT)).toEqual([
            {from: 'e5', to: 'f7', kind: 'best'},
            {from: 'f7', to: 'd8', kind: 'idea'},
        ]);
        expect([...coachHighlights(COMMENT)]).toEqual(['d8']);
        expect(coachArrows(null)).toEqual([]);
    });
});
