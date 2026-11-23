// --- FILE: frontend/src/services/personalities.ts ---

/**
 * Opponent workshop: personalities assembled by the player (task 10.2).
 *
 * One source of truth at a time: for a guest — localStorage of this browser, for a logged-in player —
 * the server (/api/v1/bots/personalities). After login the guest personalities are offered to be moved
 * to the profile; the moved ones are deleted from the browser, those that did not fit (limit, name clash)
 * stay in it, and the player sees the reason.
 *
 * Server: routes src/api/personalities.py (table bot_personalities), opening search — GET /api/v1/bots/openings
 * (src/api/bots.py). The character format and allowed slider bounds are defined by BotPersonalityConfig
 * (src/services/bots/personality.py); here is its mirror — PersonalityConfig.
 */

import {API_BASE_URL} from '../config/api';
import {UiError, readApiErrorOr} from './apiErrors';
import {tp, uiMessage} from '../i18n';
import type {MessageKey} from '../i18n';

/** How a personality values pieces (in pawns): affects the choice of exchanges, not the engine evaluation. */
export interface PieceValues {
    pawn: number;
    knight: number;
    bishop: number;
    rook: number;
    queen: number;
}

/** Opponent character — a mirror of the server's BotPersonalityConfig (value bounds are checked by the server). */
export interface PersonalityConfig {
    /** −100...100: plus — checks, sacrifices, play against the king; minus — prophylaxis and quiet moves. */
    aggression: number;
    /** Feature weights 0...200: 100 — normal weight, 0 — the feature is ignored, 200 — doubled. */
    center_control: number;
    mobility: number;
    king_safety: number;
    pawn_structure: number;
    piece_values: PieceValues;
    /**
     * Strength sliders: randomness (0...100) — random spread between close candidates; blunder_guard_cp — the window
     * from the best move in centipawns within which the style chooses the move; target_elo — target rating.
     */
    randomness: number;
    blunder_guard_cp: number;
    target_elo: number;
    /** Favourite openings (task 21.2): positions (EPD) of openings table entries, up to three per colour. */
    openings_white?: string[];
    openings_black?: string[];
    /**
     * Task 21.4: beginner habits, opening character, attitude to draws (−100 — never agrees, +100 —
     * gladly) and the weight of passed pawns (0...200, 100 — like everyone).
     */
    habits?: Habit[];
    opening_style?: OpeningStyle;
    draw_attitude?: number;
    passed_pawns?: number;
}

/** Codes of habits and opening characters — the same as on the server; labels — catalog workshop.habits / openingStyles. */
export const HABITS = ['hangs_pieces', 'early_queen', 'pawn_grabber', 'knight_lover', 'no_castling', 'trades_all'] as const;
export type Habit = typeof HABITS[number];
export const OPENING_STYLES = ['normal', 'trapper', 'trap_victim', 'gambit', 'early_queen', 'drawish', 'capture_lover', 'offbeat'] as const;
export type OpeningStyle = typeof OPENING_STYLES[number];
/** Form limits — the same as in the server check (no more than three habits and three openings per colour). */
export const MAX_HABITS = 3;

export const MAX_FAVORITE_OPENINGS = 3;

/** Entry of the open openings table: position (EPD) — what is stored in openings_white / openings_black. */
export interface OpeningEntry {
    eco: string;
    /** English proper noun from the open openings table — not translated. */
    name: string;
    epd: string;
    moves: string[];
}

/** Opening search by name or ECO code, or entries by positions (to show the names of the selected ones). */
export async function fetchOpenings(params: { q?: string; epds?: string[] }): Promise<OpeningEntry[]> {
    const query = new URLSearchParams();
    if (params.q) query.set('q', params.q);
    for (const epd of params.epds ?? []) query.append('epd', epd);
    const res = await fetch(`${API_BASE_URL}/api/v1/bots/openings?${query.toString()}`);
    if (!res.ok) throw new UiError(await readApiErrorOr(res, 'common.networkError'));
    return ((await res.json()) as { openings: OpeningEntry[] }).openings;
}

/** What the player assembled in the form: name and character. The name goes into the PGN, so the server checks it as a player name. */
export interface PersonalityDraft {
    name: string;
    config: PersonalityConfig;
}

/** Saved personality — from the server or from the guest's localStorage. */
export interface Personality extends PersonalityDraft {
    /** A number — id on the server; a string — local id of a guest personality. */
    id: number | string;
    created_at: string;
    updated_at: string;
}

/** Result of moving guest personalities (POST /bots/personalities/import). */
export interface ImportResult {
    created: Personality[];
    /** reason — server error code (serverErrors), params — its parameters. */
    skipped: { name: string; reason: string; params?: Record<string, string | number> }[];
}

/** Personality count limit — the same as on the server (MAX_PERSONALITIES_PER_USER); a guest has the same in the browser. */
export const MAX_PERSONALITIES = 20;
/** localStorage key with the guest's personalities (JSON array of Personality). */
export const GUEST_STORAGE_KEY = 'regence_guest_personalities';

/** Character of a new personality — the same defaults as BotPersonalityConfig on the server. */
export const DEFAULT_CONFIG: PersonalityConfig = {
    aggression: 0,
    center_control: 100,
    mobility: 100,
    king_safety: 100,
    pawn_structure: 100,
    piece_values: {pawn: 1, knight: 3, bishop: 3, rook: 5, queen: 9},
    randomness: 20,
    blunder_guard_cp: 120,
    target_elo: 1500,
    draw_attitude: 0,
    passed_pawns: 100,
};

const sameName = (a: string, b: string) => a.trim().toLocaleLowerCase() === b.trim().toLocaleLowerCase();

// --- Guest: localStorage ----------------------------------------------------------------------

/** Guest personalities from localStorage; corrupted entries and unavailable storage give an empty list. */
export function readGuestPersonalities(): Personality[] {
    try {
        const raw = localStorage.getItem(GUEST_STORAGE_KEY);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed.filter((p) => p && typeof p.name === 'string' && p.config) : [];
    } catch {
        return [];
    }
}

function writeGuestPersonalities(items: Personality[]): void {
    try {
        if (items.length) localStorage.setItem(GUEST_STORAGE_KEY, JSON.stringify(items));
        else localStorage.removeItem(GUEST_STORAGE_KEY);
    } catch {
        // Storage is unavailable (private mode) — guest personalities live until reload.
    }
}

/**
 * Create (without id) or change a guest personality. The rules are the same as the server's, with the same error texts:
 * the name is not repeated, no more than MAX_PERSONALITIES personalities. Reserved names are not checked for a guest — the
 * server checks them when moving to the profile.
 */
export function saveGuestPersonality(draft: PersonalityDraft, id?: string): Personality {
    const items = readGuestPersonalities();
    if (items.some((p) => p.id !== id && sameName(p.name, draft.name))) {
        throw new UiError(uiMessage('serverErrors.personality_duplicate'));
    }
    const now = new Date().toISOString();
    const existing = id ? items.find((p) => p.id === id) : undefined;
    if (!existing && items.length >= MAX_PERSONALITIES) {
        throw new UiError(uiMessage('serverErrors.personality_limit', {max: MAX_PERSONALITIES}));
    }
    const saved: Personality = existing
        ? {...existing, ...draft, updated_at: now}
        : {...draft, id: `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, created_at: now, updated_at: now};
    writeGuestPersonalities(existing ? items.map((p) => (p.id === id ? saved : p)) : [...items, saved]);
    return saved;
}

export function deleteGuestPersonality(id: string): void {
    writeGuestPersonalities(readGuestPersonalities().filter((p) => p.id !== id));
}

// --- Logged-in player: server ------------------------------------------------------------------

const BASE = `${API_BASE_URL}/api/v1/bots/personalities`;

/** Request with a token; a refusal — UiError with text by server code, and if there is no code — with the fallback message. */
async function request<T>(token: string, url: string, init: RequestInit, fallback: MessageKey): Promise<T> {
    const res = await fetch(url, {
        ...init,
        headers: {Authorization: `Bearer ${token}`, ...(init.body ? {'Content-Type': 'application/json'} : {})},
    });
    if (!res.ok) throw new UiError(await readApiErrorOr(res, fallback));
    return (res.status === 204 ? undefined : await res.json()) as T;
}

// Four requests to /api/v1/bots/personalities: list (GET), create (POST), edit (PUT /{id}), delete
// (DELETE /{id}). The server returns and changes only the player's own personalities.
export const listPersonalities = (token: string) =>
    request<Personality[]>(token, BASE, {method: 'GET'}, 'workshop.loadFailed');

export const createPersonality = (token: string, draft: PersonalityDraft) =>
    request<Personality>(token, BASE, {method: 'POST', body: JSON.stringify(draft)}, 'workshop.saveFailed');

export const updatePersonality = (token: string, id: number, draft: Partial<PersonalityDraft>) =>
    request<Personality>(token, `${BASE}/${id}`, {method: 'PUT', body: JSON.stringify(draft)}, 'workshop.saveFailed');

export const deletePersonality = (token: string, id: number) =>
    request<void>(token, `${BASE}/${id}`, {method: 'DELETE'}, 'workshop.deleteFailed');

/** Moves guest personalities to the profile; only those that did not fit remain in the browser. */
export async function importGuestPersonalities(token: string): Promise<ImportResult> {
    const guests = readGuestPersonalities();
    if (!guests.length) return {created: [], skipped: []};
    const result = await request<ImportResult>(token, `${BASE}/import`, {
        method: 'POST',
        body: JSON.stringify({items: guests.map(({name, config}) => ({name, config}))}),
    }, 'workshop.importFailed');
    const moved = new Set(result.created.map((p) => p.name.toLocaleLowerCase()));
    writeGuestPersonalities(guests.filter((p) => !moved.has(p.name.toLocaleLowerCase())));
    return result;
}

/**
 * After login: if the browser has guest personalities — offers to move them to the profile.
 * Returns the move result or null if there is nothing to move or the player declined.
 */
export async function offerGuestPersonalityTransfer(
    token: string,
    confirm: (message: string) => boolean = (message) => window.confirm(message),
): Promise<ImportResult | null> {
    const count = readGuestPersonalities().length;
    if (!count || !confirm(tp('auth.importConfirm', count))) {
        return null;
    }
    return importGuestPersonalities(token);
}
