// --- FILE: frontend/src/services/onboarding.ts ---
// First login (task 17.8): answers at registration and the choice of an opponent for the first game. No requests here: the answers
// go to the server together with registration (login form), the starting rating is computed by the server from them
// (src/services/onboarding.py), and the opponent is chosen from the bot catalog (services/botCatalog.ts).

import type {CatalogArchetype} from './botCatalog';

/** Questionnaire answers at registration: playing experience and self-assessed strength. Codes are the same as the server accepts. */
export type Experience = 'new' | 'casual' | 'regular';
export type StrengthBand = 'under_1000' | '1000_1400' | '1400_1800' | 'over_1800';

export const EXPERIENCES: Experience[] = ['new', 'casual', 'regular'];
export const STRENGTH_BANDS: StrengthBand[] = ['under_1000', '1000_1400', '1400_1800', 'over_1800'];

/** Games per category while the rating is provisional (the server's PROVISIONAL_GAMES, src/services/rating.py). */
export const PROVISIONAL_GAMES = 30;

/** Transition state to the main board: start the first game by the starting rating. */
export interface FirstGameStart {
    rating: number;
}

/**
 * First game opponent: the strongest archetype not stronger than the player (by measured strength — the first game must be
 * manageable), and if all are stronger — the weakest one.
 */
export function pickFirstOpponent(archetypes: CatalogArchetype[], rating: number): CatalogArchetype | null {
    if (archetypes.length === 0) return null;
    const sorted = [...archetypes].sort((a, b) => a.rating - b.rating);
    const fitting = sorted.filter((a) => a.rating <= rating);
    return fitting.length > 0 ? fitting[fitting.length - 1] : sorted[0];
}
