// --- FILE: frontend/src/services/profile.ts ---
// Player profile and leaderboard: GET /api/v1/profile/<name> (profile, ladder, arena trophies), /stats (totals over all
// games), /games (paged; for master champions — their PGN archive), /rating-history (rating values saved by the
// server when games finish), /profile/leaderboard. Routes — src/api/profile.py; everything is open without login.
// Used by Profile.tsx, ChampionGames.tsx and Leaderboard.tsx. Request and errors — the common apiRequest (http.ts).

import {apiRequest} from './http';

/** Rating category by time control; the same codes on the server. */
export type RatingCategory = 'bullet' | 'blitz' | 'rapid' | 'classical';

/** Player profile as served by GET /profile/<name>. */
export interface UserProfile {
    id: number;
    username: string;
    avatar?: string | null;
    bullet_rating: number;
    blitz_rating: number;
    rapid_rating: number;
    classical_rating: number;
    created_at: string;
    /** Club ladder: a separate rating of games against bots without hints and takebacks. */
    ladder?: { rating: number; games: number; step: number; total: number };
    /** Arena trophies (task 33.5): first, second and third places — src/services/arena_awards.py. */
    arena_trophies?: { gold: number; silver: number; bronze: number };
}

/** Player totals over all games (GET /stats): computed by the server, not by the client from a loaded page. */
export interface PlayerStats {
    total: number;
    wins: number;
    draws: number;
    losses: number;
    rated_games: Record<RatingCategory, number>;
}

/** Game in a player's history or in a champion's archive. */
export interface ProfileGame {
    game_id: number;
    white_username: string;
    white_rating: number;
    black_username: string;
    black_rating: number;
    status: string;
    is_rated: boolean;
    /** The player used the mentor (task 11.3). */
    assisted?: boolean;
    /** Blindfold play (task 19.5): level and peeks. */
    blindfold?: number | null;
    peeks?: number | null;
    result: string;
    pgn_date: string | null;
    site: string | null;
    eco: string | null;
    finished_at: string | null;
}

/** Page of games: items and total count. */
export interface ProfileGamesPage {
    items: ProfileGame[];
    total: number;
}

/** Rating after a game and its change from that game (GET /rating-history). */
export interface RatingPoint {
    game_id: number;
    finished_at: string;
    rating: number;
    delta: number;
}

/** Leaderboard row. */
export interface LeaderboardEntry {
    rank: number;
    avatar?: string | null;
    username: string;
    rating: number;
}

/** Player profile path: the name is encoded (master names may contain spaces and commas). */
const playerPath = (username: string) => `/profile/${encodeURIComponent(username)}`;

export const profileApi = {
    /** Profile; no player — UiError with text user_not_found, any other refusal — profile.loadFailed. */
    get: (username: string) => apiRequest<UserProfile>(playerPath(username), {}, 'profile.loadFailed'),
    stats: (username: string) => apiRequest<PlayerStats>(`${playerPath(username)}/stats`),
    /** Games by page; sort='asc' — from first to last (champion archive). */
    games: (username: string, limit: number, offset: number, sort?: 'asc') => {
        const params = new URLSearchParams({limit: String(limit), offset: String(offset)});
        if (sort) params.set('sort', sort);
        return apiRequest<ProfileGamesPage>(`${playerPath(username)}/games?${params}`, {}, 'championGames.loadFailed');
    },
    ratingHistory: (username: string, category: RatingCategory) =>
        apiRequest<{ points: RatingPoint[] }>(`${playerPath(username)}/rating-history?category=${category}`),
    /**
     * Mark blindfold play (task 19.5) in a finished unrated game: level and number of peeks. The server accepts
     * the mark only from a participant of such a game; a failure does not matter to the player — the caller swallows it.
     */
    markBlindfold: (gameId: number | string, level: number, peeks: number) =>
        apiRequest<unknown>(`/profile/games/${gameId}/blindfold`, {method: 'POST', body: JSON.stringify({level, peeks})}),
    /** Leaderboard of a category: the first `limit` players. */
    leaderboard: (category: RatingCategory, limit: number) =>
        apiRequest<LeaderboardEntry[]>(`/profile/leaderboard?limit=${limit}&category=${category}`, {}, 'leaderboard.loadFailed'),
};
