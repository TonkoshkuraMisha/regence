// Page background (task 18.1): the pattern and the palette are applied to the page and remembered; an unknown one — to the defaults.

import {existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {afterEach, describe, expect, it} from 'vitest';
import {PAGE_PATTERNS, applyPageBackground, getSavedPagePalette, getSavedPagePattern, pageBackgroundStyle} from '../pageBackground';

afterEach(() => {
    localStorage.clear();
    document.body.removeAttribute('style');
});

describe('page background', () => {
    it('by default — no pattern, the colour of the club room', () => {
        expect(getSavedPagePattern()).toBe('none');
        expect(getSavedPagePalette()).toBe('room');
        expect(pageBackgroundStyle('none', 'room')).toEqual({backgroundColor: '#2C221C', backgroundImage: 'none'});
    });

    it('the choice is applied and remembered; junk in storage is ignored', () => {
        applyPageBackground('celtic', 'teal', true);
        expect(document.body.style.backgroundImage).toContain('/assets/patterns/celtic.svg');
        expect(getSavedPagePattern()).toBe('celtic');
        expect(getSavedPagePalette()).toBe('teal');
        localStorage.setItem('regence_page_pattern', 'unknown');
        localStorage.setItem('regence_page_palette', 'pink');
        expect(getSavedPagePattern()).toBe('none');
        expect(getSavedPagePalette()).toBe('room');
    });

    it('pattern files are in place', () => {
        for (const pattern of PAGE_PATTERNS.filter((p) => p !== 'none')) {
            expect(existsSync(resolve(__dirname, '../../../public/assets/patterns', `${pattern}.svg`)), pattern).toBe(true);
        }
    });
});
