// Migrating settings on renaming the platform michess → Regence: old keys move over, new ones are not overwritten.

import {afterEach, describe, expect, it} from 'vitest';
import {migrateLegacyStorage, migrateStorage} from '../storageMigration';

afterEach(() => {
    localStorage.clear();
    sessionStorage.clear();
});

describe('migrating michess_ → regence_ settings', () => {
    it('old keys move over and are deleted; an already set new one is not overwritten; foreign ones are untouched', () => {
        localStorage.setItem('michess_board_theme', 'walnut');
        localStorage.setItem('michess_language', 'uk');
        localStorage.setItem('regence_language', 'en');
        localStorage.setItem('other_key', 'x');
        expect(migrateStorage(localStorage)).toBe(1);
        expect(localStorage.getItem('regence_board_theme')).toBe('walnut');
        expect(localStorage.getItem('regence_language')).toBe('en');
        expect(localStorage.getItem('michess_board_theme')).toBeNull();
        expect(localStorage.getItem('michess_language')).toBeNull();
        expect(localStorage.getItem('other_key')).toBe('x');
        expect(migrateStorage(localStorage)).toBe(0);  // a second run does nothing
    });

    it('both storages at startup', () => {
        sessionStorage.setItem('michess_xray_modes', '[]');
        migrateLegacyStorage();
        expect(sessionStorage.getItem('regence_xray_modes')).toBe('[]');
    });
});
