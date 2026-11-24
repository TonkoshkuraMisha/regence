// --- FILE: frontend/src/services/weeklyLegends.ts ---
// The weekly tournament against legends (task 26.1; rules — src/services/weekly_legends.py): the week's line-up, the
// player's results and the standings (GET /api/v1/events/weekly-legends, open to guests) and the start of a fair game
// with a legend (POST /api/v1/events/weekly-legends/start). The game is played on the main board: the page passes
// WeeklyGameStart in location.state, and the result is counted by /bots/save-game with weekly=true (hooks/useBotGame.ts).

import {apiRequest} from './http';

/** A legend of the week and the player's result against it (null — not played yet). */
export interface WeeklyLegend {
    bot_id: string;
    rating: number | null;
    points: number | null;
    /** Why a game counted as a loss: a server code (weeklyLegends.forfeit.*). */
    forfeit: string | null;
}

export interface WeeklyStanding {
    place: number;
    username: string;
    avatar: string | null;
    points: number;
    wins: number;
    games: number;
}

export interface WeeklyEvent {
    week: string;
    ends_at: string;
    base_time_ms: number;
    increment_ms: number;
    legends: WeeklyLegend[];
    /** The legend of the player's open (unfinished) weekly game. */
    open_game: string | null;
    standings: { top: WeeklyStanding[]; me: WeeklyStanding | null; players: number };
    last_winner: WeeklyStanding | null;
}

/** What the page hands to the board to start a weekly game. */
export interface WeeklyGameStart {
    botId: string;
    color: 'white' | 'black';
    baseTimeMs: number;
    incrementMs: number;
    /** A started weekly game that this start counted as an abandoned loss. */
    abandoned: string | null;
}

/** How a saved weekly game was counted: the weekly field of the /bots/save-game response. */
export interface WeeklyOutcome {
    points: number;
    forfeit: string | null;
    total: number;
}

interface StartResponse {
    bot_id: string;
    color: 'white' | 'black';
    base_time_ms: number;
    increment_ms: number;
    abandoned: string | null;
}

const post = (body: unknown): RequestInit => ({method: 'POST', body: JSON.stringify(body)});

export const weeklyLegendsApi = {
    event: () => apiRequest<WeeklyEvent>('/events/weekly-legends', {}, 'weeklyLegends.loadFailed'),
    start: async (botId: string, color: 'white' | 'black' | 'random' = 'random'): Promise<WeeklyGameStart> => {
        const r = await apiRequest<StartResponse>('/events/weekly-legends/start', post({bot_id: botId, color}),
            'weeklyLegends.startFailed');
        return {botId: r.bot_id, color: r.color, baseTimeMs: r.base_time_ms, incrementMs: r.increment_ms, abandoned: r.abandoned};
    },
};
