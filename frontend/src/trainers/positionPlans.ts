// --- FILE: frontend/src/trainers/positionPlans.ts ---
// "Plan in this position" (task 27.9): pure rules of the trainer over the prepared set content/positionPlans.json.
// A question is a position from a master game and three plans, each named by a category and its concrete first move here;
// the first option in the file is the plan the master played. The set is built and checked by the engine in advance
// (scripts/dev/build_position_plans.py: the master's move is within 30 cp of the best one, each wrong plan's best first
// move is weaker by at least 100 cp), so no engine runs here. The texts of the categories are i18n keys positionPlans.<code>.
// Used by components/trainers/PositionPlanQuiz.tsx.

import data from '../content/positionPlans.json';
import {rng} from './vision';

/** Plan categories of the generator (PLANS in build_position_plans.py); the i18n catalogue has a name for each. */
export const PLAN_CODES = ['passed_pawn', 'central_break', 'pawn_storm', 'queenside_pawns', 'knight_manoeuvre', 'rook_file',
    'king_march'] as const;
export type PlanCode = typeof PLAN_CODES[number];

/** One option: the plan category, its first move (UCI) and the engine evaluation after it, cp for the side to move. */
export interface PlanOption {
    plan: PlanCode;
    move: string;
    score: number;
}

/** A prepared question: the position, the game, the game's next plies and the options (the master's plan first). */
export interface PlanQuestion {
    id: string;
    fen: string;
    white: string;
    black: string;
    year: number | null;
    continuation: string[];
    options: PlanOption[];
}

/** The whole set, as generated. */
export const POSITION_PLANS = data as PlanQuestion[];

/** Questions in one attempt. */
export const PLAN_ROUNDS = 10;

/** A question as shown: the options in a seeded order and the index of the master's plan among them. */
export interface ShownQuestion {
    question: PlanQuestion;
    options: PlanOption[];
    answer: number;
}

/** Fisher-Yates shuffle with a seeded generator: the same seed gives the same attempt (tests, a repeated attempt). */
function shuffled<T>(items: readonly T[], next: () => number): T[] {
    const copy = [...items];
    for (let i = copy.length - 1; i > 0; i--) {
        const j = Math.floor(next() * (i + 1));
        [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    return copy;
}

/**
 * An attempt of count questions: different positions, the plan categories of the answers mixed (no category twice in a row
 * when the set allows it), the options shuffled. The master's plan is options[answer].
 */
export function planAttempt(seed: number, count = PLAN_ROUNDS, set: PlanQuestion[] = POSITION_PLANS): ShownQuestion[] {
    const next = rng(seed);
    const pool = shuffled(set, next);
    const picked: PlanQuestion[] = [];
    while (picked.length < Math.min(count, set.length)) {
        const last = picked.at(-1)?.options[0].plan;
        const index = pool.findIndex((q) => q.options[0].plan !== last);
        picked.push(...pool.splice(index < 0 ? 0 : index, 1));
    }
    return picked.map((question) => {
        const options = shuffled(question.options, next);
        return {question, options, answer: options.indexOf(question.options[0])};
    });
}
