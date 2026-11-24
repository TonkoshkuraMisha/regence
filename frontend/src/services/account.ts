// --- FILE: frontend/src/services/account.ts ---
// Login, registration and the account: POST /api/v1/auth/login (OAuth2 form and the long-login refresh cookie),
// /auth/register, /auth/change-password (src/api/auth.py); email linking and unlinking, confirmation by link, password
// reset, data export, deletion and kid mode — /api/v1/account/* (src/api/account.py), restoring an account waiting for
// deletion — /auth/restore; the email address and profile flags —
// GET /profile/me. Used by AuthModal.tsx, Settings.tsx and EmailLinkPages.tsx. Request and errors — apiRequest (http.ts);
// storing the token is the caller's job (authToken.setToken).

import type {Language, UiMessage} from '../i18n';
import {apiRequest} from './http';

/** The player's own profile data needed by the settings page. */
export interface OwnAccount {
    id?: number;
    blitz_rating?: number;
    username?: string;
    email: string | null;
    translation_helper?: boolean;
    avatar?: string | null;
    /** Kid mode (task 23.1) and whether turning it off needs the guardian code. */
    kid_mode?: boolean;
    kid_guardian_code?: boolean;
}

/** Kid mode state after a change (POST /account/kid-mode). */
export interface KidModeState {
    kid_mode: boolean;
    kid_guardian_code: boolean;
}

/** Strength answers at registration (task 17.8): the server derives the starting rating from them; everything is optional. */
export interface RegisterRequest {
    username: string;
    password: string;
    experience?: string;
    strength?: string;
    invite_code?: string;
    /** Consent to the community rules and privacy policy (task 23.1). */
    accept_terms: boolean;
    /** A player under 16 (task 23.1): only with a guardian's consent and code; the account starts in kid mode. */
    under_16?: boolean;
    guardian_consent?: boolean;
    guardian_code?: string;
}

/** Response of login and password change: the new access token. */
interface TokenResponse {
    access_token: string;
}

/** POST with a JSON body. */
const post = (body: unknown, init: RequestInit = {}): RequestInit => ({method: 'POST', body: JSON.stringify(body), ...init});

/** HTTP 429: login attempt limit exceeded. */
const TOO_MANY_REQUESTS = 429;

/** The login form (OAuth2) to /auth/login or /auth/restore; returns the access token, the browser stores the refresh cookie. */
async function signInAt(path: '/auth/login' | '/auth/restore', username: string, password: string): Promise<string> {
    const form = new URLSearchParams({username, password});
    const data = await apiRequest<TokenResponse>(path, {
        method: 'POST', body: form, credentials: 'include',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    },
        (status) => (status === TOO_MANY_REQUESTS ? 'auth.tooManyAttempts' : 'auth.wrongCredentials'));
    return data.access_token;
}

export const accountApi = {
    /**
     * Login by name and password. 429 without a server code — «too many attempts»; an account waiting for deletion —
     * the code account_deletion_pending (the caller offers restore).
     */
    login: (username: string, password: string) => signInAt('/auth/login', username, password),
    /** Cancel a requested account deletion during the grace period and log in (task 23.1). */
    restore: (username: string, password: string) => signInAt('/auth/restore', username, password),
    register: (request: RegisterRequest) =>
        apiRequest<{ blitz_rating: number }>('/auth/register', post(request), 'auth.registrationFailed'),
    /** Changing the password revokes earlier sessions; returns a new token (and a new refresh cookie). */
    changePassword: async (currentPassword: string, newPassword: string): Promise<string> => {
        const data = await apiRequest<TokenResponse>('/auth/change-password',
            post({current_password: currentPassword, new_password: newPassword}, {credentials: 'include'}),
            'settings.passwordChangeFailed');
        return data.access_token;
    },
    me: () => apiRequest<OwnAccount>('/profile/me'),
    /** Link an email (the message with a link arrives in the player's language) or unlink it; the password is required. */
    linkEmail: (email: string, password: string, language: Language) =>
        apiRequest<unknown>('/account/email', post({email, password, language}), 'settings.emailFailed'),
    removeEmail: (password: string) => apiRequest<unknown>('/account/email/remove', post({password}), 'settings.emailFailed'),
    /** Confirm the email via the link from the message; returns the confirmed address. */
    verifyEmail: (token: string) =>
        apiRequest<{ email: string }>('/account/email/verify', post({token}), 'serverErrors.email_link_invalid'),
    requestPasswordReset: (email: string, language: Language) =>
        apiRequest<unknown>('/account/password-reset', post({email, language}), 'auth.resetFailed'),
    confirmPasswordReset: (token: string, newPassword: string) =>
        apiRequest<unknown>('/account/password-reset/confirm', post({token, new_password: newPassword}),
            'serverErrors.email_link_invalid'),
    /** All of one's data as a single JSON (the right to export). */
    exportData: () => apiRequest<unknown>('/account/export', {}, 'settings.exportFailed'),
    /** Request deletion: the account closes at once and is erased after the grace period; returns that moment (ISO). */
    deleteAccount: (password: string) =>
        apiRequest<{ delete_after: string }>('/account/delete', post({password}), 'settings.deleteFailed'),
    /** Kid mode on (password, optional guardian code) or off (the guardian code if one is set, otherwise the password). */
    setKidMode: (enabled: boolean, secret: { password?: string; guardian_code?: string }) =>
        apiRequest<KidModeState>('/account/kid-mode', post({enabled, ...secret}), 'settings.kidModeFailed'),
};

/** Whether a refusal is «the account is waiting for deletion» (the login form then offers restore). */
export function isDeletionPending(ui: UiMessage): boolean {
    return 'key' in ui && ui.key === 'serverErrors.account_deletion_pending';
}
