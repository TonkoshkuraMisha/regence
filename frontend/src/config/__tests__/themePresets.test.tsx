// Theme sets (task 18.3): the parts exist, applying writes all settings, the preview draws a position.

import {render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';
import {THEME_PRESETS, applyPreset, findPreset, getSavedPresetId, presetIsValid} from '../themePresets';
import {getSavedBoardThemeKey, getSavedPieceSetKey} from '../boardAppearance';
import {getSavedPagePalette, getSavedPagePattern} from '../pageBackground';
import {SOUND_SETS, soundEngine} from '../../services/soundEngine';
import {ThemePreview} from '../../components/settings/ThemePreview';

afterEach(() => {
    localStorage.clear();
    soundEngine.setSoundSet('wood');
    document.body.removeAttribute('style');
});

describe('theme sets', () => {
    it('nine sets, different, all parts exist', () => {
        expect(THEME_PRESETS).toHaveLength(9);
        expect(new Set(THEME_PRESETS.map((p) => p.id)).size).toBe(9);
        for (const preset of THEME_PRESETS) {
            expect(presetIsValid(preset), preset.id).toBe(true);
            expect(SOUND_SETS[preset.sound], preset.id).toBeDefined();
        }
    });

    it('applying sets the board, pieces, background, sounds and remembers the set', () => {
        applyPreset(findPreset('study')!);
        expect(getSavedBoardThemeKey()).toBe('leather');
        expect(getSavedPieceSetKey()).toBe('mpchess');
        expect(getSavedPagePattern()).toBe('manuscript');
        expect(getSavedPagePalette()).toBe('parchment');
        expect(soundEngine.getSoundSet()).toBe('wood');
        expect(getSavedPresetId()).toBe('study');
        applyPreset(findPreset('night')!);
        expect(soundEngine.getSoundSet()).toBe('soft');
        expect(localStorage.getItem('regence_sound_set')).toBe('soft');
        expect(findPreset('nope')).toBeUndefined();
    });

    it('autumn park, a 1950s club and a chess school: their own board, pattern and palette (task 31.1)', () => {
        applyPreset(findPreset('autumn_park')!);
        expect([getSavedBoardThemeKey(), getSavedPagePattern(), getSavedPagePalette()]).toEqual(['autumn', 'leaves', 'autumn']);
        expect(document.body.style.backgroundImage).toContain('/assets/patterns/leaves.svg');
        applyPreset(findPreset('club_1950s')!);
        expect([getSavedBoardThemeKey(), getSavedPagePattern(), getSavedPagePalette()]).toEqual(['club50', 'parquet', 'bottle']);
        applyPreset(findPreset('chess_school')!);
        expect([getSavedBoardThemeKey(), getSavedPagePattern(), getSavedPagePalette()]).toEqual(['chalkboard', 'notebook', 'ink']);
    });

    it('the preview is a live position: 32 squares with pieces from the set\'s piece set', () => {
        render(<ThemePreview preset={findPreset('kids')!}/>);
        const images = screen.getByTestId('preview-kids').querySelectorAll('img');
        expect(images.length).toBe(32);
        expect(images[0].getAttribute('src')).toContain('/assets/pieces/totoy/');
    });
});
