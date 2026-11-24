// --- FILE: frontend/src/services/timeMachine.ts ---
// "Time Machine" (task 28.3): famous tournaments of the past that the player joins as an extra participant.
// The server provides keys and numbers (lineup, strength, real result); names, stories and names of people come from the catalog.
// Endpoints (src/api/tournaments.py): GET /api/v1/tournaments/time-machine — the tournament feed, open to guests too;
// POST /api/v1/tournaments/time-machine/{key} — join a tournament, sign-in only. Lineups and real results
// are recorded on the server in src/services/time_machine.py. Catalog: tournament names — timeMachine.events.<key>,
// masters of the past — bots.guests.<id>, historical bots — bots.profiles.<id>.

import {API_BASE_URL} from '../config/api';
import {UiError, readApiErrorOr} from './apiErrors';
import {ladderOpponentName} from '../config/players';
import {hasMessage} from '../i18n';
import type {I18n, MessageKey} from '../i18n';
import {getToken} from './authToken';
import type {Tournament, TournamentFormat} from './tournaments';

/** Prefix of the key under which a master of the past is saved as a tournament participant ("guest:<id>", as on the server). */
export const GUEST_PREFIX = 'guest:';

/** A participant of a historical tournament and their real result. */
export interface FieldEntry {
    id: string;
    /** bot — a historical master with a book and a portrait; guest — a master of the past (a tournament participant). */
    kind: 'bot' | 'guest';
    rating: number;
    /** Place in the real tournament; null — eliminated without a place (knockout tournament). */
    place: number | null;
    /** Points in the real tournament; null — a knockout tournament has no points. */
    score: number | null;
}

/** A famous tournament in the "Time Machine" feed. */
export interface HistoricEvent {
    key: string;
    year: number;
    format: TournamentFormat;
    /** Number of rounds of a round-robin (in each round everyone plays everyone). */
    cycles: number;
    /** Participants including the player. */
    size: number;
    rounds: number;
    /** How many games the player will play; null — depends on the player themselves (knockout). */
    player_games: number | null;
    /** The real table is incomplete: the tournament was not finished or draws gave no points. */
    partial?: boolean;
    field: FieldEntry[];
    /**
     * History of the joined player in this tournament: the id of their ongoing tournament (null — none), best place and how many
     * times they completed the tournament. A guest receives empty values.
     */
    active_id: number | null;
    best_place: number | null;
    played: number;
}

const BASE = `${API_BASE_URL}/api/v1/tournaments/time-machine`;

/** Request with a token if the player is signed in; a refusal is a UiError with text by server code or the fallback. */
async function call<T>(url: string, init: RequestInit, fallback: MessageKey): Promise<T> {
    const token = getToken();
    const res = await fetch(url, {
        ...init,
        headers: {
            ...(token ? {Authorization: `Bearer ${token}`} : {}),
            ...(init.body ? {'Content-Type': 'application/json'} : {}),
        },
    });
    if (!res.ok) throw new UiError(await readApiErrorOr(res, fallback));
    return res.json() as Promise<T>;
}

/** Feed of famous tournaments by year. */
export const getTimeMachine = () =>
    call<{ events?: HistoricEvent[] }>(BASE, {method: 'GET'}, 'timeMachine.loadFailed').then((r) => r.events ?? []);

/**
 * Join a tournament: the server creates the player's ordinary tournament with the full historical lineup and the chosen time
 * control; games between the masters are played out by the server. After that the tournament runs like any other (tournaments.ts).
 */
export const startHistoricEvent = (key: string, baseTimeMs: number, incrementMs: number) =>
    call<Tournament>(`${BASE}/${encodeURIComponent(key)}`, {
        method: 'POST', body: JSON.stringify({base_time_ms: baseTimeMs, increment_ms: incrementMs}),
    }, 'timeMachine.startFailed');

/** Full name of a master of the past in the player's language; an id without a translation is shown as is. */
export function guestName(id: string, t: I18n['t']): string {
    const key = `bots.guests.${id}.name`;
    return hasMessage(key) ? t(key as MessageKey) : id;
}

/** Short name (surname) — for tables and the tournament bracket, as with historical bots. */
export function guestShortName(id: string, t: I18n['t']): string {
    const key = `bots.guests.${id}.shortName`;
    return hasMessage(key) ? t(key as MessageKey) : guestName(id, t);
}

/** One line about a master of the past: who they are and how they played. */
export function guestAbout(id: string, t: I18n['t']): string | null {
    const key = `bots.guests.${id}.about`;
    return hasMessage(key) ? t(key as MessageKey) : null;
}

/** Full name of a historical tournament participant: for a master with a portrait — from the bot catalog, for a master of the past — their own. */
export function fieldName(entry: Pick<FieldEntry, 'id' | 'kind'>, t: I18n['t']): string {
    if (entry.kind === 'guest') return guestName(entry.id, t);
    const key = `bots.profiles.${entry.id}.name`;
    return hasMessage(key) ? t(key as MessageKey) : ladderOpponentName('historical', entry.id, t);
}

/** Short name of a participant — where space is tight. */
export function fieldShortName(entry: Pick<FieldEntry, 'id' | 'kind'>, t: I18n['t']): string {
    return entry.kind === 'guest' ? guestShortName(entry.id, t) : ladderOpponentName('historical', entry.id, t);
}

/** Points in the usual notation: 16.5 → "16½", 0.5 → "½". */
export function scoreText(score: number): string {
    const whole = Math.floor(score);
    const half = score - whole >= 0.5;
    return `${whole || !half ? whole : ''}${half ? '½' : ''}`;
}

/** Tournament name in the player's language; an unknown key — as is. */
export function eventTitle(key: string, t: I18n['t']): string {
    const message = `timeMachine.events.${key}.title`;
    return hasMessage(message) ? t(message as MessageKey) : key;
}

/** A row of the weekly legends table: the place in the table, the player and the place they took in the tournament. */
export interface LegendsRow {
    place: number;
    username: string;
    tournament_place: number;
    me: boolean;
}

/** The legends event of the week and the table of the best runs (GET /tournaments/legends-week, src/services/legends_week.py). */
export interface LegendsWeek {
    event_key: string;
    /** Monday (UTC) the week starts on and the next Monday, ISO dates. */
    starts_on: string;
    ends_on: string;
    rows: LegendsRow[];
    me: LegendsRow | null;
}

/** This week's announcement and table; open to guests too. */
export const getLegendsWeek = () =>
    call<LegendsWeek>(`${API_BASE_URL}/api/v1/tournaments/legends-week`, {method: 'GET'}, 'timeMachine.loadFailed');
