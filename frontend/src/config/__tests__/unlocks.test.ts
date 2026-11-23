// Unlockable styling (task 18.4): locks by earned achievements, a guest, network errors.

import {afterEach, describe, expect, it, vi} from 'vitest';
import {BOARD_THEMES, PIECE_SETS} from '../boardAppearance';
import {UNLOCKS, loadUnlocks, lockOf, setEarnedForTests, unlockText} from '../unlocks';
import {THEME_PRESETS} from '../themePresets';

afterEach(() => {
    vi.unstubAllGlobals();
    setEarnedForTests([]);
});

describe('unlockable styling', () => {
    it('locks are on existing boards and sets; some sets are open at once', () => {
        for (const id of Object.keys(UNLOCKS.board)) expect(BOARD_THEMES[id], id).toBeDefined();
        for (const id of Object.keys(UNLOCKS.pieces)) expect(PIECE_SETS[id], id).toBeDefined();
        const open = THEME_PRESETS.filter((p) => !lockOf('board', p.board) && !lockOf('pieces', p.pieces));
        expect(open.length).toBeGreaterThanOrEqual(4);
        expect(lockOf('board', 'walnut')).toBeNull();
        expect(unlockText('wins_10')).toBe('Unlocks with the achievement «Ten wins»');
    });

    it('loading: earned achievements remove the locks; a guest and a network failure — everything locked stays locked', async () => {
        vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
            ok: true, json: async () => ({
                achievements: [{code: 'wins_10', earned_at: '2026-11-15'}, {code: 'tournament_win', earned_at: null}],
            }),
            url,
        } as unknown as Response)));
        await loadUnlocks('alice');
        expect(String((fetch as unknown as { mock: { calls: string[][] } }).mock.calls[0][0])).toContain('/profile/alice/achievements');
        expect(lockOf('board', 'marble')).toBeNull();
        expect(lockOf('pieces', 'lewis')).toBe('tournament_win');
        await loadUnlocks(null);
        expect(lockOf('board', 'marble')).toBe('wins_10');
        vi.stubGlobal('fetch', vi.fn(async () => {
            throw new Error('offline');
        }));
        await loadUnlocks('alice');
        expect(lockOf('board', 'marble')).toBe('wins_10');
    });
});
