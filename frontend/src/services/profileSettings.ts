// --- FILE: frontend/src/services/profileSettings.ts ---
// Profile settings on the server (task 17.7): interface language, "translation helper" mode, theme preset and avatar —
// PATCH /api/v1/profile/me/settings (src/api/profile.py, columns of the users table). They are read together with the profile
// (GET /profile/me in App.tsx). The translation-mode flag is a small shared store: App sets it from the profile and
// the settings page toggles it.

import {API_BASE_URL} from '../config/api';
import type {Language} from '../i18n';
import {getToken} from './authToken';

/** Profile settings as the server returns them after saving. */
export interface ProfileSettings {
    language: Language | null;
    translation_helper: boolean;
    /** Theme preset key (config/themePresets.ts). */
    theme_preset: string | null;
    /** Avatar — piece code and background number of the form "wN-3" (the server validates the format). */
    avatar: string | null;
}

/**
 * Save part of the settings: the server changes only the fields sent and returns all four. null — the player is not signed in or
 * the server refused (the reason for refusal is not parsed).
 */
export async function saveProfileSettings(body: Partial<ProfileSettings>): Promise<ProfileSettings | null> {
    const token = getToken();
    if (!token) return null;
    const res = await fetch(`${API_BASE_URL}/api/v1/profile/me/settings`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json', Authorization: `Bearer ${token}`},
        body: JSON.stringify(body),
    });
    return res.ok ? res.json() as Promise<ProfileSettings> : null;
}

let helperOn = false;
const listeners = new Set<() => void>();

/** Whether the "translation helper" mode is on (in-page memory value, not localStorage). */
export function isTranslationHelperOn(): boolean {
    return helperOn;
}

/** Toggle the mode and notify subscribers; the caller sends the value to the server (saveProfileSettings). */
export function setTranslationHelper(value: boolean): void {
    if (helperOn === value) return;
    helperOn = value;
    listeners.forEach((listener) => listener());
}

/** Subscribe to mode toggling (for useSyncExternalStore); returns the unsubscribe function. */
export function subscribeTranslationHelper(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}
