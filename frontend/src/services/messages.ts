// --- FILE: frontend/src/services/messages.ts ---
// Direct messages (task 30.1): conversations, sending text and cards (game, position, puzzle, lesson, tournament),
// the "who can write to me" setting and the block list.
// All requests go to /api/v1/messages and only with login (routes src/api/messages.py, rules —
// src/services/direct_messages.py, attachment cards — src/services/attachments.py). A new message is also delivered by the
// server to the recipient's open tabs over WebSocket.

import {apiRequest} from './http';

/** Direct message attachments; in the feed also a library game and one's own achievement (task 30.2). */
export type AttachmentKind = 'game' | 'position' | 'puzzle' | 'lesson' | 'tournament' | 'library' | 'achievement';
/** Who can write to the player: everyone, only those they follow, nobody. */
export type DmPolicy = 'all' | 'following' | 'nobody';

/**
 * Attachment card: kind, reference and a snapshot of the data at send time. The set of filled fields depends on the kind:
 * the server checks the reference and builds the snapshot itself, the client sends only {kind, ref}.
 */
export interface Attachment {
    kind: AttachmentKind;
    ref: string;
    white?: string | null;
    black?: string | null;
    result?: string | null;
    status?: string | null;
    fen?: string;
    rating?: number;
    format?: string;
    size?: number;
    owner?: string | null;
    event_key?: string | null;
    career_stage?: string | null;
    year?: number | null;
    event?: string | null;
    earned_at?: string | null;
}

/** One conversation message from the viewer's point of view (mine — sent by the viewer). */
export interface DirectMessage {
    id: number;
    mine: boolean;
    body: string;
    attachment: Attachment | null;
    created_at: string | null;
    read: boolean;
    /** Held back by the insult filter until the moderator decides (task 30.3), visible only to the sender. */
    held?: boolean;
}

/** Conversation list row: the other party, the last message and the number of unread ones from them. */
export interface Conversation {
    username: string;
    avatar: string | null;
    last: DirectMessage;
    unread: number;
    /** The other party is in the viewer's block list. */
    blocked: boolean;
}

/** Conversation with a player (GET /messages/with/{name}): a page of messages, oldest first. */
export interface Thread {
    username: string;
    avatar: string | null;
    messages: DirectMessage[];
    /** Whether one can write now; if not — reason: a reason code from the server (text — from the catalog). */
    can_write: boolean;
    reason: string | null;
    blocked: boolean;
}

/** Direct message settings: who can write and the names of players in the block list. */
export interface DmSettings {
    dm_policy: DmPolicy;
    blocked: string[];
}

/** Request to /api/v1/messages via the common http.ts wrapper (token, JSON, errors). */
const call = <T>(path: string, init: RequestInit = {}) => apiRequest<T>(`/messages${path}`, init);

const user = (name: string) => encodeURIComponent(name);

/** Direct message endpoints. The hide and markRead responses carry the new total unread count — for the header. */
export const messagesApi = {
    conversations: () => call<{ conversations: Conversation[]; unread: number }>(''),
    unread: () => call<{ unread: number }>('/unread'),
    /** beforeId — loading an earlier page: messages older than the given one. */
    thread: (name: string, beforeId?: number) =>
        call<Thread>(`/with/${user(name)}${beforeId ? `?before_id=${beforeId}` : ''}`),
    /** sendAnyway — the player insists after a filter refusal (text_flagged): the message is held back until a moderator. */
    send: (name: string, body: string, attachment?: { kind: AttachmentKind; ref: string } | null, sendAnyway = false) =>
        call<DirectMessage>(`/with/${user(name)}`, {
            method: 'POST', body: JSON.stringify({body, attachment: attachment ?? null, send_anyway: sendAnyway}),
        }),
    /** Hide the conversation from the list until a new message from the other party (this is not a block). */
    hide: (name: string) => call<{ unread: number }>(`/with/${user(name)}/hide`, {method: 'POST'}),
    markRead: (name: string) => call<{ unread: number }>(`/with/${user(name)}/read`, {method: 'POST'}),
    settings: () => call<DmSettings>('/settings'),
    setPolicy: (policy: DmPolicy) => call<DmSettings>('/settings', {method: 'PUT', body: JSON.stringify({dm_policy: policy})}),
    block: (name: string) => call<DmSettings>(`/block/${user(name)}`, {method: 'POST'}),
    unblock: (name: string) => call<DmSettings>(`/block/${user(name)}`, {method: 'DELETE'}),
};

/** FEN: eight board ranks; side to move and the other fields are optional. The exact position check is done by the server. */
const FEN_RE = /^([pnbrqkPNBRQK1-8]+\/){7}[pnbrqkPNBRQK1-8]+(\s+[wb](\s+\S+){0,4})?$/;

/**
 * What the player pasted: a position FEN or a link to a library game, game, tournament, lesson. Unknown — null (then the
 * kind is chosen manually). A library link is checked before a game link: its address also contains "/game/".
 */
export function detectAttachment(raw: string): { kind: AttachmentKind; ref: string } | null {
    const text = raw.trim();
    if (!text) return null;
    if (FEN_RE.test(text)) return {kind: 'position', ref: text};
    const library = text.match(/\/library\/game\/(\d+)(?:[/?#]|$)/);
    if (library) return {kind: 'library', ref: library[1]};
    const game = text.match(/\/game\/(\d+)(?:[/?#]|$)/);
    if (game) return {kind: 'game', ref: game[1]};
    const tournament = text.match(/\/tournaments\/(\d+)(?:[/?#]|$)/);
    if (tournament) return {kind: 'tournament', ref: tournament[1]};
    const lesson = text.match(/\/learn\/([A-Za-z0-9_.:-]+)(?:[/?#]|$)/);
    if (lesson) return {kind: 'lesson', ref: lesson[1]};
    return null;
}

/** Where the card leads (null — a card without a page: position and puzzle are shown as a diagram). */
export function attachmentLink(a: Attachment): string | null {
    if (a.kind === 'game') return `/game/${a.ref}`;
    if (a.kind === 'tournament') return `/tournaments/${a.ref}`;
    if (a.kind === 'lesson') return `/learn/${a.ref}`;
    if (a.kind === 'library') return `/library/game/${a.ref}`;
    return null;
}
