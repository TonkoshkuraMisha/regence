// --- FILE: frontend/src/services/gameSummary.ts ---
// Game summary (task 11.5): the game type is computed by the server (src/services/game_summary.py); here — choosing the next
// opponent by result and bot strength. No request here: the summary arrives as the summary field together with the game analysis
// (/api/v1/analysis/game/{id}, for imported games — /api/v1/imports/games/{id}/analysis).

/**
 * Game type by the evaluation graph: "seesaw", "decided by a mistake", "domination", "missed win", "even fight",
 * "gradual advantage". Thresholds and check order — in the docstring of src/services/game_summary.py.
 */
export type GameSummaryKind = 'seesaw' | 'decisive_blunder' | 'domination' | 'missed_win' | 'balanced' | 'gradual';
export const GAME_SUMMARY_KINDS: readonly GameSummaryKind[] = [
    'seesaw', 'decisive_blunder', 'domination', 'missed_win', 'balanced', 'gradual',
];

/** Game summary as served by the server (computed from a finished analysis, without the engine). Plies are 1-based. */
export interface GameSummary {
    kind: GameSummaryKind;
    /** Ply of the turning point; null — there was no turning point. */
    turning_point_ply: number | null;
    /** How many times the decisive advantage passed from one side to the other. */
    lead_changes: number;
    /** Share of moves (0...1) when the position was equal. */
    equal_share: number;
    /** Key moments of the side: best move and worst (biggest loss). */
    white: { best_ply: number | null; worst_ply: number | null };
    black: { best_ply: number | null; worst_ply: number | null };
    /** Missed punishments: the reply did not punish the opponent's big mistake (task B.5). No field — old analysis. */
    missed?: { ply: number; color: 'white' | 'black'; cp: number }[];
}

/** Whether the client knows the game type: an unknown one (server is newer) cannot be shown — labels come from the catalog. */
export function isSummaryKind(value: unknown): value is GameSummaryKind {
    return typeof value === 'string' && (GAME_SUMMARY_KINDS as readonly string[]).includes(value);
}

/** Opponent from the pool: a historical bot or a workshop archetype. */
export interface PoolOpponent {
    kind: 'historical' | 'archetype';
    id: string;
    rating: number;
}

export type GameOutcome = 'win' | 'loss' | 'draw';

/** Strength step below which an opponent is considered "of the same level". */
const SAME_LEVEL = 40;

/** Outcome for the player from the result record ("1-0", "0-1"); anything else counts as a draw. */
export function outcomeFor(result: string, playerColor: 'white' | 'black'): GameOutcome {
    if (result === '1-0') return playerColor === 'white' ? 'win' : 'loss';
    if (result === '0-1') return playerColor === 'black' ? 'win' : 'loss';
    return 'draw';
}

/**
 * Next opponent: after a win — the nearest noticeably stronger one, after a loss — the nearest noticeably weaker one,
 * after a draw — another opponent, nearest by strength (on equal distance — the stronger one). If there is nobody in the needed
 * direction — the nearest by strength. "Noticeably" — at least SAME_LEVEL rating points.
 */
export function recommendOpponent(
    pool: readonly PoolOpponent[], current: { id: string; rating: number }, outcome: GameOutcome,
): PoolOpponent | null {
    const others = pool.filter((o) => o.id !== current.id);
    if (others.length === 0) return null;
    // Nearest by strength; on equal distance — the stronger one: this way the player improves.
    const byDistance = [...others].sort(
        (a, b) => Math.abs(a.rating - current.rating) - Math.abs(b.rating - current.rating) || b.rating - a.rating,
    );
    if (outcome === 'win') {
        const stronger = others.filter((o) => o.rating >= current.rating + SAME_LEVEL).sort((a, b) => a.rating - b.rating);
        return stronger[0] ?? byDistance[0];
    }
    if (outcome === 'loss') {
        const weaker = others.filter((o) => o.rating <= current.rating - SAME_LEVEL).sort((a, b) => b.rating - a.rating);
        return weaker[0] ?? byDistance[0];
    }
    return byDistance[0];
}
