// --- FILE: frontend/src/services/botGameSnapshot.ts ---
// Snapshot of a game in progress against a bot in localStorage: a bot game lives only in the browser, and without a snapshot a page reload
// (or navigating to another page and back) lost the position, and in a tournament a repeated start counted as a loss
// (server: start_player_game, task A.2). The snapshot stores everything needed to continue: the PGN (with a «from own setup» position and
// odds), the player's color, the opponent, clocks, increment, ladder and tournament flags. Written by Chessboard.tsx on every move and
// when the page closes, read and applied by it on opening; erased when the game ends or is left.
// Rules: there is one snapshot (one bot game on the board), it belongs to the player (another account does not see it), it lives
// SNAPSHOT_TTL_MS; the clock of the side to move is reduced on resume by the time elapsed since the write (a reload does not
// stop the clock). The only storage is localStorage under the key regence_bot_game.

import type {CustomOpponent} from '../config/archetypes';

// localStorage key holding the snapshot.
const STORAGE_KEY = 'regence_bot_game';
// Format version: a snapshot of another version is ignored (we do not try to read a foreign structure).
const SNAPSHOT_VERSION = 1;
// How long a snapshot counts as alive (ms): a day — a bot game does not last longer, beyond that it is a forgotten game.
export const SNAPSHOT_TTL_MS = 24 * 60 * 60 * 1000;

/** Game odds: kind and who gives them (as in chessboard/odds.ts); strings, so as not to depend on the board module. */
export interface SnapshotOdds {
    kind: string;
    giver: string;
}

export interface BotGameSnapshot {
    version: number;
    /** When it was written (ms since the epoch) — the time spent on the reload is counted from it. */
    savedAt: number;
    /** Player name: another account does not get the snapshot. */
    username: string;
    /** id of a historical bot or «custom» (then the opponent is in custom). */
    botId: string;
    custom: CustomOpponent | null;
    color: 'white' | 'black';
    /** The whole game as PGN: with FEN and SetUp headers if it did not start from the standard setup. */
    pgn: string;
    whiteTimeMs: number;
    blackTimeMs: number;
    /** Base time (minutes) and increment (seconds) of the game — for the clocks after resuming. */
    baseMinutes: number;
    incrementSeconds: number;
    odds: SnapshotOdds | null;
    ladder: boolean;
    /** Tournament game: the number of the schedule game and of the tournament — otherwise null. */
    tournamentGameId: number | null;
    tournamentId: number | null;
    /** The game was paused: on resume the clocks are not reduced by the reload time (snapshots without the field — not paused). */
    paused?: boolean;
}

/** Saves the snapshot; storage unavailable — silently (resuming a game is a convenience, not a guarantee). */
export function saveBotGameSnapshot(snapshot: Omit<BotGameSnapshot, 'version' | 'savedAt'>, now: number = Date.now()): void {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({...snapshot, version: SNAPSHOT_VERSION, savedAt: now}));
    } catch {
        // Full or forbidden — without a snapshot the game simply will not survive a reload.
    }
}

/** Erases the snapshot (the game is over, abandoned, or the result is already recorded). */
export function clearBotGameSnapshot(): void {
    try {
        localStorage.removeItem(STORAGE_KEY);
    } catch {
        // Nothing to do.
    }
}

/** Whether the parsed value fits as a snapshot of the current version: fields of the right types, clocks and PGN present. */
function isSnapshot(value: unknown): value is BotGameSnapshot {
    if (!value || typeof value !== 'object') return false;
    const s = value as Record<string, unknown>;
    return s.version === SNAPSHOT_VERSION
        && typeof s.savedAt === 'number' && typeof s.username === 'string' && typeof s.botId === 'string'
        && (s.color === 'white' || s.color === 'black') && typeof s.pgn === 'string'
        && typeof s.whiteTimeMs === 'number' && typeof s.blackTimeMs === 'number'
        && typeof s.baseMinutes === 'number' && typeof s.incrementSeconds === 'number'
        && typeof s.ladder === 'boolean'
        && (s.tournamentGameId === null || typeof s.tournamentGameId === 'number')
        && (s.tournamentId === null || typeof s.tournamentId === 'number');
}

/**
 * Snapshot for this player if it exists, is fresh and intact; otherwise null (and a corrupted or expired one is erased).
 * username — the current player: another account's snapshot is neither returned nor erased (its owner still needs it).
 */
export function loadBotGameSnapshot(username: string, now: number = Date.now()): BotGameSnapshot | null {
    let raw: string | null;
    try {
        raw = localStorage.getItem(STORAGE_KEY);
    } catch {
        return null;
    }
    if (raw === null) return null;
    let parsed: unknown;
    try {
        parsed = JSON.parse(raw);
    } catch {
        parsed = null;
    }
    if (!isSnapshot(parsed) || now - parsed.savedAt > SNAPSHOT_TTL_MS || parsed.savedAt > now + SNAPSHOT_TTL_MS) {
        clearBotGameSnapshot();
        return null;
    }
    return parsed.username === username ? parsed : null;
}

/**
 * Clocks after resuming: from the side to move the time elapsed since the snapshot was written is subtracted (a reload does not
 * stop the clock, but a paused game does not reduce it); not below zero — a fallen flag is handled by the usual time check.
 */
export function clocksAfterGap(
    snapshot: Pick<BotGameSnapshot, 'whiteTimeMs' | 'blackTimeMs' | 'savedAt'> & { paused?: boolean }, whiteToMove: boolean, now: number = Date.now(),
): { white: number; black: number } {
    const gap = snapshot.paused ? 0 : Math.max(0, now - snapshot.savedAt);
    return {
        white: whiteToMove ? Math.max(0, snapshot.whiteTimeMs - gap) : snapshot.whiteTimeMs,
        black: whiteToMove ? snapshot.blackTimeMs : Math.max(0, snapshot.blackTimeMs - gap),
    };
}
