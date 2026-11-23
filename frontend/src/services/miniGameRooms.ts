// --- FILE: frontend/src/services/miniGameRooms.ts ---
// Trainer games against a human over the network (task 19.8): a room for two by link. Rules and state are on the server
// (src/services/mini_game_rooms.py, endpoints src/api/mini_game_rooms.py, /api/v1/mini-game-rooms); the client only
// shows the room and polls it (get) — this is how it learns about the opponent's move.
import {apiRequest} from './http';


export type RoomColor = 'white' | 'black';

/** Room (mini_game_rooms.view on the server). you — the requester's colour; null — a spectator or guest. */
export interface MiniRoom {
    code: string;
    game_id: string;
    fen: string;
    moves: string[];
    result: '1-0' | '0-1' | '1/2-1/2' | null;
    /** Why it ended: by the rules of the game or by resignation. */
    reason: 'rules' | 'resign' | null;
    /** Grows with every move; a move is sent with the version in which the player saw the position. */
    version: number;
    /** "Once more" room — both players move there. */
    next: string | null;
    white: string | null;
    black: string | null;
    you: RoomColor | null;
    /** The second seat is still free. */
    waiting: boolean;
}

const call = (path: string, init: RequestInit = {}) => apiRequest<MiniRoom>(`/mini-game-rooms${path}`, init);

export const miniRoomsApi = {
    create: (gameId: string, color: RoomColor | 'random' = 'random') =>
        call('', {method: 'POST', body: JSON.stringify({game_id: gameId, color})}),
    get: (code: string) => call(`/${code}`),
    join: (code: string) => call(`/${code}/join`, {method: 'POST'}),
    move: (code: string, move: string, version: number) =>
        call(`/${code}/move`, {method: 'POST', body: JSON.stringify({move, version})}),
    resign: (code: string) => call(`/${code}/resign`, {method: 'POST'}),
    rematch: (code: string) => call(`/${code}/rematch`, {method: 'POST'}),
};

/** Link to the room for the opponent. */
export function roomLink(code: string, origin = window.location.origin): string {
    return `${origin}/train/games/room/${code}`;
}
