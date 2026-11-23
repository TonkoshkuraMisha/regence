// --- FILE: frontend/src/services/tablebase.ts ---
// Endgame tablebases (task 14.4): POST /analysis/tablebase — the position result for the side to move and its
// best move (the perfect defender answers it). Subject to the fair-play rule.
// Route — src/api/analysis.py, calculation — src/services/tablebase.py: the server queries a tablebase service
// at TABLEBASE_URL (only the position leaves), and the answer is cached in Redis. A position with more pieces than the
// tablebases cover is rejected by the server with code tablebase_too_many_pieces. An unavailable tablebase service is replaced by a Stockfish
// evaluation (source: 'engine', dtm and dtz — null, maybe-* categories — a disputed evaluation); with no engine either —
// tablebase_unavailable. The trainer's verdict on the answer — trainerVerdict.

import {apiRequest} from './http';

/** Best move per tablebase; category, dtm and dtz are passed as is from the tablebase service response for this move. */
export interface TablebaseMove {
    uci: string;
    san: string;
    category: string | null;
    dtm: number | null;
    dtz: number | null;
}

/** Tablebase answer for a position. */
export interface TablebaseProbe {
    /** win | loss | draw | cursed-win | blessed-loss | maybe-win | maybe-loss | unknown — for the side to move. */
    category: string | null;
    /** Distance to mate (dtm) and to the 50-move counter reset (dtz) — in plies; null — the tablebases do not know. */
    dtm: number | null;
    dtz: number | null;
    /** Best move of the side to move (first in the tablebase service response); null — no moves in the response. */
    best: TablebaseMove | null;
    /** tablebase — an exact tablebase answer; engine — tablebases unavailable, the engine evaluation answered. */
    source: 'tablebase' | 'engine';
}

/**
 * Outcome of the player's move in the endgame trainer by the answer for the opponent (who moves): continue — play on,
 * winLost — the win is lost, drawLost — the draw is lost. Strict for exact tablebases: for a win the opponent must
 * be losing. For an engine evaluation the game is cut off only by a clear verdict (draw / win); a disputed maybe-* evaluation is
 * not grounds to count a mistake.
 */
export function trainerVerdict(probe: TablebaseProbe, winning: boolean): 'continue' | 'winLost' | 'drawLost' {
    const category = probe.category;
    if (probe.source === 'engine') {
        if (winning) return category === 'draw' || category === 'win' ? 'winLost' : 'continue';
        return category === 'win' ? 'drawLost' : 'continue';
    }
    if (winning) return category !== 'loss' ? 'winLost' : 'continue';
    return category === 'win' || category === 'maybe-win' ? 'drawLost' : 'continue';
}

/** Tablebase query by position (FEN). A server refusal, including the ban during a game, is a UiError with text by code. */
export function probeTablebase(fen: string): Promise<TablebaseProbe> {
    return apiRequest<TablebaseProbe>('/analysis/tablebase', {method: 'POST', body: JSON.stringify({fen})});
}
