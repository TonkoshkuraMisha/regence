// --- FILE: frontend/src/services/tournaments.ts ---
// Tournaments with historical masters (tasks 15.1-15.3): API and participant labels in the player's language.
// All requests go to /api/v1/tournaments and require sign-in (routes in src/api/tournaments.py). Schedule, seats and
// match rules live in src/services/tournament_rules.py; games between bots are played by the server in the background
// (tournament_simulation.py). The player's game result is not sent here: it arrives with the saving of the played
// game (POST /api/v1/bots/save-game with the tournament_game_id field) - the outcome cannot be submitted directly.

import type {PersonalityConfig} from './personalities';
import {ARCHETYPE_PREFIX, isArchetypeId} from '../config/archetypes';
import type {CustomOpponent} from '../config/archetypes';
import {ladderOpponentName} from '../config/players';
import type {I18n, MessageKey} from '../i18n';
import {apiRequest} from './http';
import {GUEST_PREFIX, guestShortName} from './timeMachine';

export type TournamentFormat = 'round_robin' | 'knockout' | 'swiss';
/** Swiss system (task 15.4): number of rounds by size - same as on the server (tournament_rules.SWISS_ROUNDS). */
export const SWISS_ROUNDS: Record<number, number> = {6: 4, 8: 5};
/** Bot opponent: historical bot, workshop archetype or persona (custom one or a master of the past). */
export type ParticipantKind = 'bot' | 'archetype' | 'personality';

/** Tournament participant. */
export interface TournamentPlayer {
    /** Participant number - their seed: 1 is the strongest by rating at the start. */
    seat: number;
    kind: 'user' | ParticipantKind;
    user_id: number | null;
    /** id of a historical bot, "archetype:<id>" or "guest:<id>" of a master of the past; null for the player. */
    bot_key: string | null;
    personality_name: string | null;
    rating: number;
    /** Final place; null - the tournament is still running. */
    place: number | null;
    /** Knockout: the round in which the participant was eliminated. */
    eliminated_round: number | null;
    /** Workshop opponent's character - the board starts the game with it; null for a historical bot and for the player. */
    config: PersonalityConfig | null;
}

/** Tournament schedule game. */
export interface TournamentGame {
    id: number;
    round: number;
    board: number;
    /**
     * Knockout: main - the main game of the match, rematch - replay after a draw (colors swap, time control
     * half as long), armageddon - the decisive game where Black needs only a draw.
     */
    stage: 'main' | 'rematch' | 'armageddon';
    white_seat: number;
    black_seat: number;
    base_time_ms: number;
    increment_ms: number;
    /** null - the game has not been played yet. */
    result: '1-0' | '0-1' | '1/2-1/2' | null;
    /** Saved game (games table) - for viewing; null - there is none. */
    game_id: number | null;
}

/**
 * Table row. Places in a round-robin: points, then head-to-head among those tied, then the
 * Sonneborn-Berger coefficient, then seed; buchholz comes only in the Swiss system.
 */
export interface Standing {
    seat: number;
    points: number;
    head_to_head: number;
    sonneborn_berger: number;
    buchholz?: number;
    place: number;
}

/** Whole tournament (GET /tournaments/{id}): participants, schedule with results and the table. */
export interface Tournament {
    id: number;
    format: TournamentFormat;
    size: number;
    status: 'active' | 'finished';
    base_time_ms: number;
    increment_ms: number;
    current_round: number;
    created_at: string;
    finished_at: string | null;
    /** Number of the player themself among the participants. */
    my_seat: number | null;
    /** The player resigned the tournament: bots finish their games, the player no longer plays. */
    withdrawn: boolean;
    /** "Time machine": key of a famous tournament; an ordinary tournament has none. */
    event_key?: string | null;
    players: TournamentPlayer[];
    games: TournamentGame[];
    standings: Standing[];
}

/** Tournament in the player's list (GET /tournaments, newest first). */
export interface TournamentSummary {
    id: number;
    format: TournamentFormat;
    size: number;
    status: 'active' | 'finished';
    created_at: string;
    my_place: number | null;
    /** Career stage key, if the tournament was started from it. */
    career_stage?: string | null;
    event_key?: string | null;
    /** Current round and whether the player's game in it is ready ("Continue tournament" on the home page). */
    current_round: number;
    my_game_ready: boolean;
}

/** Tournament creation body (POST /tournaments). size - number of participants including the player (4 to 8). */
export interface TournamentCreate {
    format: TournamentFormat;
    size: number;
    participants: { kind: ParticipantKind; id: string | number }[];
    /** Random opponents from a strength range (task 15.4) instead of chosen ones. */
    random?: RandomOpponents;
    base_time_ms: number;
    increment_ms: number;
}

/** Tournament game that the player launches on the main board (passed via location.state). */
export interface TournamentGameStart {
    tournamentId: number;
    gameId: number;
    color: 'white' | 'black';
    baseTimeMs: number;
    incrementMs: number;
    /** Historical bot - by id; workshop opponent - by name and character. */
    botId: string | null;
    custom: CustomOpponent | null;
}

const BASE = '/tournaments';

/** Request to the tournaments API (shared apiRequest); on a failure without a server code - the fallback message. */
const call = <T>(path: string, init: RequestInit, fallback: MessageKey) => apiRequest<T>(path, init, fallback);

/** Allowed tournament sizes per format - GET /tournaments/formats (source of truth is the server). */
export const getFormatSizes = () =>
    call<Record<TournamentFormat, number[]>>(`${BASE}/formats`, {method: 'GET'}, 'tournaments.loadFailed');

export const listTournaments = () => call<TournamentSummary[]>(BASE, {method: 'GET'}, 'tournaments.loadFailed');
export const getTournament = (id: number) => call<Tournament>(`${BASE}/${id}`, {method: 'GET'}, 'tournaments.loadFailed');
/** Start your game (task A.2): restarting an already started game is a loss, forfeited = true. */
export const startMyGame = (tournamentId: number, gameId: number) =>
    call<{ forfeited: boolean; game: TournamentGame }>(
        `${BASE}/${tournamentId}/games/${gameId}/start`, {method: 'POST'}, 'tournaments.loadFailed',
    );

/** Resign the tournament (task A.3): the player's remaining games are losses. */
export const withdrawTournament = (tournamentId: number) =>
    call<Tournament>(`${BASE}/${tournamentId}/withdraw`, {method: 'POST'}, 'tournaments.loadFailed');

/** Random opponents: around the player's strength, stronger or weaker - picked by the server. */
export type RandomOpponents = 'my_level' | 'stronger' | 'weaker';

/** Career stage (task 15.4); a hidden invitation has no details. */
export interface CareerStage {
    key: string;
    number: number;
    invitational: boolean;
    hidden: boolean;
    unlocked: boolean;
    best_place: number | null;
    format?: TournamentFormat;
    size?: number;
    base_time_ms?: number;
    increment_ms?: number;
    target?: number;
    opponents?: { kind: ParticipantKind; id: string | number }[];
}

/** Career: ladder stages of ready-made tournaments (src/services/tournament_career.py). */
export const getCareer = () => call<{ stages: CareerStage[] }>(`${BASE}/career`, {method: 'GET'}, 'tournaments.loadFailed');
/** Start a career-stage tournament; the server will not start a locked stage (403). */
export const startCareerStage = (key: string) =>
    call<Tournament>(`${BASE}/career/${encodeURIComponent(key)}`, {method: 'POST'}, 'tournaments.createFailed');

/** Create your own tournament; the server immediately queues the first-round bot games for simulation. */
export const createTournament = (body: TournamentCreate) =>
    call<Tournament>(BASE, {method: 'POST', body: JSON.stringify(body)}, 'tournaments.createFailed');

/** id of the master of the past ("Time machine") if the participant is one; in a tournament such a participant is a persona with a key. */
export function guestIdOf(player: Pick<TournamentPlayer, 'kind' | 'bot_key'>): string | null {
    return player.kind === 'personality' && player.bot_key?.startsWith(GUEST_PREFIX)
        ? player.bot_key.slice(GUEST_PREFIX.length) : null;
}

/** Opponent page: for a master of the past - their catalog card; the others have no separate page. */
export function opponentPage(player: Pick<TournamentPlayer, 'kind' | 'bot_key'>): string | null {
    const guest = guestIdOf(player);
    return guest ? `/masters?master=${encodeURIComponent(guest)}` : null;
}

/** The player's last played game in the tournament. */
export function myLastGame(t: Tournament): TournamentGame | null {
    if (t.my_seat == null) return null;
    const mine = t.games.filter((g) => g.result && (g.white_seat === t.my_seat || g.black_seat === t.my_seat));
    return mine.sort((a, b) => b.round - a.round || b.id - a.id)[0] ?? null;
}

/** Participant name in the player's language: "You", a bot, an archetype, a master of the past or a persona name. */
export function participantName(player: TournamentPlayer, t: I18n['t'], myName?: string): string {
    if (player.kind === 'user') return myName || t('tournaments.you');
    const guest = guestIdOf(player);
    if (guest) return guestShortName(guest, t);
    if (player.kind === 'bot' && player.bot_key) return ladderOpponentName('historical', player.bot_key, t);
    if (player.kind === 'archetype' && player.bot_key) {
        return ladderOpponentName('archetype', player.bot_key.slice(ARCHETYPE_PREFIX.length), t);
    }
    return player.personality_name ?? '?';
}

/** The player's game that can be played now: current round, no result. */
export function myPendingGame(t: Tournament): TournamentGame | null {
    if (t.status !== 'active' || t.my_seat == null || t.withdrawn) return null;
    const mine = t.games.filter((g) => g.result === null && g.round === t.current_round
        && (g.white_seat === t.my_seat || g.black_seat === t.my_seat));
    return mine[0] ?? null;
}

/** What to pass to the main board to start a tournament game. */
export function gameStart(t: Tournament, game: TournamentGame, name: string): TournamentGameStart {
    const color = game.white_seat === t.my_seat ? 'white' : 'black';
    const opponent = t.players.find((p) => p.seat === (color === 'white' ? game.black_seat : game.white_seat))!;
    const archetypeId = opponent.kind === 'archetype' && opponent.bot_key
        ? opponent.bot_key.slice(ARCHETYPE_PREFIX.length) : null;
    // Master of the past: the board shows the name in the player's language, the game is saved under the name from the tournament.
    const guest = guestIdOf(opponent) !== null;
    const custom: CustomOpponent | null = opponent.kind === 'bot' || !opponent.config ? null : {
        name: guest ? name : opponent.personality_name ?? name,
        ...(guest && opponent.personality_name ? {savedName: opponent.personality_name} : {}),
        config: opponent.config,
        ...(isArchetypeId(archetypeId) ? {archetypeId} : {}),
    };
    return {
        tournamentId: t.id, gameId: game.id, color, baseTimeMs: game.base_time_ms, incrementMs: game.increment_ms,
        botId: opponent.kind === 'bot' ? opponent.bot_key : null, custom,
    };
}

/**
 * How many rounds in total: Swiss - from the SWISS_ROUNDS table, round-robin - from the schedule, knockout - the number of
 * bracket rounds (log2 of the size, rounded up). Big historical tournaments have any size and number of rounds, so
 * where possible the number is taken from the schedule's games themselves.
 */
export function totalRounds(t: Tournament): number {
    if (t.format === 'swiss') return SWISS_ROUNDS[t.size] ?? Math.max(1, ...t.games.map((g) => g.round));
    // One round - one less than the number of participants (with an odd number - the same); a multi-round schedule
    // is created in full, and the last round is visible from the games.
    if (t.format === 'round_robin') return Math.max(t.size % 2 === 0 ? t.size - 1 : t.size, ...t.games.map((g) => g.round));
    return Math.max(1, Math.ceil(Math.log2(t.size)));
}

/** Whether there are bot games the server is computing right now (the page refreshes the state while they run). */
export function botGamesRunning(t: Tournament): boolean {
    if (t.status !== 'active') return false;
    return t.games.some((g) => g.result === null && g.round === t.current_round
        && g.white_seat !== t.my_seat && g.black_seat !== t.my_seat);
}
