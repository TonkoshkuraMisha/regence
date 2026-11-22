// --- FILE: frontend/src/services/__tests__/botGameSnapshot.test.ts ---
// Снимок партии с ботом: запись и чтение, чужой игрок, просрочка, испорченные данные, часы после перезагрузки.
import {beforeEach, describe, expect, it} from 'vitest';
import {
    SNAPSHOT_TTL_MS, clearBotGameSnapshot, clocksAfterGap, loadBotGameSnapshot, saveBotGameSnapshot,
} from '../botGameSnapshot';

const BASE = {
    username: 'Anna', botId: 'philidor', custom: null, color: 'white' as const, pgn: '1. e4 e5',
    whiteTimeMs: 300000, blackTimeMs: 290000, baseMinutes: 5, incrementSeconds: 0, odds: null,
    ladder: false, tournamentGameId: 7, tournamentId: 3,
};

describe('снимок партии с ботом', () => {
    beforeEach(() => localStorage.clear());

    it('записанный снимок читается тем же игроком', () => {
        saveBotGameSnapshot(BASE, 1000);
        expect(loadBotGameSnapshot('Anna', 2000)?.pgn).toBe('1. e4 e5');
    });

    it('чужой аккаунт снимок не получает и не стирает', () => {
        saveBotGameSnapshot(BASE, 1000);
        expect(loadBotGameSnapshot('Boris', 2000)).toBeNull();
        expect(loadBotGameSnapshot('Anna', 2000)).not.toBeNull();
    });

    it('просроченный и испорченный снимки стираются', () => {
        saveBotGameSnapshot(BASE, 1000);
        expect(loadBotGameSnapshot('Anna', 1000 + SNAPSHOT_TTL_MS + 1)).toBeNull();
        localStorage.setItem('regence_bot_game', '{не json');
        expect(loadBotGameSnapshot('Anna')).toBeNull();
        expect(localStorage.getItem('regence_bot_game')).toBeNull();
    });

    it('clear стирает снимок', () => {
        saveBotGameSnapshot(BASE, 1000);
        clearBotGameSnapshot();
        expect(loadBotGameSnapshot('Anna', 1500)).toBeNull();
    });

    it('часы того, чей ход, уменьшаются на время перезагрузки, но не ниже нуля', () => {
        const snap = {whiteTimeMs: 10000, blackTimeMs: 8000, savedAt: 1000};
        expect(clocksAfterGap(snap, true, 4000)).toEqual({white: 7000, black: 8000});
        expect(clocksAfterGap(snap, false, 4000)).toEqual({white: 10000, black: 5000});
        expect(clocksAfterGap(snap, true, 99000).white).toBe(0);
    });

    it('партия на паузе: часы при продолжении не уменьшаются', () => {
        const snap = {whiteTimeMs: 10000, blackTimeMs: 8000, savedAt: 1000, paused: true};
        expect(clocksAfterGap(snap, true, 99000)).toEqual({white: 10000, black: 8000});
        expect(clocksAfterGap(snap, false, 99000)).toEqual({white: 10000, black: 8000});
    });
});
