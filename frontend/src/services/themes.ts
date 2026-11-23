// --- FILE: frontend/src/services/themes.ts ---
// Tactical theme registry (task 13.0): codes, sections and parents — from the server (GET /api/v1/themes), names and
// explanations — from the catalogs (themes.<code>.name / .short / .explain) in the player's language.
// Source of truth — src/services/themes.py (theme descriptions — docs/training/tactical-themes.md); route —
// src/api/themes.py, open without sign-in.

import {API_BASE_URL} from '../config/api';
import {hasMessage, uiMessage} from '../i18n';
import type {I18n} from '../i18n';
import {UiError} from './apiErrors';

/** Sections A–L of the tactics catalog; section names are in the translation catalog. */
export type ThemeSection = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G' | 'H' | 'I' | 'J' | 'K' | 'L';
/** Which theme text is needed: name, short or detailed explanation. */
export type ThemeTextPart = 'name' | 'short' | 'explain';

/** Registry theme as the server returns it. */
export interface ThemeInfo {
    /** Immutable theme code — the key in the puzzle database, in the player's progress and in the text catalog. */
    code: string;
    section: ThemeSection;
    /** Parent theme code (e.g. for fork kinds the parent is fork); null — a top-level theme. */
    parent: string | null;
    /** How the theme's puzzles are labeled: D — motif detector, L — open puzzle database tag, M — manual labeling. */
    sources: ('D' | 'L' | 'M')[];
    /** How many puzzles are needed at each of the four stages for the theme to be issued "by theme". */
    minimums: [number, number, number, number];
}

/** Response of GET /api/v1/themes: sections and themes in catalog order. */
export interface ThemeRegistry {
    sections: ThemeSection[];
    themes: ThemeInfo[];
}

let cached: Promise<ThemeRegistry> | null = null;

/**
 * Theme registry: one request per tab (the result is cached); after an error the next call goes to the network again.
 * Themes for which the client has no texts yet (the server is newer) are dropped.
 */
export function fetchThemeRegistry(): Promise<ThemeRegistry> {
    if (!cached) {
        cached = fetch(`${API_BASE_URL}/api/v1/themes`)
            .then((res) => {
                if (!res.ok) throw new UiError(uiMessage('common.networkError'));
                return res.json() as Promise<ThemeRegistry>;
            })
            .then((registry) => ({...registry, themes: registry.themes.filter((theme) => isKnownTheme(theme.code))}))
            .catch((err) => {
                cached = null;
                throw err;
            });
    }
    return cached;
}

/** For tests: reset the cached registry. */
export function resetThemeRegistryCache(): void {
    cached = null;
}

/** The theme is known to the client (texts exist): a new server theme without texts is not shown by an old client. */
export function isKnownTheme(code: string): boolean {
    return /^[a-z][a-z0-9_]*$/.test(code) && hasMessage(`themes.${code}.name`);
}

/** Name, short or detailed explanation of a theme in the player's language; an unknown theme — its code. */
export function themeText(code: string, part: ThemeTextPart, t: I18n['t']): string {
    const key = `themes.${code}.${part}`;
    return hasMessage(key) ? t(key as never) : code;
}

/** Themes of a section in registry order. */
export function themesOfSection(registry: ThemeRegistry, section: ThemeSection): ThemeInfo[] {
    return registry.themes.filter((theme) => theme.section === section);
}

/** Child themes (e.g. fork kinds). */
export function childThemes(registry: ThemeRegistry, code: string): ThemeInfo[] {
    return registry.themes.filter((theme) => theme.parent === code);
}
