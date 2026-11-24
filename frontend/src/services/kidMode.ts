// --- FILE: frontend/src/services/kidMode.ts ---
// Kid mode on the client (task 23.1; the rules are on the server, src/services/kid_mode.py). A small shared store like the
// translation helper (profileSettings.ts): App sets it from the profile (GET /profile/me, field kid_mode), the settings page
// after turning the mode on or off. Components read it with useKidMode() to hide what the server refuses anyway in kid
// mode: free-text game chat, messages, the feed and sharing to it, the study room chat.

import {useSyncExternalStore} from 'react';

let kidModeOn = false;
const listeners = new Set<() => void>();

/** Whether the signed-in player is in kid mode (false for a guest). */
export function isKidModeOn(): boolean {
    return kidModeOn;
}

/** Set the mode from the profile or after a change in the settings and notify subscribers. */
export function setKidModeOn(value: boolean): void {
    if (kidModeOn === value) return;
    kidModeOn = value;
    listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

/** React hook: the current kid mode flag, re-rendering when it changes. */
export function useKidMode(): boolean {
    return useSyncExternalStore(subscribe, isKidModeOn, isKidModeOn);
}
