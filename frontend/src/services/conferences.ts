// --- FILE: frontend/src/services/conferences.ts ---
// Conferences (task 33.6): the Conference Cup for the season and the player's country in the profile. The rules and the country table are on
// the server (src/services/conferences.py); the client gets the «country → conference» table together with the page.
// Country names are not stored in the translation catalogs: the browser provides them (Intl.DisplayNames) in the UI language.
// Endpoints (src/api/conferences.py): GET /api/v1/conferences — the page, PUT /api/v1/conferences/me — the country.

import type {ConferenceKey} from './arenas';
import {apiRequest} from './http';

/** Conference Cup row: the sum of the conference's standings across the season's arenas. */
export interface CupRow {
    conference: ConferenceKey;
    score: number;
    /** In how many of the season's arenas the conference scored points. */
    arenas: number;
}

/** Conference match in the page list (conferences.matches on the server): score — win 1, draw ½. */
export interface MatchRow {
    arena_id: number;
    home: ConferenceKey;
    guest: ConferenceKey;
    starts_at: string;
    status: 'scheduled' | 'running' | 'closing' | 'finished';
    home_score: number;
    guest_score: number;
    /** How many players of both conferences signed up. */
    players: number;
}

/** Country and conference of the joined player (users.country on the server; the conference is determined by the country). */
export interface Membership {
    /** ISO 3166-1 alpha-2 country code from the profile; null — not specified. */
    country: string | null;
    conference: ConferenceKey | null;
    /** Whether the conference can be changed this season (one change per season). */
    can_change: boolean;
}

/** Response of GET /api/v1/conferences: the season's Cup, reference data for choosing a country and the joined player's data. */
export interface ConferencesData {
    /** Season «YYYY-MM» — a calendar month. */
    season: string;
    /** How many of a conference's best players count toward the arena standings. */
    top_players: number;
    table: CupRow[];
    /** Conference matches of the season and the nearest ones. */
    matches?: MatchRow[];
    /** The five conferences and the time zone (IANA) by whose local time the schedule of their arenas is built. */
    conferences: { key: ConferenceKey; timezone: string }[];
    /** Country code → conference: all countries that can be chosen. */
    countries: Record<string, ConferenceKey>;
    /** Country named by the proxy in front of the server — only a hint. */
    suggested_country: string | null;
    /** null — request without login. */
    me: Membership | null;
}

/** Request to /api/v1/conferences through the shared http.ts wrapper (token, JSON, errors). */
const call = <T>(path: string, init: RequestInit = {}) => apiRequest<T>(`/conferences${path}`, init);

export const conferencesApi = {
    /** Conferences page for the current season (the server accepts a season parameter but the client does not pass it). */
    page: () => call<ConferencesData>(''),
    /** null — remove the country from the profile. */
    setCountry: (country: string | null) => call<Membership>('/me', {method: 'PUT', body: JSON.stringify({country})}),
};

/** Country name in the UI language; if the browser does not know it — the code itself. */
export function countryName(code: string, language: string): string {
    try {
        return new Intl.DisplayNames([language], {type: 'region'}).of(code) ?? code;
    } catch {
        return code;
    }
}

/** Country from the browser language («uk-UA» → UA) — a fallback hint when the server did not name a country. */
export function localeCountry(languages: readonly string[] = navigator.languages ?? [navigator.language ?? '']): string | null {
    for (const tag of languages) {
        const region = /^[a-z]{2,3}[-_]([A-Za-z]{2})\b/.exec(tag)?.[1];
        if (region) return region.toUpperCase();
    }
    return null;
}
