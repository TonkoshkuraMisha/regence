// --- FILE: frontend/src/trainers/memory.ts ---
// Memory trainers (task 19.3). "Restore the position": a position from a real game is shown for a few seconds,
// then it must be set up from memory; scoring is per square. "Remember the game": the first moves of a known game are
// played back, then they must be repeated on the board. Positions are from classic games (14.7) and endgames (14.4): natural
// positions are remembered differently than random ones.

import {Chess} from 'chess.js';
import {rng} from './vision';

export type Placement = Record<string, string>;

/** "Restore the position" steps: 4-6, 7-12, 13-24 pieces; display time decreases from 15 to 3 s. */
export const MEMORY_LEVELS: { min: number; max: number; seconds: number }[] = [
    {min: 3, max: 6, seconds: 15}, {min: 3, max: 6, seconds: 10}, {min: 4, max: 6, seconds: 6},
    {min: 7, max: 12, seconds: 15}, {min: 7, max: 12, seconds: 10}, {min: 7, max: 12, seconds: 6},
    {min: 13, max: 18, seconds: 15}, {min: 13, max: 24, seconds: 10}, {min: 13, max: 24, seconds: 6}, {min: 13, max: 24, seconds: 3},
];

export function memoryLevel(level: number) {
    return MEMORY_LEVELS[Math.min(MEMORY_LEVELS.length, Math.max(1, level)) - 1];
}

export function placementOfFen(fen: string): Placement {
    const result: Placement = {};
    fen.split(' ')[0].split('/').forEach((row, i) => {
        let file = 0;
        for (const ch of row) {
            if (/\d/.test(ch)) file += Number(ch);
            else result[`${String.fromCharCode(97 + file++)}${8 - i}`] = ch;
        }
    });
    return result;
}

/** All game positions (after every ply) and endgame positions - the pool for "Restore the position". */
export function positionPool(games: { moves: string[] }[], endgames: { fen: string }[]): string[] {
    const pool: string[] = [];
    for (const game of games) {
        const board = new Chess();
        for (const uci of game.moves) {
            try {
                board.move({from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4]});
            } catch {
                break;
            }
            pool.push(board.fen());
        }
    }
    for (const item of endgames) pool.push(item.fen);
    return pool;
}

export function pieceCount(fen: string): number {
    return Object.keys(placementOfFen(fen)).length;
}

/** Position for a level: from the pool - with a piece count in the level's range; deterministic by seed. */
export function pickPosition(pool: string[], level: number, seed: number): string | null {
    const {min, max} = memoryLevel(level);
    const fitting = pool.filter((fen) => {
        const n = pieceCount(fen);
        return n >= min && n <= max;
    });
    if (fitting.length === 0) return null;
    return fitting[Math.floor(rng(seed)() * fitting.length)];
}

export interface PlacementScore {
    /** Squares where the piece stands correctly. */
    correct: string[];
    /** Squares with an error: wrong piece, extra or missing. */
    wrong: string[];
    /** 0-100: share of correct squares among all occupied in the original position or in the answer. */
    score: number;
}

export function scorePlacement(target: Placement, answer: Placement): PlacementScore {
    const squares = new Set([...Object.keys(target), ...Object.keys(answer)]);
    const correct: string[] = [];
    const wrong: string[] = [];
    for (const square of squares) (target[square] === answer[square] ? correct : wrong).push(square);
    correct.sort();
    wrong.sort();
    return {correct, wrong, score: squares.size === 0 ? 100 : Math.round((correct.length / squares.size) * 100)};
}

/** "Remember the game": how many plies to show at the level (6-24). */
export function recallPlies(level: number): number {
    return 4 + 2 * Math.min(10, Math.max(1, level));
}

export function pickGame<T extends { moves: string[] }>(games: T[], level: number, seed: number): T | null {
    const need = recallPlies(level);
    const fitting = games.filter((g) => g.moves.length >= need);
    return fitting.length ? fitting[Math.floor(rng(seed + 31)() * fitting.length)] : null;
}
