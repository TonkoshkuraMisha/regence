// --- FILE: frontend/src/services/gameImport.ts ---
// Import of games from lichess, chess.com and PGN (task 24.1): /api/v1/imports. Login required — games are tied to the
// player; after import the server analyses them in the background and builds "My mistakes" puzzles from the player's slips.
// Routes — src/api/game_import.py, rules — src/services/game_import.py. The server blocks import and analysis while a
// game against a human is in progress (fair play): otherwise a live game could be pasted into "import" to get an evaluation.
// /subscriptions - the opt-in daily import (src/services/game_import_schedule.py). A Fischer random (Chess960) game is
// replayed on the server (/games/{id}/chess960): the client chess library has no 960 castling.

import {apiRequest} from './http';
import type {Archive960} from './chess960';

/** Site from which games are fetched by nickname. */
export type ImportSource = 'lichess' | 'chesscom';
/** Where the game in the list came from: a site or a pasted PGN. */
export type ImportedSource = ImportSource | 'pgn';
export type ImportSpeed = 'bullet' | 'blitz' | 'rapid' | 'classical' | 'daily';
/** Ordinary chess or Fischer random chess (opened in the 960 viewer). */
export type ImportVariant = 'standard' | 'chess960';

/** Imported game in the list (game_import.view on the server). */
export interface ImportedGameView {
    id: number;
    source: ImportedSource;
    variant: ImportVariant;
    /** Which colour the player themself had: by nickname on the site or by name in the PGN headers. */
    color: 'white' | 'black';
    white: string;
    black: string;
    white_rating: number | null;
    black_rating: number | null;
    result: string;
    speed: ImportSpeed | null;
    played_at: string | null;
    /** Engine analysis is already ready. */
    analyzed: boolean;
    /** How many "My mistakes" puzzles were made from this game. */
    puzzles: number;
}

/** Result of one import: what was added, how many games already existed and how many were skipped as unusable. */
export interface ImportResult {
    added: ImportedGameView[];
    duplicates: number;
    skipped: number;
}

/** List page: total — all games of the player, max — storage limit (setting GAME_IMPORT_MAX_STORED). */
export interface ImportedList {
    total: number;
    max: number;
    games: ImportedGameView[];
}

/** Daily import from a site (game_import_schedule.view): the username followed and how the last run went. */
export interface ImportSubscriptionView {
    source: ImportSource;
    username: string;
    last_run_at: string | null;
    last_added: number;
    /** The serverErrors.* code of the last run's refusal, or null. */
    last_error: string | null;
}

/** Page size of the imported games list. */
export const IMPORT_PAGE = 20;
/** How many recent games can be requested per import (choice in the form). */
export const IMPORT_COUNTS = [5, 10, 20] as const;
const call = <T>(path: string, init: RequestInit = {}) => apiRequest<T>(`/imports${path}`, init);

/** Import endpoints; all require login. */
export const importApi = {
    /** The player's latest games from a site by nickname (the server itself calls the site's open API). */
    fetchSite: (source: ImportSource, username: string, max: number) =>
        call<ImportResult>('/fetch', {method: 'POST', body: JSON.stringify({source, username, max})}),
    /** Games from a pasted PGN; player — the player's name in the headers, used to determine their colour. */
    pastePgn: (pgn: string, player: string, max: number) =>
        call<ImportResult>('/pgn', {method: 'POST', body: JSON.stringify({pgn, player, max})}),
    list: (offset = 0) => call<ImportedList>(`/games?offset=${offset}&limit=${IMPORT_PAGE}`),
    /** One game; puzzle_plies — plies from which "My mistakes" puzzles were made. */
    game: (id: number | string) => call<ImportedGameView & { puzzle_plies: number[] }>(`/games/${id}`),
    remove: (id: number) => call<void>(`/games/${id}`, {method: 'DELETE'}),
    /** A Fischer game step by step: the position after every ply, replayed by the server with 960 castling. */
    chess960: (id: number | string) => call<Archive960>(`/games/${id}/chess960`),
    /** Daily import: the sites followed; the server imports on a schedule, once a day. */
    subscriptions: () => call<{ subscriptions: ImportSubscriptionView[] }>('/subscriptions'),
    subscribe: (source: ImportSource, username: string) =>
        call<ImportSubscriptionView>(`/subscriptions/${source}`, {method: 'PUT', body: JSON.stringify({username})}),
    unsubscribe: (source: ImportSource) => call<void>(`/subscriptions/${source}`, {method: 'DELETE'}),
};

/** Where an imported game opens: the review with the coach, or the 960 viewer for a Fischer game. */
export const importedGamePath = (game: Pick<ImportedGameView, 'id' | 'variant'>) =>
    (game.variant === 'chess960' ? `/import/game/${game.id}/960` : `/import/game/${game.id}`);

/** Outcome from the player's point of view: win / loss / draw; unknown — no result recorded in the game ("*"). */
export function outcome(game: ImportedGameView): 'win' | 'loss' | 'draw' | 'unknown' {
    if (game.result === '1/2-1/2') return 'draw';
    if (game.result === '1-0') return game.color === 'white' ? 'win' : 'loss';
    if (game.result === '0-1') return game.color === 'black' ? 'win' : 'loss';
    return 'unknown';
}

/** The player's opponent in an imported game: name and rating of the side the player did not play. */
export function opponentOf(game: ImportedGameView): { name: string; rating: number | null } {
    return game.color === 'white'
        ? {name: game.black, rating: game.black_rating}
        : {name: game.white, rating: game.white_rating};
}

// The nickname on the site is remembered in the browser — a convenience, not data: everything works without it.
// localStorage keys: regence_import_nick_lichess and regence_import_nick_chesscom.
const NICK_KEY = 'regence_import_nick';

/** Nickname the player last used to import games from this site; empty — not remembered. */
export function savedNick(source: ImportSource): string {
    try {
        return localStorage.getItem(`${NICK_KEY}_${source}`) ?? '';
    } catch {
        return '';
    }
}

export function rememberNick(source: ImportSource, nick: string): void {
    try {
        localStorage.setItem(`${NICK_KEY}_${source}`, nick);
    } catch {
        // private mode — nothing is remembered
    }
}
