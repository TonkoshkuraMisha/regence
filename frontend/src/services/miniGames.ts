// --- FILE: frontend/src/services/miniGames.ts ---
// Trainer mini-games (pawn battles etc.): the player's move and the bot's first move as White.
// Endpoints POST /api/v1/mini-games/{game}/move and /bot-first (src/api/mini_games.py, rules — src/services/mini_games.py);
// work without login. Used by MiniGames.tsx. Request and errors — apiRequest (http.ts). "Over the network" rooms — miniGameRooms.ts.

import {apiRequest} from './http';

/** Server answer to a move: new position, result (1-0, 0-1, 1/2-1/2 or null) and the bot's reply move (uci), if there was one. */
export interface MoveReply {
    fen: string;
    result: string | null;
    bot_move: string | null;
}

/** POST to /api/v1/mini-games{path}; a server refusal — UiError with the error code. */
export const postMiniGame = (path: string, body: object) =>
    apiRequest<MoveReply>(`/mini-games${path}`, {method: 'POST', body: JSON.stringify(body)});
