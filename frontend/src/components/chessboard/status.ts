// --- FILE: frontend/src/components/chessboard/status.ts ---
// Game status line ("The opponent offers a draw", "The game is over..."). Stored not as ready text
// but as a catalog message with parameters (the shared UiMessage type from i18n); a parameter may itself be a message
// (a termination reason, a bot name, a server error). The text is assembled at display time, so a language change translates
// an already shown status too, and the logic ("is there a draw offer") does not depend on wording.

import {renderUiMessage, uiMessage} from '../../i18n';
import type {I18n, MessageKey, MessageParam, UiMessage} from '../../i18n';

export type GameStatus = UiMessage;
export type StatusParam = MessageParam;

/** Builds a status: a catalog key (status.*, ladder.*, tournaments.*, bots.*) and parameters. */
export function status(key: MessageKey, params?: Record<string, StatusParam>): GameStatus {
    return uiMessage(key, params);
}

/** Message parameter: translated at display time, in the current language. */
export function messageParam(key: MessageKey, params?: Record<string, StatusParam>): StatusParam {
    return uiMessage(key, params);
}

/** Whether a status with this key is currently shown: this is how logic learns, for example, that a draw offer is pending. */
export function hasStatusKey(value: GameStatus | null, key: MessageKey): boolean {
    return value !== null && 'key' in value && value.key === key;
}

/** Status text in the current language (called at render time). */
export function renderStatus(value: GameStatus, t: I18n['t']): string {
    return renderUiMessage(value, t);
}

// Game termination reasons that have a status.reasons.* label in the catalog. The reason code comes from the server:
// the reason field of the game_over event or the termination field of the GET /profile/games/{id}/summary response.
const GAME_OVER_REASONS = new Set([
    'checkmate', 'stalemate', 'timeout', 'resignation', 'agreement', 'draw_agreement', 'repetition',
    '50_move_rule', 'insufficient_material', 'timeout_vs_insufficient_material', 'abandoned',
    'abandoned_vs_insufficient_material',
] as const);

type GameOverReason = typeof GAME_OVER_REASONS extends Set<infer R> ? R : never;

function isKnownReason(reason: string): reason is GameOverReason {
    return (GAME_OVER_REASONS as Set<string>).has(reason);
}

/**
 * Game result: "The game is over. Result: 1-0 (checkmate)"; a game cancelled on move 1 has its own message. An unknown
 * reason (a new server code) gives a result without a reason; an empty result gives null (nothing to show).
 */
export function describeGameOver(result: string | null | undefined, reason?: string | null): GameStatus | null {
    if (reason === 'aborted' || result === '*') return status('status.aborted');
    if (!result) return null;
    if (reason && isKnownReason(reason)) {
        return status('status.gameOverReason', {result, reason: messageParam(`status.reasons.${reason}`)});
    }
    return status('status.gameOver', {result});
}
