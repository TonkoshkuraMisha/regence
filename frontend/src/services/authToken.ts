// --- FILE: frontend/src/services/authToken.ts ---
// Login token (task 17.5). The short-lived access token lives only in page memory — an injected script (XSS) will not find
// it in localStorage; the long login keeps the refresh token in an httpOnly cookie that JavaScript cannot see at all.
// On page load the session is restored from the cookie (restoreSession); a minute before expiry the token
// refreshes itself; a failed refresh means logout (the regence-auth-expired event).
// Server: POST /api/v1/auth/refresh and /auth/logout (src/api/auth.py), sessions — src/services/auth_sessions.py.
// The access token lifetime is set by the server (ACCESS_TOKEN_EXPIRE_MINUTES, 15 minutes); the client reads it from the token's exp field.

import {API_BASE_URL} from '../config/api';

/** localStorage key where the token lived in earlier versions; now it is only erased (dropLegacyToken). */
const LEGACY_STORAGE_KEY = 'token';
/** How long before the token expires a new one is requested. */
const REFRESH_AHEAD_MS = 60_000;
/**
 * window event: the token could not be refreshed (by the timer here or when issuing a WS ticket in gameSocket.ts).
 * The UI logout itself does not happen through it but through onTokenChange: on failure refreshSession sets the token to null,
 * and App.tsx learns about it by subscription. The app has no listeners of the event — only tests check it.
 */
export const AUTH_EXPIRED_EVENT = 'regence-auth-expired';

let current: string | null = null;
let refreshTimer: ReturnType<typeof setTimeout> | null = null;
let inFlight: Promise<string | null> | null = null;
const listeners = new Set<(token: string | null) => void>();

/** The token from earlier versions in localStorage is no longer used: it lived a day and was accessible to scripts. */
function dropLegacyToken(): void {
    try {
        localStorage.removeItem(LEGACY_STORAGE_KEY);
    } catch {
        // storage unavailable — nothing is stored anyway
    }
}

/** JWT expiry moment (ms) from the exp field; null — cannot be parsed. */
function expiresAt(token: string): number | null {
    try {
        const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
        return typeof payload.exp === 'number' ? payload.exp * 1000 : null;
    } catch {
        return null;
    }
}

/** Refresh timer: fires REFRESH_AHEAD_MS before the token expires, but no sooner than one second from now. */
function schedule(token: string | null): void {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = null;
    const exp = token ? expiresAt(token) : null;
    if (exp === null) return;
    refreshTimer = setTimeout(() => {
        void refreshSession().then((fresh) => {
            if (!fresh) window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
        });
    }, Math.max(1_000, exp - Date.now() - REFRESH_AHEAD_MS));
}

/** Current access token from page memory; null — the player is not logged in (or login is still being restored). */
export function getToken(): string | null {
    return current;
}

/** Remember the token (after login, registration or refresh), restart the timer and notify subscribers. */
export function setToken(token: string | null): void {
    current = token;
    schedule(token);
    listeners.forEach((listener) => listener(token));
}

/** Forget the token (logout, expired session). The server cookie is erased by logout(). */
export function clearToken(): void {
    setToken(null);
}

/** Subscribe to token changes (login, logout, refresh); returns an unsubscribe function. */
export function onTokenChange(listener: (token: string | null) => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

/** New access token via the refresh cookie; concurrent calls share one request. null — no session. */
export function refreshSession(): Promise<string | null> {
    if (!inFlight) {
        const before = current;
        inFlight = fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {method: 'POST', credentials: 'include'})
            .then(async (res) => (res.ok ? ((await res.json()).access_token as string) : null))
            .catch(() => null)
            .then((token) => {
                // The player may have logged in again while the request was running — a failure does not erase the fresh token.
                if (token) setToken(token);
                else if (current === before) setToken(null);
                return token;
            })
            .finally(() => {
                inFlight = null;
            });
    }
    return inFlight;
}

/** On page load: remove the old token from localStorage and restore login via the cookie. */
export function restoreSession(): Promise<string | null> {
    dropLegacyToken();
    return current ? Promise.resolve(current) : refreshSession();
}

/** Logout on this device: the session on the server is deleted, the token is forgotten. */
export async function logout(): Promise<void> {
    clearToken();  // the UI logs out immediately without waiting for the server
    try {
        await fetch(`${API_BASE_URL}/api/v1/auth/logout`, {method: 'POST', credentials: 'include'});
    } catch {
        // without a network the server session will expire on its own; locally the logout is already done
    }
}
