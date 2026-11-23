// --- FILE: frontend/src/services/transparency.ts ---
// Transparency and open data (task 24.3): bot calibration logs, information about the open API and export of one's own
// games as a single PGN file.
// Endpoints: GET /api/v1/bots/calibration/runs, /bots/calibration/runs/{name} and /bots/tuning-log (src/api/bots.py),
// GET /api/v1/bots/engine (engine info for the "About" page, GPL), GET /api/v1/public (src/api/public.py) - all open without sign-in, with the open-API rate limit; own games -
// GET /api/v1/account/games.pgn (src/api/account.py), sign-in only.

import {apiFetch, apiRequest, apiUrl} from './http';

/** Engine of this installation (GET /bots/engine): its exact version and source - a GPL requirement (task 23.1). */
export interface EngineInfo {
    name: string | null;
    source_url: string;
}

/** Installation engine info (src/api/bots.py); open without sign-in. */
export const fetchEngineInfo = () => apiRequest<EngineInfo>('/bots/engine');

/** Info about the latest calibration (meta section of src/services/bots/calibration.json). */
export interface CalibrationMeta {
    date: string;
    games: number;
    /** Ratings of the Stockfish references the bots played against, and the reference time per move in seconds. */
    anchors?: number[];
    anchor_movetime_s?: number;
}

/** Calibration run log: log - match protocol, pgn - the games themselves; size - file size in bytes. */
export interface CalibrationRun {
    name: string;
    date: string;
    title: string;
    kind: 'log' | 'pgn';
    size: number;
}

/** Open API description (GET /api/v1/public): version, list of addresses and request limit. */
export interface PublicApiInfo {
    version: number;
    endpoints: string[];
    rate_limit: { requests: number; window_s: number };
}

/**
 * Log of personality tuning by self-play (task 32.3, table bot_tuning_log): what was measured (measured) against the
 * declared strength (target) and how the strength sliders were shifted - "was, became" pairs.
 */
export interface TuningEntry {
    key: string;
    created_at: string | null;
    games: number;
    measured: number;
    target: number;
    randomness: [number, number];
    blunder_guard_cp: [number, number];
}

/** Tuning log and rules: games per measurement (games) and divergence threshold (drift). */
export interface TuningLog {
    entries: TuningEntry[];
    rules: { games: number; drift: number };
}

/** Direct link to the run log file - for downloading. */
export const runUrl = (name: string) => apiUrl(`/bots/calibration/runs/${encodeURIComponent(name)}`);

export const transparencyApi = {
    runs: () => apiRequest<{ calibration: CalibrationMeta | null; runs: CalibrationRun[] }>('/bots/calibration/runs'),
    /** Run log - text, not JSON. */
    runText: async (name: string) => (await apiFetch(`/bots/calibration/runs/${encodeURIComponent(name)}`)).text(),
    publicApi: () => apiRequest<PublicApiInfo>('/public'),
    tuningLog: () => apiRequest<TuningLog>('/bots/tuning-log'),
};

/** Save text as a file (one-day link: CSP allows blob:). */
export function saveTextFile(text: string, filename: string, type: string): void {
    const url = URL.createObjectURL(new Blob([text], {type}));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
}

/**
 * All own finished games as one PGN; returns the number of games (0 - nothing to export, no file is created).
 * The server reports the number in the X-Total-Count header; if the header is missing it is counted by [Event tags in the text.
 */
export async function downloadMyGamesPgn(username: string | null): Promise<number> {
    const res = await apiFetch('/account/games.pgn', {}, 'settings.exportFailed');
    const text = await res.text();
    const total = Number(res.headers.get('X-Total-Count') ?? 0);
    if (!text.trim()) return 0;
    saveTextFile(text, `regence-${username ?? 'games'}.pgn`, 'application/x-chess-pgn');
    return total || text.split('[Event ').length - 1;
}
