// Boards (task 18.1): coordinates are readable on every board (WCAG contrast ≥ 4.5), textures exist, names are in the catalogs.

import {existsSync, readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {describe, expect, it} from 'vitest';
import {BOARD_THEMES, DEFAULT_LAST_MOVE, lastMoveColor, textureLayerStyle} from '../boardAppearance';
import {CATALOGS, LANGUAGES} from '../../i18n';

function luminance(hex: string): number {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
        .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
}

const themes = Object.values(BOARD_THEMES);

describe('boards', () => {
    it('at least 22 boards, the id matches the key', () => {
        expect(themes.length).toBeGreaterThanOrEqual(22);
        for (const [key, theme] of Object.entries(BOARD_THEMES)) expect(theme.id).toBe(key);
    });

    it.each(themes.map((theme) => [theme.id, theme] as const))('%s: coordinates contrast with the square (WCAG ≥ 4.5)', (_id, theme) => {
        expect(contrast(theme.coordLight, theme.light)).toBeGreaterThanOrEqual(4.5);
        expect(contrast(theme.coordDark, theme.dark)).toBeGreaterThanOrEqual(4.5);
    });

    it('every board has a name in both languages', () => {
        for (const language of LANGUAGES) {
            const names = CATALOGS[language].appearance.themes as Record<string, string>;
            for (const theme of themes) expect(names[theme.id], `${language}: ${theme.id}`).toBeTruthy();
        }
    });

    it('texture files are in place', () => {
        for (const theme of themes) {
            if (theme.texture) expect(existsSync(resolve(__dirname, '../../../public/assets/textures', theme.texture.file)), theme.id).toBe(true);
        }
    });

    it('texture layer: the blend mode, a frame without a layer at 0, hatching only on dark squares', () => {
        expect(textureLayerStyle(BOARD_THEMES.walnut, 'frame')).toMatchObject({opacity: 0.25, mixBlendMode: 'multiply'});
        expect(textureLayerStyle(BOARD_THEMES.glass, 'square')?.mixBlendMode).toBe('screen');
        expect(textureLayerStyle(BOARD_THEMES.maple, 'square')).toBeNull();
        expect(textureLayerStyle(BOARD_THEMES.newspaper, 'frame')).toBeNull();
        expect(textureLayerStyle(BOARD_THEMES.newspaper, 'square', false)).toBeNull();
        expect(textureLayerStyle(BOARD_THEMES.newspaper, 'square', true)?.backgroundImage).toContain('hatch.svg');
        expect(lastMoveColor(BOARD_THEMES.maple)).toBe(DEFAULT_LAST_MOVE);
        expect(lastMoveColor(BOARD_THEMES.neon)).not.toBe(DEFAULT_LAST_MOVE);
    });
});

describe('square focus ring (task 26.3, WCAG 1.4.11)', () => {
    // The ring is two-coloured — black and white (index.css, .board-square:focus-visible): on any square of any theme at least
    // one colour must differ from the square with a contrast of at least 3:1, otherwise the keyboard focus is not visible.
    const RING = ['#000000', '#FFFFFF'];
    const MIN_NON_TEXT_CONTRAST = 3;

    it.each(themes.map((theme) => [theme.id, theme] as const))('%s: the ring is visible on a light and a dark square', (_id, theme) => {
        for (const square of [theme.light, theme.dark]) {
            expect(Math.max(...RING.map((ring) => contrast(ring, square)))).toBeGreaterThanOrEqual(MIN_NON_TEXT_CONTRAST);
        }
    });

    it('the ring style is two colours', () => {
        const css = readFileSync(resolve(__dirname, '../../index.css'), 'utf8');
        const rule = css.slice(css.indexOf('.board-square:focus-visible'));
        for (const ring of RING) expect(rule).toContain(ring);
    });
});
