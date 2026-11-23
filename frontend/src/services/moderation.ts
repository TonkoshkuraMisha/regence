// --- FILE: frontend/src/services/moderation.ts ---
// Moderation (task 17.4): reports, appeal, queue and moderator decisions.
// All requests go to /api/v1/moderation and only with login (routes src/api/moderation.py, rules —
// src/services/moderation.py). The queue and decisions are served only to a moderator; automation only creates tickets.

import {apiRequest} from './http';

/** Report reason: unfair play, insults, spam, other (REASONS on the server). */
export type ReportReason = 'cheating' | 'abuse' | 'spam' | 'other';
/**
 * Moderator decision (ACTIONS on the server): dismiss — reject; warn — warning; chat_ban — disable chat
 * for a day; mark_cheater / clear_cheater — confirm or remove the unfair play flag; accept — accept (a translation
 * fix); hide — remove the text; release — release what the filter held back.
 */
export type ModerationAction = 'dismiss' | 'warn' | 'chat_ban' | 'mark_cheater' | 'clear_cheater' | 'accept' | 'hide' | 'release';

/** Ticket in the moderator queue (GET /moderation/queue). */
export interface QueueItem {
    id: number;
    /**
     * player and message — a report on a player or a game chat message; cheat_review — anti-cheat flag review;
     * appeal — appeal; translation — translation fix; content — a report on a direct message, post or
     * comment; held — text held back by the filter.
     */
    kind: 'player' | 'message' | 'cheat_review' | 'appeal' | 'translation' | 'content' | 'held';
    reason: string;
    comment: string | null;
    /** Copy of the text being reported (saved at the moment of the report). */
    message_text: string | null;
    /** For translation: "language:key" and page. */
    subject?: string | null;
    context?: string | null;
    game_id: number | null;
    created_at: string | null;
    reporter: string | null;
    target: string | null;
    /** Information about the player the ticket is about: anti-cheat flag, trust factor (users.trust_factor), number of reports. */
    target_is_cheater: boolean;
    target_trust: number | null;
    reports_on_target: number;
}

/** State of the player themself (GET /moderation/me): role, unfair play flag, open appeal, chat ban. */
export interface ModerationMe {
    is_moderator: boolean;
    is_cheater: boolean;
    open_appeal: boolean;
    /** Until when chat is disabled (ISO); null — chat is not disabled. */
    chat_banned_until: string | null;
}

/** Request to /api/v1/moderation via the common http.ts wrapper (token, JSON, errors). */
const call = <T>(path: string, init: RequestInit = {}) => apiRequest<T>(`/moderation${path}`, init);

/** Summary of violations over 30 days (GET /moderation/summary, src/services/moderation_report.py). */
export interface ViolationsSummary {
    days: number;
    opened: number;
    resolved: number;
    open_now: number;
    oldest_open_hours: number | null;
    by_kind: Record<string, number>;
    by_action: Record<string, number>;
    cheaters: number;
    top_targets: { username: string; reports: number }[];
}

export const moderationApi = {
    me: () => call<ModerationMe>('/me'),
    /** Report on a player or on a game chat message (message_text — a copy of the message). */
    report: (body: { target: string; kind: 'player' | 'message'; reason: ReportReason; comment?: string; message_text?: string; game_id?: number | null }) =>
        call<{ id: number }>('/reports', {method: 'POST', body: JSON.stringify(body)}),
    /** Translation fix from "translation helper" mode: catalog key, current text and the proposed one. */
    suggestTranslation: (body: { language: string; key: string; current: string; suggestion: string; context: string }) =>
        call<{ id: number }>('/translations', {method: 'POST', body: JSON.stringify(body)}),
    /** Appeal against an unfair play flag (one open per player). */
    appeal: (comment: string) => call<{ id: number }>('/appeal', {method: 'POST', body: JSON.stringify({comment})}),
    queue: () => call<{ reports: QueueItem[] }>('/queue'),
    summary: () => call<ViolationsSummary>('/summary'),
    /** Report on a message, post or comment (task 30.3): subject — "dm:12", "post:5", "comment:7". */
    reportText: (subject: string, reason: ReportReason) =>
        call<{ id: number }>('/reports/text', {method: 'POST', body: JSON.stringify({subject, reason})}),
    resolve: (id: number, action: ModerationAction) =>
        call<{ id: number; action: string }>(`/reports/${id}/resolve`, {method: 'POST', body: JSON.stringify({action})}),
};
