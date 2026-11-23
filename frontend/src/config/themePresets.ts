// --- FILE: frontend/src/config/themePresets.ts ---
// Theme bundles (task 18.3): board (with frame) + pieces + hall background + sound set "in one click". A signed-in player stores
// the choice in the profile (it travels between devices), a guest - in the browser. Applying writes the same keys that
// the individual settings set, so any part of the bundle can be changed manually afterwards.

import {BOARD_THEMES, PIECE_SETS} from './boardAppearance';
import {applyPageBackground} from './pageBackground';
import type {PagePalette, PagePattern} from './pageBackground';
import {soundEngine} from '../services/soundEngine';
import type {SoundSetId} from '../services/soundEngine';

export type PresetId = 'club' | 'marble_hall' | 'study' | 'tournament' | 'night' | 'kids'
    | 'autumn_park' | 'club_1950s' | 'chess_school';

export interface ThemePreset {
    id: PresetId;
    board: string;
    pieces: string;
    pattern: PagePattern;
    palette: PagePalette;
    sound: SoundSetId;
}

export const THEME_PRESETS: ThemePreset[] = [
    {id: 'club', board: 'walnut', pieces: 'merida', pattern: 'none', palette: 'room', sound: 'wood'},
    {id: 'marble_hall', board: 'marble', pieces: 'celtic', pattern: 'marble', palette: 'teal', sound: 'marble'},
    {id: 'study', board: 'leather', pieces: 'mpchess', pattern: 'manuscript', palette: 'parchment', sound: 'wood'},
    {id: 'tournament', board: 'vinyl', pieces: 'cburnett', pattern: 'none', palette: 'room', sound: 'soft'},
    {id: 'night', board: 'ebony', pieces: 'spatial', pattern: 'celtic', palette: 'teal', sound: 'soft'},
    {id: 'kids', board: 'tournament', pieces: 'totoy', pattern: 'bauhaus', palette: 'room', sound: 'bright'},
    // Task 31.1 (owner's idea): autumn in a chess park, a fifties club hall, a school club.
    {id: 'autumn_park', board: 'autumn', pieces: 'cburnett', pattern: 'leaves', palette: 'autumn', sound: 'wood'},
    {id: 'club_1950s', board: 'club50', pieces: 'merida', pattern: 'parquet', palette: 'bottle', sound: 'wood'},
    {id: 'chess_school', board: 'chalkboard', pieces: 'merida', pattern: 'notebook', palette: 'ink', sound: 'soft'},
];

export const PRESET_STORAGE_KEY = 'regence_theme_preset';

export function findPreset(id: string | null | undefined): ThemePreset | undefined {
    return THEME_PRESETS.find((preset) => preset.id === id);
}

export function getSavedPresetId(): string | null {
    try {
        return localStorage.getItem(PRESET_STORAGE_KEY);
    } catch {
        return null;
    }
}

/** Apply a bundle: board, pieces, page background, sounds; remember in the browser. */
export function applyPreset(preset: ThemePreset): void {
    try {
        localStorage.setItem('regence_board_theme', preset.board);
        localStorage.setItem('regence_piece_set', preset.pieces);
        localStorage.setItem(PRESET_STORAGE_KEY, preset.id);
    } catch {
        // Storage unavailable - background and sound still change until reload.
    }
    applyPageBackground(preset.pattern, preset.palette, true);
    soundEngine.setSoundSet(preset.sound);
}

/** All parts of the bundle exist (checked by a test). */
export function presetIsValid(preset: ThemePreset): boolean {
    return Boolean(BOARD_THEMES[preset.board] && PIECE_SETS[preset.pieces]);
}
