// --- FILE: frontend/src/services/masters.ts ---
// Catalog of masters of the past (task 28.5): participants of "Time Machine" tournaments, each can be played in a separate
// game. The server returns keys and numbers; the name and the line about a master come from catalogs by id (services/timeMachine.ts).
// Endpoints (src/api/bots.py, open without login): GET /api/v1/bots/guests — list, GET /api/v1/bots/guests/{id} —
// one master's character. The masters themselves are described on the server in src/services/bots/guests.py.

import {API_BASE_URL} from '../config/api';
import {UiError, readApiErrorOr} from './apiErrors';
import type {MessageKey} from '../i18n';
import type {PersonalityConfig} from './personalities';

/** Master of the past in the opponent catalog. */
export interface Master {
    id: string;
    /** Name for PGN and archive: "Surname, Name" in Latin letters. */
    pgn_name: string;
    /** Lifespan "1806–1853"; null — no reliable dates. */
    era: string | null;
    /** Strength of the master bot: set from historical estimates relative to calibrated bots, not measured by matches. */
    rating: number;
    /** Keys of the historical tournaments the master played in, by year. */
    events: string[];
    /** Signature openings — names from the open openings table. */
    openings: { white: string[]; black: string[] };
}

/** Player colour in a game with a master; random — by lot. */
export type MasterColor = 'white' | 'black' | 'random';

/** Route state with which the board starts a game with a master (Chessboard.tsx). */
export interface MasterGameStart {
    /** Name in the player's language — on the board. */
    name: string;
    /** Name from the PGN — the game is saved on the server under it. */
    savedName: string;
    config: PersonalityConfig;
    color: MasterColor;
}

const BASE = `${API_BASE_URL}/api/v1/bots/guests`;

async function call<T>(url: string, fallback: MessageKey): Promise<T> {
    const res = await fetch(url);
    if (!res.ok) throw new UiError(await readApiErrorOr(res, fallback));
    return res.json() as Promise<T>;
}

/** All masters of the catalog (GET /bots/guests); error — UiError with the text masters.loadFailed. */
export const getMasters = () =>
    call<{ guests?: Master[] }>(BASE, 'masters.loadFailed').then((r) => r.guests ?? []);

/** Master's character — the same with which they play in the historical tournament. */
export const getMasterConfig = (id: string) =>
    call<{ id: string; pgn_name: string; rating: number; config: PersonalityConfig }>(
        `${BASE}/${encodeURIComponent(id)}`, 'masters.startFailed');

/** Master list order — see sortMasters. */
export type MasterOrder = 'strength' | 'years' | 'name';

/** Birth year; null — lifespan unknown. */
export function birthYear(master: Pick<Master, 'era'>): number | null {
    const year = master.era ? Number.parseInt(master.era, 10) : Number.NaN;
    return Number.isFinite(year) ? year : null;
}

/** List order: by strength (strongest first), by lifespan (oldest first, undated — at the end) or by name. */
export function sortMasters(list: Master[], order: MasterOrder, nameOf: (master: Master) => string, locale?: string): Master[] {
    const byName = (a: Master, b: Master) => nameOf(a).localeCompare(nameOf(b), locale);
    return [...list].sort((a, b) => {
        if (order === 'strength') return b.rating - a.rating || byName(a, b);
        if (order === 'years') {
            const [ya, yb] = [birthYear(a), birthYear(b)];
            if (ya === null || yb === null) return ya === yb ? byName(a, b) : ya === null ? 1 : -1;
            return ya - yb || byName(a, b);
        }
        return byName(a, b);
    });
}

/** Search by name: in the player's language or in Latin letters, as in the PGN; case-insensitive. */
export function matchesQuery(master: Pick<Master, 'pgn_name'>, name: string, query: string): boolean {
    const needle = query.trim().toLocaleLowerCase();
    return !needle || name.toLocaleLowerCase().includes(needle) || master.pgn_name.toLocaleLowerCase().includes(needle);
}
