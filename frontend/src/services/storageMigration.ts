// --- FILE: frontend/src/services/storageMigration.ts ---
// Platform rename michess → Regence (owner decision 18.11.2026): the player's browser settings (theme and
// board size, piece set, language, sound, mentor, x-ray, import nicknames, etc.) were stored under "michess_…" keys.
// Once at startup each such key is moved to "regence_…" (if the new one does not exist yet) and removed — the player does not
// lose settings. Storage errors (private mode, denied access) do not block startup. Called from src/main.tsx.

/** Old and new storage key prefixes. */
export const LEGACY_PREFIX = 'michess_';
export const CURRENT_PREFIX = 'regence_';

/** Moves LEGACY_PREFIX keys to CURRENT_PREFIX within one storage; returns the number moved. */
export function migrateStorage(storage: Storage): number {
    const legacy: string[] = [];
    for (let i = 0; i < storage.length; i++) {
        const key = storage.key(i);
        if (key?.startsWith(LEGACY_PREFIX)) legacy.push(key);
    }
    let moved = 0;
    for (const key of legacy) {
        const next = CURRENT_PREFIX + key.slice(LEGACY_PREFIX.length);
        const value = storage.getItem(key);
        if (value !== null && storage.getItem(next) === null) {
            storage.setItem(next, value);
            moved += 1;
        }
        storage.removeItem(key);
    }
    return moved;
}

/** localStorage and sessionStorage; an unavailable storage is skipped. */
export function migrateLegacyStorage(): void {
    for (const pick of [() => window.localStorage, () => window.sessionStorage]) {
        try {
            migrateStorage(pick());
        } catch {
            // storage unavailable — nothing to migrate
        }
    }
}
