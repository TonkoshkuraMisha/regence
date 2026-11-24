// --- FILE: frontend/src/services/chess960.ts ---
// Fischer random chess against a bot: GET /api/v1/chess960/new[number] — the setup, POST /move — the player's move and the bot's reply,
// POST /bot-move — the bot's first move as White (src/api/chess960.py, rules — src/services/chess960.py). The server does not store
// the game: the position and moves are sent in full each time. The bot's move is engine help: during the player's own game against a human
// the server does not give it (src/api/fair_play.py). Used by chess960/Chess960Page.tsx. Request and errors — http.ts.

import {apiRequest} from './http';

/** State of a 960 game from the server response. */
export interface State960 {
    number: number;
    fen: string;
    moves: string[];
    sans: string[];
    result: string | null;
    termination: string | null;
    bot_move: string | null;
    check: boolean;
}

/** Request to /chess960{path}: without a body — GET (new position), with a body — POST (move or bot move). */
export const chess960Call = (path: string, body?: object) =>
    apiRequest<State960>(`/chess960${path}`, body ? {method: 'POST', body: JSON.stringify(body)} : {});

/** A finished Fischer game for the archive viewer: `fens[i]` is the position after ply i (`fens[0]` is the start). */
export interface Archive960 {
    game_id: number;
    start_fen: string;
    fens: string[];
    moves: string[];
    sans: string[];
    result: string | null;
}

/** Engine evaluation of each archive position, centipawns from White's point of view (GET /chess960/archive/{id}/analysis). */
export interface Analysis960 {
    game_id: number;
    scores: number[];
    complete: boolean;
}

/** The replay record of a finished Fischer game (GET /chess960/archive/{id}); another variant is a not_chess960_game error. */
export const chess960Archive = (gameId: number | string) => apiRequest<Archive960>(`/chess960/archive/${gameId}`);

/** Engine evaluation of a finished Fischer game (engine work: rate limit, fair play, may answer engine_busy). */
export const chess960Analysis = (gameId: number | string) => apiRequest<Analysis960>(`/chess960/archive/${gameId}/analysis`);
