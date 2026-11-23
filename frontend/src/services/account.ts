// --- FILE: frontend/src/services/account.ts ---
// Login, registration and the account: POST /api/v1/auth/login (OAuth2 form and the long-login refresh cookie),
// /auth/register, /auth/change-password (src/api/auth.py); email linking and unlinking, confirmation by link, password
// reset, data export and deletion — /api/v1/account/* (src/api/account.py); the email address and profile flags —
// GET /profile/me. Used by AuthModal.tsx, Settings.tsx and EmailLinkPages.tsx. Request and errors — apiRequest (http.ts);
// storing the token is the caller's job (authToken.setToken).

import type {Language} from '../i18n';
import {apiRequest} from './http';

/** The player's own profile data needed by the settings page. */
export interface OwnAccount {
    id?: number;
    blitz_rating?: number;
    username?: string;
    email: string | null;
    translation_helper?: boolean;
    avatar?: string | null;
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
}

/** Response of login and password change: the new access token. */
interface TokenResponse {
    access_token: string;
}

/** POST with a JSON body. */
const post = (body: unknown, init: RequestInit = {}): RequestInit => ({method: 'POST', body: JSON.stringify(body), ...init});

/** HTTP 429: login attempt limit exceeded. */
const TOO_MANY_REQUESTS = 429;

export const accountApi = {
    /** Login by name and password; the browser stores the refresh cookie. 429 without a server code — «too many attempts». */
    login: async (username: string, password: string): Promise<string> => {
        const form = new URLSearchParams({username, password});
        const data = await apiRequest<TokenResponse>('/auth/login', {
            method: 'POST', body: form, credentials: 'include',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        },
            (status) => (status === TOO_MANY_REQUESTS ? 'auth.tooManyAttempts' : 'auth.wrongCredentials'));
        return data.access_token;
    },
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
    deleteAccount: (password: string) => apiRequest<unknown>('/account/delete', post({password}), 'settings.deleteFailed'),
};
