// --- FILE: frontend/src/services/workout.ts ---
// Daily workout (task 22.2): today's plan - puzzles on weak themes, a trainer, repetitions.
// Endpoint GET /api/v1/workout (src/api/workout.py); the server counts steps from the actual training done today.
// Used by WorkoutPage.tsx. Request and errors - apiRequest (http.ts).

import {apiRequest} from './http';

/** Workout plan step; the kind (kind) determines which fields arrive and where the button leads. */
export type WorkoutStep =
    | { kind: 'puzzles'; themes: string[]; target: number; done: number }
    | { kind: 'trainer'; trainer: string; done: boolean }
    | { kind: 'repertoire'; due: number; repertoire_id: number | null; done: boolean }
    | { kind: 'mistake'; due: number; done: boolean };

/** Today's plan: date, whether fully done, streak of consecutive days and steps. */
export interface WorkoutPlan {
    date: string;
    complete: boolean;
    streak: number;
    steps: WorkoutStep[];
}

/** Loads today's plan; a server refusal - UiError with text by error code. */
export const fetchWorkoutPlan = () => apiRequest<WorkoutPlan>('/workout');

/** Summary of the last 7 days (GET /workout/week, src/services/weekly_summary.py) and advice as a code (weekly.advice.<code>). */
export interface WeekSummary {
    since: string;
    games: { total: number; wins: number; draws: number; losses: number; rating_delta: number };
    puzzles: { attempts: number; solved: number };
    days_active: number;
    streak: number;
    advice: 'comeback' | 'try_puzzles' | 'play_games' | 'review_losses' | 'keep_going';
}

export const fetchWeekSummary = () => apiRequest<WeekSummary>('/workout/week');
