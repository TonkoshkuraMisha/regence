// --- FILE: frontend/src/services/library.ts ---
// Game library (task 27.1): /api/v1/library — collection tree, collection games, search and PGN for the viewer.
// Without login public collections are visible; with a token — also one's own private ones (and service ones for moderators).
// Routes — src/api/library.py, visibility rules and search — src/services/library.py. The data of the "Miniatures"
// and "Recognise the structure" trainers (/library/miniatures, /library/structure-quiz) also comes from here.

import type {CoachComment} from './coach';
import {apiRequest} from './http';

/** Library collection. The server returns them as a flat list; the client builds the tree by parent_id (childrenOf). */
export interface LibraryCollection {
    id: number;
    parent_id: number | null;
    name: string;
    /** public — visible to all, owner — only to the owner, staff — service, only for moderators. */
    visibility: 'public' | 'owner' | 'staff';
    /** Games directly in this collection, without nested ones (with nested — totalGames). */
    games: number;
}

/** Game list row: PGN headers and game length in plies. */
export interface LibraryGameRow {
    id: number;
    white: string;
    black: string;
    event: string;
    site: string;
    date: string;
    year: number | null;
    result: string;
    eco: string;
    opening: string;
    plies: number;
    /** Pawn structure (task 27.5) — a code from STRUCTURES. */
    structure?: string | null;
    /** Tactics that paid off in the game (task 27.5) — codes from GAME_THEMES. */
    themes?: string[];
}

/** Theme marks of games — the same as the server (src/services/game_themes.py GAME_THEMES); names — `themes.<code>.name`. */
export const GAME_THEMES = ['fork', 'double_check', 'pin', 'skewer', 'discovered_attack', 'discovered_check', 'overload',
    'interference', 'trapped_piece'] as const;

/** Pawn structure codes — the same as the server tags (src/services/pawn_structures.py); names — in the catalog. */
export const STRUCTURES = ['hedgehog', 'maroczy', 'wedge', 'kid_chain', 'modern_benoni', 'stonewall', 'saw', 'french_chain',
    'french_exchange', 'carlsbad', 'hanging_pawns', 'isolated_pawn', 'spanish', 'symmetry'] as const;
export type StructureCode = typeof STRUCTURES[number];

/** "Miniature" (27.9): a game that ended in mate; fen — position before the mate, answer — the game move. */
export interface LibraryMiniature extends LibraryGameRow {
    fen: string;
    moves: string[];
    answer: string;
}

/** "Recognise the structure" question (27.9): game_id = null — a teaching skeleton. */
export interface StructureQuestion {
    fen: string;
    answer: StructureCode;
    options: StructureCode[];
    game_id: number | null;
    ply: number | null;
}

/** Game list page: total — total found, games — no more than LIBRARY_PAGE rows. */
export interface LibraryPage {
    total: number;
    games: LibraryGameRow[];
}

/** Search filters (GET /library/games); empty and unset ones do not go into the request (searchQuery). */
export interface LibrarySearch {
    /** Part of a player name. */
    player?: string;
    /** Start of an opening code: "B9" will find B90–B99. */
    eco?: string;
    year_from?: number;
    year_to?: number;
    result?: string;
    max_plies?: number;
    structure?: string;
    /** "Miniature" tag (27.5): only decisive games up to 25 moves. */
    miniature?: boolean;
    /** "Beautiful" tag (27.5): material sacrifice and the winner's mate. */
    beautiful?: boolean;
    /** Theme mark (task 27.5): a tactic from GAME_THEMES that paid off in the game. */
    theme?: string;
    /** Game start in UCI separated by spaces (repertoire node, 27.10). */
    moves?: string;
    offset?: number;
}

/** Game annotation (task 27.4): mentor comments as coach.* codes by plies. */
export interface LibraryAnnotation {
    /** The server shows auto and approved to everyone, draft and review — only to moderators. */
    status: 'auto' | 'draft' | 'review' | 'approved';
    version: number;
    /** Key — the ply number as a string. */
    comments: Record<string, CoachComment>;
    /** Position evaluations along the game, saved together with the annotation. */
    evals: number[];
}

/** Game list page size (limit parameter of requests). */
export const LIBRARY_PAGE = 50;

/** Request to /api/v1/library via the common http.ts wrapper (token, JSON, errors). */
const call = <T>(path: string) => apiRequest<T>(`/library${path}`);

/** Search query string: set filters plus limit = LIBRARY_PAGE. */
export function searchQuery(search: LibrarySearch): string {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(search)) {
        if (value !== undefined && value !== '') params.set(key, String(value));
    }
    params.set('limit', String(LIBRARY_PAGE));
    return params.toString();
}

export const libraryApi = {
    collections: () => call<{ collections: LibraryCollection[] }>('/collections'),
    collectionGames: (id: number, offset = 0) =>
        call<LibraryPage & { id: number; name: string }>(`/collections/${id}/games?offset=${offset}&limit=${LIBRARY_PAGE}`),
    search: (search: LibrarySearch) => call<LibraryPage>(`/games?${searchQuery(search)}`),
    /** Game annotation from the GET /library/games/{id} response; null — there is none or it is not for this visitor. */
    annotation: (id: number | string) =>
        call<{ annotation: LibraryAnnotation | null }>(`/games/${id}`).then((body) => body.annotation ?? null),
    /** seed makes the set reproducible: same seed — same games and questions. */
    miniatures: (count: number, seed: number) =>
        call<{ miniatures: LibraryMiniature[] }>(`/miniatures?count=${count}&seed=${seed}`),
    structureQuiz: (count: number, seed: number) =>
        call<{ questions: StructureQuestion[] }>(`/structure-quiz?count=${count}&seed=${seed}`),
};

/** Collection children in server order; roots — parent_id = null. */
export function childrenOf(list: LibraryCollection[], parent: number | null): LibraryCollection[] {
    return list.filter((c) => c.parent_id === parent);
}

/** Games in a collection including all nested ones (for the tree node label). */
export function totalGames(list: LibraryCollection[], id: number): number {
    const own = list.find((c) => c.id === id)?.games ?? 0;
    return own + childrenOf(list, id).reduce((sum, child) => sum + totalGames(list, child.id), 0);
}
