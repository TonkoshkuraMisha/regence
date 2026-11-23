// --- FILE: frontend/src/config/unlocks.ts ---
// Unlockable appearance (task 18.4): some boards and piece sets unlock for achievements (17.6). Locked items are visible
// in advance - with a lock and the condition; they cannot be selected until the achievement is earned. Already selected items are not taken away.

import {useSyncExternalStore} from 'react';
import {API_BASE_URL} from './api';
import {t} from '../i18n';
import type {MessageKey} from '../i18n';

export type UnlockKind = 'board' | 'pieces';

/** Which achievement unlocks what (codes - src/services/achievements.py). */
export const UNLOCKS: Record<UnlockKind, Record<string, string>> = {
    board: {marble: 'wins_10', malachite: 'puzzles_100', ebony: 'rating_1500', neon: 'arena_10', stained: 'tournament_podium'},
    pieces: {lewis: 'tournament_win', firi: 'lessons_10'},
};

let earned = new Set<string>();
const listeners = new Set<() => void>();
let snapshot = earned;

function publish(next: Set<string>): void {
    earned = next;
    snapshot = next;
    listeners.forEach((listener) => listener());
}

/** Load the player's earned achievements (called on sign-in); a guest gets an empty set. */
export async function loadUnlocks(username: string | null): Promise<void> {
    if (!username) {
        publish(new Set());
        return;
    }
    try {
        const res = await fetch(`${API_BASE_URL}/api/v1/profile/${encodeURIComponent(username)}/achievements`);
        if (!res.ok) return;
        const data = await res.json() as { achievements?: { code: string; earned_at: string | null }[] };
        publish(new Set((data.achievements ?? []).filter((a) => a.earned_at).map((a) => a.code)));
    } catch {
        // No connection - the appearance stays as it was (locked stays locked).
    }
}

export function setEarnedForTests(codes: string[]): void {
    publish(new Set(codes));
}

/** Code of the achievement that unlocks the item if not yet earned; otherwise null. */
export function lockOf(kind: UnlockKind, id: string, have: Set<string> = earned): string | null {
    const code = UNLOCKS[kind][id];
    return code && !have.has(code) ? code : null;
}

function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

/** Hook: the lock-check function, updated when achievements have loaded. */
export function useUnlocks(): (kind: UnlockKind, id: string) => string | null {
    const have = useSyncExternalStore(subscribe, () => snapshot, () => snapshot);
    return (kind, id) => lockOf(kind, id, have);
}

/** "Unlocks for the achievement '...'" - the label of a locked item. */
export function unlockText(code: string): string {
    return t('settings.unlockBy', {name: t(`achievements.items.${code}.name` as MessageKey)});
}
