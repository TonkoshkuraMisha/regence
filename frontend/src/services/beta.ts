// --- FILE: frontend/src/services/beta.ts ---
// Beta program (task 24.4): site settings (whether registration is closed, community link, version), invite
// code checking, «Report a problem» and the moderator's work with invites and reports.
// All requests go to /api/v1/beta (routes in src/api/beta.py, rules — src/services/beta.py). Without login the following are available:
// /config, /invites/check and sending a report (POST /feedback); the rest the server gives only to a moderator.

import {useEffect, useSyncExternalStore} from 'react';
import {apiRequest} from './http';

/** Site settings (GET /beta/config), parsed by parseConfig: values come from the server settings. */
export interface SiteConfig {
    /** Registration only with an invite code. */
    inviteOnly: boolean;
    /** Link to the community channel; null — not set, and the site has none. */
    communityUrl: string | null;
    /** Application version on the server (settings.VERSION). */
    version: string | null;
}

/** Invite state computed by the server: active, revoked, expired, usage count exhausted. */
export type InviteState = 'active' | 'revoked' | 'expired' | 'used_up';

/** Invite code in the moderator's list (GET /beta/invites). */
export interface Invite {
    id: number;
    code: string;
    /** Moderator's note «for whom» — not shown to players. */
    note: string | null;
    /** How many times the code can be used; null — unlimited. */
    max_uses: number | null;
    uses: number;
    expires_at: string | null;
    revoked_at: string | null;
    created_at: string | null;
    state: InviteState;
}

/** Problem report statuses — the same ones the server checks (FeedbackStatusIn in src/api/beta.py). */
export const FEEDBACK_STATUSES = ['new', 'in_progress', 'done', 'rejected'] as const;
export type FeedbackStatus = typeof FEEDBACK_STATUSES[number];

/** Problem report in the moderator's queue: the text and what the client attached on sending (sendFeedback). */
export interface FeedbackItem {
    id: number;
    message: string;
    /** Path of the page the report was sent from. */
    page: string | null;
    app_version: string | null;
    language: string | null;
    /** Browser window size «width x height» (screenSize). */
    screen: string | null;
    status: FeedbackStatus;
    /** Player name; null — the report is from a guest. */
    author: string | null;
    created_at: string | null;
    updated_at: string | null;
}

/** Report queue (GET /beta/feedback): the reports and the number of reports in each status. */
export interface FeedbackQueue {
    items: FeedbackItem[];
    counts: Record<FeedbackStatus, number>;
}

/** Request to /api/v1/beta through the shared http.ts wrapper (token, JSON, errors). */
const call = <T>(path: string, init: RequestInit = {}) => apiRequest<T>(`/beta${path}`, init);

/** Browser window size («390x844»): shows on which screen the layout broke. */
export function screenSize(): string {
    return `${Math.round(window.innerWidth)}x${Math.round(window.innerHeight)}`;
}

/** Invite link: opens the site straight on the registration form with the code filled in. */
export function inviteLink(code: string): string {
    return `${window.location.origin}/?invite=${encodeURIComponent(code)}`;
}

/** Beta endpoints. checkInvite and sendFeedback work without login; the rest — moderator only. */
export const betaApi = {
    /** Whether the code is valid (a hint in the registration form); the code itself is not consumed by the check. */
    checkInvite: (code: string) =>
        call<{ valid: boolean }>(`/invites/check?code=${encodeURIComponent(code)}`).then((r) => r.valid === true),
    /** page — only the page path: URL parameters may hold one-time links (password reset, invite). */
    sendFeedback: (body: { message: string; page: string; language: string; screen: string }) =>
        call<{ id: number }>('/feedback', {method: 'POST', body: JSON.stringify(body)}),
    /** Personal code for inviting friends and how many people came through it (GET /beta/my-invite). */
    myInvite: () => call<{ code: string; uses: number; max_uses: number | null; state: InviteState }>('/my-invite'),
    invites: () => call<{ invite_only?: boolean; invites?: Invite[] }>('/invites'),
    createInvite: (body: { note?: string; max_uses?: number; expires_in_days?: number }) =>
        call<Invite>('/invites', {method: 'POST', body: JSON.stringify(body)}),
    revokeInvite: (id: number) => call<Invite>(`/invites/${id}/revoke`, {method: 'POST'}),
    feedback: (status?: FeedbackStatus) =>
        call<Partial<FeedbackQueue>>(`/feedback${status ? `?status=${status}` : ''}`),
    setFeedbackStatus: (id: number, status: FeedbackStatus) =>
        call<{ id: number; status: FeedbackStatus }>(`/feedback/${id}/status`, {method: 'POST', body: JSON.stringify({status})}),
};

// --- site settings: one request per tab ---------------------------------------------------------------------

const DEFAULT_CONFIG: SiteConfig = {inviteOnly: false, communityUrl: null, version: null};
let config: SiteConfig = DEFAULT_CONFIG;
let pending: Promise<SiteConfig> | null = null;
const listeners = new Set<() => void>();

function parseConfig(raw: unknown): SiteConfig {
    const data = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
    const url = typeof data.community_url === 'string' && /^https?:\/\//.test(data.community_url) ? data.community_url : null;
    return {
        inviteOnly: data.invite_only === true,
        communityUrl: url,
        version: typeof data.version === 'string' ? data.version : null,
    };
}

/** Site settings from the server. Without a network or on error — defaults: registration open, no link. */
export function loadSiteConfig(): Promise<SiteConfig> {
    pending ??= (async () => {
        try {
            config = parseConfig(await apiRequest<unknown>('/beta/config'));
            listeners.forEach((notify) => notify());
        } catch {
            // the defaults remain
        }
        return config;
    })();
    return pending;
}

function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

/** Hook: site settings. Until the server responds — defaults; one request per tab for all hooks. */
export function useSiteConfig(): SiteConfig {
    const current = useSyncExternalStore(subscribe, () => config, () => config);
    useEffect(() => {
        void loadSiteConfig();
    }, []);
    return current;
}

/** Tests only: forget the loaded settings. */
export function resetSiteConfig(): void {
    config = DEFAULT_CONFIG;
    pending = null;
}

/** Community platform by link address — for the label. */
export function communityPlatform(url: string): 'telegram' | 'discord' | 'generic' {
    let host = '';
    try {
        host = new URL(url).hostname.toLowerCase();
    } catch {
        return 'generic';
    }
    if (host === 't.me' || host === 'telegram.me' || host.endsWith('.t.me')) return 'telegram';
    if (host === 'discord.gg' || host === 'discord.com' || host.endsWith('.discord.com')) return 'discord';
    return 'generic';
}
