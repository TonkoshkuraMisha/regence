// --- FILE: frontend/src/services/tools.ts ---
// "Find mate" (task 16.4): POST /analysis/find-mate — the engine, under the fair-play rule.
// Route — src/api/analysis.py, search — src/services/mate_finder.py (Stockfish via the pool, with a time limit).
// During a game with a human the server refuses; a busy engine pool is also a refusal with a code.

import {apiRequest} from './http';

/** Mate search result: whether found, in how many moves, and the mating line — in UCI (line) and in SAN (san). */
export interface MateResult {
    found: boolean;
    mate_in: number | null;
    line: string[];
    san: string[];
}

/** Search position fen for a mate no longer than moves moves. A server refusal is a UiError with text by error code. */
export function findMate(fen: string, moves: number): Promise<MateResult> {
    return apiRequest<MateResult>('/analysis/find-mate', {method: 'POST', body: JSON.stringify({fen, moves})});
}
