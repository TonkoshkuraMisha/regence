// --- FILE: frontend/src/services/ladder.ts ---
// Club ladder (games against bots by rungs): GET /api/v1/bots/ladder — ladder rating and rungs,
// POST /bots/ladder/start — the current rung's opponent and colour (src/api/ladder.py, rules — src/services/ladder.py).
// Login only. Used by chessboard/LadderPanel.tsx (ladder tab) and Chessboard.tsx (game start).
// Request and errors — apiRequest (http.ts).

import type {LadderOutcome} from '../components/chessboard/hooks/useBotGame';
import {apiRequest} from './http';
import type {PersonalityConfig} from './personalities';

/** Ladder rung from the GET /bots/ladder response. */
export interface Rung {
    key: string;
    kind: 'historical' | 'archetype';
    /** id of a bot or archetype — the name in the player's language comes from the catalog. */
    id: string;
    rating: number;
    measured: boolean;
    /** skipped — weaker than the current one but not passed: the opponent is added to the ladder below the already passed one (server, ladder.py). */
    status: 'beaten' | 'current' | 'skipped' | 'locked';
}

/** GET /bots/ladder response: ladder rating, current rung number (0-based), all rungs. */
export interface LadderState {
    rating: number;
    games: number;
    step: number;
    total: number;
    rungs: Rung[];
    active_opponent: string | null;
}

/** Rung opponent: a historical bot (bot_id) or a workshop archetype (config — its sliders). */
export interface LadderOpponent {
    key: string;
    kind: 'historical' | 'archetype';
    id: string;
    rating: number;
    bot_id: string | null;
    config: PersonalityConfig | null;
}

/** POST /bots/ladder/start response: whom to play and with which colour. */
export interface LadderStart {
    opponent: LadderOpponent;
    color: 'white' | 'black';
    step: number;
    /** Result of the previous ladder game that was started and abandoned: the server counted it as a loss. */
    forfeited: LadderOutcome | null;
}

export const ladderApi = {
    state: () => apiRequest<LadderState>('/bots/ladder', {}, 'ladder.loadFailed'),
    /** Start a game of the current rung; random — the server picks the colour. */
    start: (color: 'white' | 'black' | 'random') =>
        apiRequest<LadderStart>('/bots/ladder/start', {method: 'POST', body: JSON.stringify({color})}, 'ladder.startFailed'),
};
