// --- FILE: frontend/src/config/blindfold.ts ---
// Blindfold play (task 19.5). Levels: 1 - only own pieces visible; 2 - a piece disappears after FADE_PLIES plies
// following its last move; 3 - only pawns visible; 4 - fully blindfold. "Peek" shows everything for
// PEEK_MS (peeks are counted in the results). Unrated games only.

import {useSyncExternalStore} from 'react';

export type BlindfoldLevel = 0 | 1 | 2 | 3 | 4;
export const BLINDFOLD_LEVELS: BlindfoldLevel[] = [1, 2, 3, 4];
export const FADE_PLIES = 4;
export const PEEK_MS = 3000;

interface BoardPiece {
    type: string;
    color: 'w' | 'b';
}

/** Squares whose pieces are visible at the given level. `history` - game moves (verbose), `board` - chess.js board(). */
export function visibleSquares(level: BlindfoldLevel, board: (BoardPiece | null)[][], history: { to: string }[], myColor: 'w' | 'b'): Set<string> {
    const visible = new Set<string>();
    const recent = new Set(history.slice(-FADE_PLIES).map((m) => m.to));
    board.forEach((row, r) => row.forEach((piece, f) => {
        if (!piece) return;
        const square = `${'abcdefgh'[f]}${8 - r}`;
        const show = level === 0 || (level === 1 && piece.color === myColor) || (level === 2 && recent.has(square))
            || (level === 3 && piece.type === 'p');
        if (show) visible.add(square);
    }));
    return visible;
}

export interface BlindfoldState {
    /** Level chosen for the next game (0 - ordinary game). */
    armed: BlindfoldLevel;
    /** Level of the current game (0 - ordinary game). */
    level: BlindfoldLevel;
    peeks: number;
    peekUntil: number;
    hideMoves: boolean;
}

const KEY = 'regence_blindfold_level';

function readArmed(): BlindfoldLevel {
    try {
        const saved = Number(localStorage.getItem(KEY));
        return ([0, 1, 2, 3, 4] as number[]).includes(saved) ? saved as BlindfoldLevel : 0;
    } catch {
        return 0;
    }
}

let state: BlindfoldState = {armed: readArmed(), level: 0, peeks: 0, peekUntil: 0, hideMoves: false};
const listeners = new Set<() => void>();

function update(patch: Partial<BlindfoldState>): void {
    state = {...state, ...patch};
    listeners.forEach((listener) => listener());
}

export function getBlindfold(): BlindfoldState {
    return state;
}

export function armBlindfold(level: BlindfoldLevel): void {
    try {
        localStorage.setItem(KEY, String(level));
    } catch {
        // without storage the choice holds until reload
    }
    update({armed: level});
}

/** New game: blindfold if a level is chosen and the game may be blindfold (unrated). */
export function startBlindfold(allowed: boolean): void {
    update({level: allowed ? state.armed : 0, peeks: 0, peekUntil: 0, hideMoves: false});
}

export function stopBlindfold(): void {
    update({level: 0, peeks: 0, peekUntil: 0, hideMoves: false});
}

export function peek(now = Date.now()): void {
    if (state.level === 0 || state.peekUntil > now) return;
    update({peeks: state.peeks + 1, peekUntil: now + PEEK_MS});
    setTimeout(() => update({}), PEEK_MS + 20);
}

export function setHideMoves(hide: boolean): void {
    update({hideMoves: hide});
}

function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

export function useBlindfold(): BlindfoldState {
    return useSyncExternalStore(subscribe, getBlindfold, getBlindfold);
}

/** Move in notation (SAN or "e2e4"): from/to/promotion for the current position; null - illegal move. */
export function parseMoveInput(moves: { san: string; from: string; to: string; promotion?: string }[], input: string):
    { from: string; to: string; promotion?: string } | null {
    const text = input.trim().replace(/[+#!?]+$/, '').replace(/0/g, 'O');
    if (!text) return null;
    const uci = /^([a-h][1-8])-?([a-h][1-8])([qrbn])?$/i.exec(text);
    const found = uci
        ? moves.find((m) => m.from === uci[1].toLowerCase() && m.to === uci[2].toLowerCase()
            && (m.promotion ?? '') === (uci[3]?.toLowerCase() ?? (m.promotion ? 'q' : '')))
        : moves.find((m) => m.san.replace(/[+#]$/, '') === text) ?? moves.find((m) => m.san.replace(/[+#]$/, '').toLowerCase() === text.toLowerCase());
    return found ? {from: found.from, to: found.to, promotion: found.promotion} : null;
}
