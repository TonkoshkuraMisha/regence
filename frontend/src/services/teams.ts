// --- FILE: frontend/src/services/teams.ts ---
// Teams and the seasonal league (task 17.2).
// All requests go to /api/v1/teams (routes in src/api/teams.py, scoring rules — src/services/league.py). A season is
// a calendar month (UTC). Points are stored nowhere: the server computes them on request from the season's finished rated
// games between players of different teams. A player belongs to at most one team.

import {apiRequest} from './http';

/** League table row: team, member count, season points and rank. */
export interface LeagueRow {
    id: number;
    name: string;
    members: number;
    points: number;
    place: number;
}

/** League table for a season ("YYYY-MM"). */
export interface LeagueTable {
    season: string;
    teams: LeagueRow[];
}

/** Team: season points and each member's contribution; owner — the team's creator. */
export interface TeamView {
    id: number;
    name: string;
    season: string;
    points: number;
    members: { username: string; points: number; owner: boolean }[];
}

/** Request to /api/v1/teams through the shared http.ts wrapper (token, JSON, errors). */
const call = <T>(path: string, init: RequestInit = {}) => apiRequest<T>(`/teams${path}`, init);

/** Team endpoints. The league table is open without sign-in; own team, creation, joining and leaving — with sign-in. */
export const teamsApi = {
    /** Current season table (the server also knows past ones via the season parameter, the client does not pass it). */
    league: () => call<LeagueTable>('/league'),
    /** The player's team; team = null — they belong to none. */
    mine: () => call<{ team: TeamView | null }>('/mine'),
    create: (name: string) => call<TeamView>('', {method: 'POST', body: JSON.stringify({name})}),
    join: (id: number) => call<TeamView>(`/${id}/join`, {method: 'POST'}),
    leave: () => call<{ team: null }>('/leave', {method: 'POST'}),
};
