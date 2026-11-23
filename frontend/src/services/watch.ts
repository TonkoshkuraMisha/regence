// --- FILE: frontend/src/services/watch.ts ---
// "Watch" (task 16.3): ongoing games (/profile/games/live), master archive with filters, "Game of the day" and "fun
// collections" (/watch/*).
// Routes - src/api/watch.py and src/api/profile.py (ongoing games); all open without sign-in. The archive - historical
// master games loaded from PGN (src/db/seed.py); collections are precomputed by scripts/build_collections.py
// (table collection_entries), the server only serves them.

import type {LiveGameItem} from '../components/chessboard/types';
import {apiRequest} from './http';

/** Master archive game in a list: players, year, place, result and opening code. */
export interface ArchiveGame {
    id: number;
    white: string;
    black: string;
    year: string | null;
    site: string | null;
    result: string | null;
    eco: string | null;
}

/** Archive filters (GET /watch/archive): part of a player's name, years, opening code, result and page offset. */
export interface ArchiveFilters {
    player?: string;
    year_from?: number;
    year_to?: number;
    eco?: string;
    result?: '1-0' | '0-1' | '1/2-1/2';
    offset?: number;
}

/** Keys of the "fun collections" - the same as on the server (src/services/collections.py); titles are in the catalog. */
export const COLLECTIONS = ['shortest', 'checks', 'capture_streak', 'peaceful', 'promotions', 'pawn_wars', 'stalemates'] as const;
export type CollectionKey = typeof COLLECTIONS[number];

/** GET to /api/v1 via the shared http.ts wrapper (the token is sent if the player is signed in; open routes ignore it). */
const get = <T>(path: string) => apiRequest<T>(path);

/** Archive page size (limit parameter). */
export const PAGE_SIZE = 20;

export const watchApi = {
    /** Games between humans in progress right now. */
    live: () => get<LiveGameItem[]>('/profile/games/live'),
    archive: (filters: ArchiveFilters) => {
        const params = new URLSearchParams({limit: String(PAGE_SIZE)});
        for (const [key, value] of Object.entries(filters)) {
            if (value !== undefined && value !== '' && value !== null) params.set(key, String(value));
        }
        return get<{ total: number; items: ArchiveGame[] }>(`/watch/archive?${params}`);
    },
    /** "Game of the day" - one for everyone: a decisive archive game picked by date; null - the archive is empty. */
    gameOfTheDay: () => get<{ date?: string; game: ArchiveGame | null }>('/watch/game-of-the-day'),
    /** Collections: games by place, value - the collection's metric (number of checks, game length, etc.). */
    collections: () => get<{ collections: Record<CollectionKey, (ArchiveGame & { value: number })[]> }>('/watch/collections'),
};
