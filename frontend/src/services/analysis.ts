// --- FILE: frontend/src/services/analysis.ts ---
// Game viewing and analysis: the game's PGN (own — /api/v1/profile/games/{id}/pgn, from the library — /library/games/{id}/pgn,
// imported — /imports/games/{id}/pgn) and engine analysis: GET — a ready analysis from the cache, POST — start it
// (/api/v1/analysis/game/{id}, src/api/analysis.py; for imported games — /imports/games/{id}/analysis). Analysis is engine
// help: during the player's own game against a human the server does not provide it (src/api/fair_play.py); the client just shows the refusal.
// Used by GameViewer.tsx (viewing) and chessboard/GameSummaryPanel.tsx (post-game summary). Requests — http.ts.

import type {FullGameAnalysisReport} from '../components/gameViewer/viewerModel';
import type {MessageKey} from '../i18n';
import {apiFetch, apiRequest, apiUrl} from './http';

/** Where the game comes from: played on the site (and the masters archive), the book library, or a player's import. */
export type GameSource = 'played' | 'library' | 'imported';

/** PGN path of a game by its source. */
function pgnPath(source: GameSource, id: number | string): string {
    if (source === 'library') return `/library/games/${id}/pgn`;
    if (source === 'imported') return `/imports/games/${id}/pgn`;
    return `/profile/games/${id}/pgn`;
}

/** Analysis path: imported games have their own, the rest use the shared engine analysis. */
const analysisPath = (source: GameSource, id: number | string) =>
    (source === 'imported' ? `/imports/games/${id}/analysis` : `/analysis/game/${id}`);

export const analysisApi = {
    /** PGN URL for the «download» link. */
    pgnUrl: (source: GameSource, id: number | string) => apiUrl(pgnPath(source, id)),
    /** The game's PGN text. */
    pgn: async (source: GameSource, id: number | string) => (await apiFetch(pgnPath(source, id), {}, 'viewer.loadFailed')).text(),
    /** Ready analysis from the cache; none or a failure — null (the analysis can be started with a button). */
    cached: (source: GameSource, id: number | string) =>
        apiRequest<FullGameAnalysisReport>(analysisPath(source, id)).catch(() => null),
    /**
     * Start the analysis; a refusal (engine busy, limit, own game in progress) — UiError with text by the server code.
     * T — which part of the report the caller reads (the game summary describes it with its own type); fallback — refusal text without a code.
     */
    run: <T = FullGameAnalysisReport>(source: GameSource, id: number | string, fallback: MessageKey = 'viewer.analysisFailed') =>
        apiRequest<T>(analysisPath(source, id), {method: 'POST'}, fallback),
};
