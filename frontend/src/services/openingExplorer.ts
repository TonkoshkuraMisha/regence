// --- FILE: frontend/src/services/openingExplorer.ts ---
// Opening explorer (task 16.2): POST /analysis/opening-explorer — moves from a position with game statistics, the opening
// name and master games from the archive and the library. Under the fair play rule: during a game against a human the server
// answers 409.
// Route — src/api/analysis.py, computation — src/services/opening_explorer.py: statistics come from the position index
// of played games (tables position_stats and position_games), the name — from the open openings table. Library examples
// carry their marks (structure, themes — task 27.5); libraryMarks collects them for links to the library search.

import {apiRequest} from './http';
import {GAME_THEMES, STRUCTURES} from './library';
import type {StructureCode} from './library';

type GameThemeCode = typeof GAME_THEMES[number];

/** Opening by the openings table: ECO code and English name (a proper noun, not translated). */
export interface ExplorerOpening {
    eco: string;
    name: string;
}

/** Move from a position and the results of games in which it occurred. */
export interface ExplorerMove {
    uci: string;
    san: string;
    games: number;
    white_wins: number;
    draws: number;
    black_wins: number;
    /** Opening name after this move, if it is different. */
    opening: ExplorerOpening | null;
}

/**
 * Master game that passed through the position: from the champions' archive (id — site game, view /game/{id}) or from the
 * public library collection (id — library game, /library/game/{id}). A repeat of one game in both places is
 * shown by the server once — as the library game (src/services/opening_explorer.merge_examples).
 */
export interface ExplorerGame {
    id: number;
    white: string;
    black: string;
    year: string | null;
    result: string | null;
    eco: string | null;
    source: 'archive' | 'library';
    /** Only for library games: there are explanations the player can see. */
    annotated?: boolean;
    /** Only for library games: the pawn structure mark (task 27.5), a code from STRUCTURES or null. */
    structure?: string | null;
    /** Only for library games: tactics that paid off (task 27.5), codes from GAME_THEMES. */
    themes?: string[];
}

/** Marks of the library games under a position: each structure and theme once, in the library filter order. */
export interface LibraryMarks {
    structures: StructureCode[];
    themes: GameThemeCode[];
}

/**
 * Distinct marks of the library examples under a position, so the explorer can lead to "library games with this
 * structure / theme" (/library?structure= and ?theme=). Codes the client does not know are skipped: the library filter
 * could not open them either.
 */
export function libraryMarks(games: ExplorerGame[]): LibraryMarks {
    const library = games.filter((g) => g.source === 'library');
    const structures = new Set(library.map((g) => g.structure));
    const themes = new Set(library.flatMap((g) => g.themes ?? []));
    return {
        structures: STRUCTURES.filter((code) => structures.has(code)),
        themes: GAME_THEMES.filter((code) => themes.has(code)),
    };
}

/** Explorer response for a position after the sent moves. */
export interface ExplorerResult {
    fen: string;
    /** Opening of the current position; null — the position is not in the openings table. */
    opening: ExplorerOpening | null;
    moves: ExplorerMove[];
    games: ExplorerGame[];
}

/** Explorer for a position: moves — moves from the initial position in UCI. A server refusal — UiError with text by code. */
export function exploreOpening(moves: string[]): Promise<ExplorerResult> {
    return apiRequest<ExplorerResult>('/analysis/opening-explorer', {method: 'POST', body: JSON.stringify({moves})});
}

/** Shares of White wins, draws and Black wins in percent (the sum is 100: draws get the rounding remainder). */
export function shares(move: Pick<ExplorerMove, 'games' | 'white_wins' | 'draws' | 'black_wins'>): [number, number, number] {
    if (!move.games) return [0, 0, 0];
    const white = Math.round((move.white_wins / move.games) * 100);
    const black = Math.round((move.black_wins / move.games) * 100);
    return [white, 100 - white - black, black];
}
