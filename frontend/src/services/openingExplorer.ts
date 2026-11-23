// --- FILE: frontend/src/services/openingExplorer.ts ---
// Opening explorer (task 16.2): POST /analysis/opening-explorer — moves from a position with game statistics, the opening
// name and master games from the archive and the library. Under the fair play rule: during a game against a human the server
// answers 409.
// Route — src/api/analysis.py, computation — src/services/opening_explorer.py: statistics come from the position index
// of played games (tables position_stats and position_games), the name — from the open openings table.

import {apiRequest} from './http';

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
