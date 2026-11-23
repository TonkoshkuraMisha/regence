// --- FILE: frontend/src/components/chessboard/types.ts ---
// Types of the lobby, Live games and chat (extracted from Chessboard.tsx). Where the data comes from: the lobby and in-progress
// game lists are HTTP polling every 1.5 s (GET /profile/matchmaking/queue and /profile/games/live, the useGameSocket hook),
// chat messages are the WebSocket chat_message event.

/** A game in progress between humans in the "Live" list (a row of the GET /profile/games/live response). */
export interface LiveGameItem {
    game_id: number;
    white_username: string;
    white_rating: number;
    black_username: string;
    black_rating: number;
    base_time_ms: number;
    increment_ms: number;
    spectators_count: number;
    /** false means a friendly game (unrated). */
    is_rated?: boolean;
}

/** Game chat message as it is stored on the client (assembled from a chat_message event). */
export interface ChatMessageItem {
    sender: string;
    /** Text typed by the player; empty for a quick phrase: its text is taken from the catalog by code. */
    text: string;
    preset?: ChatPresetId;
    timestamp: number;
}

/** Quick phrase codes: the same list as CHAT_PRESETS on the server (src/api/websockets.py). */
export const QUICK_CHAT_PRESETS = ['good_luck', 'thanks', 'nice_move', 'time_trouble'] as const;

export type ChatPresetId = typeof QUICK_CHAT_PRESETS[number];

/** Validation of a quick phrase code from a server event: an unknown code is not shown as a phrase. */
export function isChatPreset(value: unknown): value is ChatPresetId {
    return typeof value === 'string' && (QUICK_CHAT_PRESETS as readonly string[]).includes(value);
}

/** A pawn move to the last rank that awaits a piece choice; isPremove means the promotion was set by a premove. */
export interface PendingPromotion {
    from: string;
    to: string;
    color: 'w' | 'b';
    isPremove?: boolean;
}

/** Open challenge in the lobby (a row of the GET /profile/matchmaking/queue response). */
export interface QueuePlayer {
    user_id: number;
    username: string;
    rating: number;
    base_time_ms: number;
    increment_ms: number;
    /** false means a challenge to a friendly game. */
    rated?: boolean;
}

/**
 * Server error codes unrelated to matchmaking: they must not reset the opponent search
 * (unlike "already in a game", "challenge is stale", etc.). The codes are from the src/core/errors.py registry and arrive
 * in the WebSocket error event; handleServerError in useGameSocket parses them.
 */
export const GAME_ACTION_ERROR_CODES: ReadonlySet<string> = new Set([
    'rate_limited',
    'message_too_large',
    'draw_offer_too_soon',
    'chat_forbidden',
    'spectate_unavailable',
    'game_not_in_progress',
    'abort_too_late',
    'berserk_unavailable',
    'berserk_too_late',
    'no_draw_offer',
    'no_rematch_offer',
]);
