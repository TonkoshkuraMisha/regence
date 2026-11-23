// --- FILE: frontend/src/config/boardPrefs.ts ---
// Board settings (task 18.4): how to show the opponent's move, how to move, "quick move", opponent move animation and
// captured-piece order. Stored in the browser; components subscribe to changes.

import {useSyncExternalStore} from 'react';

export interface BoardPrefs {
    /** Opponent move: square highlight, arrow, or both. */
    lastMove: 'highlight' | 'arrow' | 'both';
    /** Move input: drag and click, or two clicks only (handy on a touchpad and phone). */
    moveInput: 'both' | 'click';
    /** "Quick move": clicking a square that only one of your pieces can reach makes the move immediately. */
    quickMove: boolean;
    /** Opponent move animation. */
    animateOpponent: boolean;
    /** Captured pieces: by value, by kind (from pawns) or by capture order. */
    captured: 'value' | 'kind' | 'order';
}

export const DEFAULT_BOARD_PREFS: BoardPrefs = {lastMove: 'highlight', moveInput: 'both', quickMove: false, animateOpponent: true, captured: 'value'};

const KEY = 'regence_board_prefs';
const ALLOWED: { [K in keyof BoardPrefs]: readonly BoardPrefs[K][] } = {
    lastMove: ['highlight', 'arrow', 'both'],
    moveInput: ['both', 'click'],
    quickMove: [true, false],
    animateOpponent: [true, false],
    captured: ['value', 'kind', 'order'],
};

function read(): BoardPrefs {
    try {
        const saved = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Partial<Record<keyof BoardPrefs, unknown>>;
        const prefs = {...DEFAULT_BOARD_PREFS};
        for (const key of Object.keys(ALLOWED) as (keyof BoardPrefs)[]) {
            if ((ALLOWED[key] as readonly unknown[]).includes(saved[key])) (prefs as Record<string, unknown>)[key] = saved[key];
        }
        return prefs;
    } catch {
        return {...DEFAULT_BOARD_PREFS};
    }
}

let current: BoardPrefs = read();
const listeners = new Set<() => void>();

export function getBoardPrefs(): BoardPrefs {
    return current;
}

export function setBoardPref<K extends keyof BoardPrefs>(key: K, value: BoardPrefs[K]): void {
    current = {...current, [key]: value};
    try {
        localStorage.setItem(KEY, JSON.stringify(current));
    } catch {
        // Storage unavailable - the setting holds until reload.
    }
    listeners.forEach((listener) => listener());
}

/** Re-read from storage (tests, another tab). */
export function reloadBoardPrefs(): void {
    current = read();
    listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

export function useBoardPrefs(): BoardPrefs {
    return useSyncExternalStore(subscribe, getBoardPrefs, getBoardPrefs);
}

const GLYPHS: Record<string, string> = {q: '♛', r: '♜', b: '♝', n: '♞', p: '♟'};
const VALUE_ORDER = ['q', 'r', 'b', 'n', 'p'];
const KIND_ORDER = ['p', 'n', 'b', 'r', 'q'];

/**
 * Pieces captured by each side in the required order. `byValue` - symbols already computed by material (as before);
 * capture order needs the game's move history (chess.js, verbose).
 */
export function orderCaptured(mode: BoardPrefs['captured'], byValue: { white: string[]; black: string[] },
                              history: { color: string; captured?: string }[]): { white: string[]; black: string[] } {
    if (mode === 'value') return byValue;
    if (mode === 'kind') {
        const sort = (list: string[]) => [...list].sort((a, b) => KIND_ORDER.indexOf(glyphType(a)) - KIND_ORDER.indexOf(glyphType(b)));
        return {white: sort(byValue.white), black: sort(byValue.black)};
    }
    const white: string[] = [];
    const black: string[] = [];
    for (const move of history) {
        if (!move.captured || !GLYPHS[move.captured]) continue;
        (move.color === 'w' ? white : black).push(GLYPHS[move.captured]);
    }
    return {white, black};
}

function glyphType(glyph: string): string {
    return VALUE_ORDER.find((type) => GLYPHS[type] === glyph) ?? 'p';
}

/** "Quick move": the only move of your piece to square `to`; otherwise null (no moves or the choice is ambiguous). */
export function quickMoveFrom(moves: { from: string; to: string; promotion?: string }[], to: string): string | null {
    const sources = new Set(moves.filter((m) => m.to === to).map((m) => m.from));
    return sources.size === 1 ? [...sources][0] : null;
}
