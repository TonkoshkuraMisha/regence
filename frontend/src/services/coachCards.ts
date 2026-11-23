// --- FILE: frontend/src/services/coachCards.ts ---
// The «club coach» after a game (owner's plan 18.11, task 5): GET /learn/after-game/{id} — the server assembles
// the game's most expensive personal puzzle, the deviation from the repertoire and the mistake themes (src/services/coach_cards.py). The module
// of the Grand Course for the lesson is chosen by the client — the course is its data (content/supercourse.ts): the first module by level
// whose steps include training on the mistake theme.

import {COURSE} from '../content/supercourse';
import type {CourseModule} from '../content/supercourse';
import type {PersonalView} from './puzzles';
import type {Deviation} from './repertoire';
import {apiRequest} from './http';

export interface AfterGameCards {
    game_id: number;
    /** Game analysis is ready; personal puzzles appear slightly later (the same background task). */
    analysed: boolean;
    puzzle: PersonalView | null;
    deviation: Deviation | null;
    /** Themes of the most expensive mistake by significance; empty — there is no mistake puzzle. */
    lesson_themes: string[];
}

/** How many times to re-ask for the cards while the game's puzzle is not ready yet, and the pause between asks. */
export const POLL_ATTEMPTS = 3;
export const POLL_DELAY_MS = 5000;

/** Cards for one's own finished game; a refusal — UiError with text by code. */
export function fetchAfterGame(gameId: number): Promise<AfterGameCards> {
    return apiRequest<AfterGameCards>(`/learn/after-game/${gameId}`);
}

/** Whether to wait for the game puzzle: the analysis is ready but the puzzle is not — the background task may not have made it yet. */
export function shouldPoll(cards: AfterGameCards | null, attempt: number): boolean {
    return cards !== null && cards.puzzle === null && attempt < POLL_ATTEMPTS;
}

/**
 * Course module for a lesson on a mistake: by themes in order of significance — the first populated module that has
 * training on this theme; among those — the earliest level. null — no suitable module.
 */
export function lessonModuleFor(themes: string[], course: CourseModule[] = COURSE): { module: CourseModule; theme: string } | null {
    for (const theme of themes) {
        const found = course
            .filter((m) => m.steps.some((s) => s.kind === 'theme' && s.id === theme))
            .sort((a, b) => a.level - b.level)[0];
        if (found) return {module: found, theme};
    }
    return null;
}
