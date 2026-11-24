// --- FILE: frontend/src/services/social.ts ---
// Players and notifications (task 17.1): search, follows and "friends", who is online, direct challenge, notification center.
// All requests go to /api/v1/social and require sign-in (routes in src/api/social.py; notifications —
// src/services/notifications.py). Besides writing a new notification to the database, the server delivers it to open tabs over
// WebSocket — the list here is needed for the first load and in case an event did not arrive.

import {apiRequest} from './http';

/** A player in search results and in the follow list. */
export interface PlayerCard {
    username: string;
    online: boolean;
    blitz_rating: number;
    rapid_rating: number;
    /** Mutual follow; the field is present only in the follow list (GET /social/following). */
    friend?: boolean;
}

/** The viewer's relation to a player: whether they follow, whether the player follows them; together — "friends". */
export interface Relation {
    username: string;
    /** This is the viewer themselves. */
    self: boolean;
    following: boolean;
    followed_by: boolean;
    friends: boolean;
    online: boolean;
}

/** Notification kinds; the text is assembled on the client from the catalog by kind and payload fields. */
export type NotificationKind = 'challenge' | 'rematch' | 'tournament_round' | 'report_answer' | 'workout_reminder' | 'post_comment'
    | 'arena_reminder' | 'arena_podium' | 'weekly_legends';

/** A notification-center notification (notifications table). The payload fields depend on the kind — see notificationLink. */
export interface AppNotification {
    id: number;
    kind: NotificationKind;
    payload: Record<string, string | number | boolean | null>;
    created_at: string | null;
    read: boolean;
}

/** The notification list and the unread count. */
export interface Inbox {
    unread: number;
    items: AppNotification[];
}

/** Request to /api/v1/social through the shared http.ts wrapper (token, JSON, errors). */
const call = <T>(path: string, init: RequestInit = {}) => apiRequest<T>(`/social${path}`, init);

const user = (name: string) => encodeURIComponent(name);

/** Achievement in the server response: code (catalog key), goal and progress, date earned (null — not unlocked), "new" flag. */
export interface AchievementItem {
    code: string;
    target: number;
    progress: number;
    earned_at: string | null;
    new: boolean;
}

/** Response of GET /profile/{name}/achievements: club title (catalog key achievements.titles.*) and achievements. */
export interface AchievementsData {
    title: string;
    achievements: AchievementItem[];
}

/**
 * Player achievements (GET /api/v1/profile/{name}/achievements, src/api/profile.py; open without sign-in).
 * Any failure (server, network, wrong response shape) — null: the profile block is simply not rendered.
 */
export async function fetchAchievements(username: string): Promise<AchievementsData | null> {
    const data = await apiRequest<AchievementsData>(`/profile/${encodeURIComponent(username)}/achievements`).catch(() => null);
    return data && Array.isArray(data.achievements) ? data : null;
}

export const socialApi = {
    /** Players whose name starts with q (case-insensitive); an exact match first. */
    search: (q: string) => call<{ players: PlayerCard[] }>(`/search?q=${encodeURIComponent(q)}`),
    relation: (name: string) => call<Relation>(`/relation/${user(name)}`),
    follow: (name: string) => call<Relation>(`/follow/${user(name)}`, {method: 'POST'}),
    unfollow: (name: string) => call<Relation>(`/follow/${user(name)}`, {method: 'DELETE'}),
    /** Whom the player follows; those who are online first. */
    following: () => call<{ players: PlayerCard[] }>('/following'),
    /**
     * Direct challenge: code — the code of a private invite the player has already created on the main board (WebSocket
     * action create_invite); the server turns it into a notification to the opponent with a link /challenge/<code>.
     */
    challenge: (name: string, code: string) => call<{ sent: boolean; online: boolean }>(`/challenge/${user(name)}`, {
        method: 'POST', body: JSON.stringify({code}),
    }),
    notifications: () => call<Inbox>('/notifications'),
    /** Mark the given notifications as read; without ids — all. */
    markRead: (ids?: number[]) => call<Inbox>('/notifications/read', {method: 'POST', body: JSON.stringify({ids: ids ?? null})}),
};

/** Where a notification leads; kinds without a page of their own (rematch, complaint reply, warm-up) lead to the home page. */
export function notificationLink(n: AppNotification): string {
    if (n.kind === 'challenge') return `/challenge/${n.payload.code}`;
    if (n.kind === 'tournament_round') return `/tournaments/${n.payload.tournament_id}`;
    if (n.kind === 'post_comment') return `/feed/post/${n.payload.post_id}`;
    if (n.kind === 'arena_reminder' || n.kind === 'arena_podium') return `/arenas/${n.payload.arena_id}`;
    if (n.kind === 'weekly_legends') return '/events/weekly';
    return '/';
}
