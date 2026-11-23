// --- FILE: frontend/src/services/__tests__/gameDates.test.ts ---
// A game date for lists and the viewer (services/gameDates.ts): unknown parts of a PGN date are removed, an unknown
// year — there is no PGN date, then the game end time is taken; nothing — null (the text is chosen by the caller).

import {describe, expect, it} from 'vitest';
import {enUS} from 'date-fns/locale';
import {gameDisplayDate, pgnDisplayDate} from '../gameDates';

describe('game date', () => {
    it('PGN: an unknown month and day are removed', () => {
        expect(pgnDisplayDate('1860.??.??')).toBe('1860');
        expect(pgnDisplayDate('1972.07.??')).toBe('1972.07');
        expect(pgnDisplayDate('2024.03.15')).toBe('2024.03.15');
    });

    it('PGN: an unknown year or an empty date — no date', () => {
        expect(pgnDisplayDate('????.??.??')).toBeNull();
        expect(pgnDisplayDate(null)).toBeNull();
        expect(pgnDisplayDate('')).toBeNull();
    });

    it('without a date in the PGN — the game end time in the player\'s language', () => {
        expect(gameDisplayDate('????.??.??', '2026-11-19T12:00:00Z', enUS)).toBe('19 Nov 2026');
        expect(gameDisplayDate(null, '2026-11-19T12:00:00Z', enUS)).toBe('19 Nov 2026');
    });

    it('a PGN date outweighs the end time; nothing — null', () => {
        expect(gameDisplayDate('1860.??.??', '2026-11-19T12:00:00Z', enUS)).toBe('1860');
        expect(gameDisplayDate(null, null, enUS)).toBeNull();
    });
});
