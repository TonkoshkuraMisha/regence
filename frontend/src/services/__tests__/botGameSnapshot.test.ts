// --- FILE: frontend/src/services/__tests__/botGameSnapshot.test.ts ---
// A bot game snapshot: writing and reading, another player, expiry, corrupted data, the clock after a reload.
import {beforeEach, describe, expect, it} from 'vitest';
import {
    SNAPSHOT_TTL_MS, clearBotGameSnapshot, clocksAfterGap, loadBotGameSnapshot, saveBotGameSnapshot,
} from '../botGameSnapshot';

const BASE = {
    username: 'Anna', botId: 'philidor', custom: null, color: 'white' as const, pgn: '1. e4 e5',
    whiteTimeMs: 300000, blackTimeMs: 290000, baseMinutes: 5, incrementSeconds: 0, odds: null,
    ladder: false, tournamentGameId: 7, tournamentId: 3,
};

describe('bot game snapshot', () => {
    beforeEach(() => localStorage.clear());

    it('a written snapshot is read by the same player', () => {
        saveBotGameSnapshot(BASE, 1000);
        expect(loadBotGameSnapshot('Anna', 2000)?.pgn).toBe('1. e4 e5');
    });

    it('another account neither gets nor erases the snapshot', () => {
        saveBotGameSnapshot(BASE, 1000);
        expect(loadBotGameSnapshot('Boris', 2000)).toBeNull();
        expect(loadBotGameSnapshot('Anna', 2000)).not.toBeNull();
    });

    it('an expired and a corrupted snapshot are erased', () => {
        saveBotGameSnapshot(BASE, 1000);
        expect(loadBotGameSnapshot('Anna', 1000 + SNAPSHOT_TTL_MS + 1)).toBeNull();
        localStorage.setItem('regence_bot_game', '{not json');
        expect(loadBotGameSnapshot('Anna')).toBeNull();
        expect(localStorage.getItem('regence_bot_game')).toBeNull();
    });

    it('clear erases the snapshot', () => {
        saveBotGameSnapshot(BASE, 1000);
        clearBotGameSnapshot();
        expect(loadBotGameSnapshot('Anna', 1500)).toBeNull();
    });

    it('the clock of the side to move decreases by the reload time, but not below zero', () => {
        const snap = {whiteTimeMs: 10000, blackTimeMs: 8000, savedAt: 1000};
        expect(clocksAfterGap(snap, true, 4000)).toEqual({white: 7000, black: 8000});
        expect(clocksAfterGap(snap, false, 4000)).toEqual({white: 10000, black: 5000});
        expect(clocksAfterGap(snap, true, 99000).white).toBe(0);
    });

    it('a game on pause: the clock does not decrease on resume', () => {
        const snap = {whiteTimeMs: 10000, blackTimeMs: 8000, savedAt: 1000, paused: true};
        expect(clocksAfterGap(snap, true, 99000)).toEqual({white: 10000, black: 8000});
        expect(clocksAfterGap(snap, false, 99000)).toEqual({white: 10000, black: 8000});
    });
});
