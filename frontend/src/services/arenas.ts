// --- FILE: frontend/src/services/arenas.ts ---
// Arenas — tournaments between humans (task 17.2): schedule, joining, «Play» (waiting for a pairing), standings, reminder.
// All requests go to /api/v1/arenas (routes in src/api/arenas.py); rules, points, statuses and standings are computed by the server
// (src/services/arena.py), the per-conference schedule — src/services/arena_schedule.py. The client only displays.

import {apiRequest} from './http';

/** closing (33.1): no more pairings — the last games are finishing or time until the end is running; results — in finished. */
export type ArenaStatus = 'scheduled' | 'running' | 'closing' | 'finished';

/**
 * Arena card — as the server builds it (arena.view in src/services/arena.py). Comes in the list (GET /arenas),
 * in the lobby announcement (GET /arenas/current) and as the basis of the arena page (ArenaDetail).
 */
export interface ArenaInfo {
    id: number;
    /** Schedule slot key; null — the arena was not created by the schedule. */
    schedule_key: string | null;
    /** arena — by time, swiss — by rounds (17.2). */
    format?: 'arena' | 'swiss' | 'match';
    /** Swiss only: total rounds and the number of the current one. */
    rounds?: number;
    current_round?: number;
    base_time_ms: number;
    increment_ms: number;
    /** Start and end — ISO time with zone (UTC); the server derives the status from them and from the number of running games. */
    starts_at: string;
    ends_at: string;
    status: ArenaStatus;
    /** Number of participants: present in the list and the announcement; on the arena page the standings length replaces it. */
    players?: number;
    /** «Berserk» is available in arena games (33.3): half the time without increment for an extra point for a win. */
    berserk?: boolean;
    /** Last start: pairings are created until then (arena format only). */
    last_start_at?: string;
    /** Running arena games — the results wait for them. */
    open_games?: number;
    /** Division on overflow (33.2): 1 — the main one. */
    division?: number;
    /** The main arena this division was split from; null — this is the main one. */
    parent_id?: number | null;
    /** Conference whose schedule the arena follows (33.4): central | western | northern | southern | eastern. */
    conference?: string | null;
    /** Conference match: the guest conference (the host is conference). */
    opponent_conference?: string | null;
    /** Evening 5+3 arena — the main arena of the day for its conference (33.4). */
    evening?: boolean;
}

/** Keys of the five conferences — the same as on the server (src/services/conferences.py); names — the conferences catalog. */
export const CONFERENCES = ['central', 'western', 'northern', 'southern', 'eastern'] as const;
export type ConferenceKey = typeof CONFERENCES[number];

/** Server string → conference key; null — empty or a key the client does not know (the server is newer). */
export function conferenceKey(value: string | null | undefined): ConferenceKey | null {
    return (CONFERENCES as readonly string[]).includes(value ?? '') ? value as ConferenceKey : null;
}

/** Arena standings row (arena.standings on the server): places are already assigned by the server. */
export interface ArenaStanding {
    place: number;
    username: string;
    /** Arena points: win 2, draw 1; during a «fire» streak — doubled. */
    score: number;
    games: number;
    wins: number;
    /** «Fire»: the win streak at which the next game's points are doubled. */
    fire: boolean;
    /** The player's rating in the arena's time control at the moment of joining. */
    rating: number;
    /** Performance in the arena — the first tiebreak on equal points. */
    performance?: number | null;
    /** The player's conference at the moment of joining the arena (33.6); null — no country in the profile. */
    conference?: string | null;
}

/** Conference standings row of an arena (33.6): the sum of points of the conference's best participants. */
export interface ArenaConferenceRow {
    conference: string;
    score: number;
    /** How many players count toward the standings and how many players of the conference are in the arena in total. */
    counted: number;
    players: number;
}

/** Player on a conference match board: points in match units (win 1, draw ½). */
export interface MatchSeat {
    username: string;
    rating: number;
    score: number;
}

/**
 * Conference match (arena.match_view on the server): host and guest, score, how many signed up on each side, whether
 * sign-up is open, and boards (before the start — a provisional lineup by rating).
 */
export interface MatchDetail {
    home: string;
    guest: string;
    home_score: number;
    guest_score: number;
    home_players: number;
    guest_players: number;
    entry_open: boolean;
    boards: { board: number; home: MatchSeat; guest: MatchSeat }[];
}

/** Arena page (GET /arenas/{id}): card, standings, conference standings and the joined player's state. */
export interface ArenaDetail extends ArenaInfo {
    standings: ArenaStanding[];
    conferences?: ArenaConferenceRow[];
    /** Only for a conference match (format 'match'). */
    match?: MatchDetail | null;
    /**
     * Player state; null — request without login. waiting — waiting for a pairing, current_game_id — their running arena game.
     * division_arena_id: the player is in another division of this arena — the client navigates there (33.2).
     * reminder: the player asked to be reminded of this arena's start (33.4).
     * podium_place: prize place 1–3 after the final results (33.5); null — not a prizewinner or no results yet.
     * username: the player's name — the results screen uses it to highlight their row in the standings.
     */
    me: {
        username?: string;
        joined: boolean; waiting: boolean; current_game_id: number | null; division_arena_id?: number | null;
        reminder?: boolean; podium_place?: number | null;
    } | null;
}

/** League time-control category (like the rating categories). */
export type LeagueCategory = 'bullet' | 'blitz' | 'rapid' | 'classical';

/** Row of the monthly arena league (src/services/arena_league.py): places are assigned by the server. */
export interface LeagueRow {
    place: number;
    username: string;
    /** Sum of the season's arena points in the category. */
    score: number;
    /** Points of the best arena — the first tiebreak on equal sums. */
    best: number;
    /** In how many arenas the player played at least one game. */
    arenas: number;
}

/** Response of GET /arenas/league: the season's league «YYYY-MM» in a category; me — the joined player's row or null. */
export interface ArenaLeague {
    season: string;
    category: LeagueCategory;
    /** Categories in which the schedule sets up arenas — the league tabs. */
    categories: LeagueCategory[];
    /** How many players are in the league in total (table has only the first rows). */
    players: number;
    table: LeagueRow[];
    me: LeagueRow | null;
}

/** Request to /api/v1/arenas through the shared http.ts wrapper (token, JSON, errors). */
const call = <T>(path: string, init: RequestInit = {}) => apiRequest<T>(`/arenas${path}`, init);

/** Arena endpoints. list, current, get and league are open without login; the rest require a token. */
export const arenasApi = {
    /** Running, upcoming (6 hours ahead) and recently finished arenas. */
    list: () => call<{ arenas: ArenaInfo[] }>(''),
    /** Lobby announcement: the running arena with the most players, otherwise the nearest by start; null — no arenas. */
    current: () => call<{ arena: ArenaInfo | null }>('/current'),
    get: (id: number) => call<ArenaDetail>(`/${id}`),
    /** Monthly arena league of the current season in a time-control category. */
    league: (category: LeagueCategory) => call<ArenaLeague>(`/league?category=${category}`),
    /** arena_id — the division the player landed in (on overflow — not the arena that was requested). */
    join: (id: number) => call<{ joined: boolean; arena_id?: number }>(`/${id}/join`, {method: 'POST'}),
    /** «Play»: either an immediate pairing (game_id) or waiting (waiting) — then the client repeats the request. */
    ready: (id: number) => call<{ waiting?: boolean; game_id?: number }>(`/${id}/ready`, {method: 'POST'}),
    /** Leave the pairing queue while remaining an arena participant. */
    leaveWaiting: (id: number) => call<{ waiting: boolean }>(`/${id}/leave-waiting`, {method: 'POST'}),
    /** «Remind»: a notification arrives shortly before the arena starts; forgetReminder — cancel. */
    remind: (id: number) => call<{ reminder: boolean }>(`/${id}/remind`, {method: 'POST'}),
    forgetReminder: (id: number) => call<{ reminder: boolean }>(`/${id}/remind`, {method: 'DELETE'}),
};

/** Time control as a label «minutes+increment seconds», for example «3+2». */
export function controlLabel(a: Pick<ArenaInfo, 'base_time_ms' | 'increment_ms'>): string {
    return `${Math.round(a.base_time_ms / 60000)}+${Math.round(a.increment_ms / 1000)}`;
}

/** Seconds until a moment (not less than zero). */
export function secondsUntil(iso: string, now = Date.now()): number {
    return Math.max(0, Math.round((new Date(iso).getTime() - now) / 1000));
}

/** Seconds → «m:ss», and from one hour — «h:mm:ss» (countdown to the start and end of an arena). */
export function clock(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}
