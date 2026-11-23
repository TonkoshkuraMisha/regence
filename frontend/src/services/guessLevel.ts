// Comparison of the "Guess the master's move" score for a whole game with the masters' level (task 14.3).
// In every selected moment the master played the best move, i.e. would score the maximum; we compare the player's share of points
// of that maximum and name the level by thresholds. Pure rules without network: nothing is stored, the client computes.

/** Result level; catalog key — `guess.level.<id>` (en/uk). */
export type GuessLevelId = 'master' | 'near' | 'confident' | 'learning';

/** Lower bounds of the points share (in percent) in descending order: the first that fits sets the level. */
export const GUESS_LEVEL_THRESHOLDS: ReadonlyArray<{ id: GuessLevelId; minPercent: number }> = [
    {id: 'master', minPercent: 90},
    {id: 'near', minPercent: 70},
    {id: 'confident', minPercent: 40},
    {id: 'learning', minPercent: 0},
];

export interface GuessLevel {
    /** Player's share of points of the maximum, whole percent (0 for an empty game). */
    percent: number;
    id: GuessLevelId;
}

/** Level by points scored and the maximum (100 per moment); an empty game counts as zero. */
export function guessLevel(points: number, max: number): GuessLevel {
    const percent = max > 0 ? Math.max(0, Math.min(100, Math.round((points / max) * 100))) : 0;
    const tier = GUESS_LEVEL_THRESHOLDS.find((item) => percent >= item.minPercent)!;
    return {percent, id: tier.id};
}
