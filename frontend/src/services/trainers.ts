// --- FILE: frontend/src/services/trainers.ts ---
// Trainers (task 19.1): attempt results, personal records and history for the chart (/api/v1/trainers). Trainers work
// without sign-in, but results are not saved.
// Routes - src/api/trainers.py, table trainer_results. The trainers themselves are computed on the client
// (frontend/src/trainers/), so the server only validates value bounds: records are personal and do not affect rating.

import {apiRequest} from './http';

/** Trainer codes - the same as the server accepts: results and records are stored under the code. */
export const TRAINER_IDS = ['quiet_path', 'knight_route', 'double_strike', 'tail',
    'coord_find', 'coord_name', 'coord_color', 'coord_diagonal', 'memory_position', 'memory_game',
    'board_placement', 'knight_tour', 'blind_move', 'blind_where',
    'calc_checks', 'calc_exchange', 'calc_distance', 'calc_square', 'calc_eval', 'calc_compare', 'structure_quiz', 'plan_quiz', 'miniatures'] as const;
export type TrainerId = typeof TRAINER_IDS[number];

/** Result of one attempt, computed on the client: level, score, time and number of mistakes. */
export interface TrainerAttempt {
    trainer: TrainerId;
    level: number;
    score: number;
    time_ms: number;
    mistakes: number;
}

/** Trainer personal record: best result, highest level passed and number of attempts. */
export interface TrainerRecord {
    best: number;
    max_level: number;
    attempts: number;
}

/** Request to /api/v1/trainers via the shared http.ts wrapper (token, JSON, errors). */
const call = <T>(path: string, init: RequestInit = {}) => apiRequest<T>(`/trainers${path}`, init);

export const trainersApi = {
    /** Save an attempt; record - whether the level's personal record was broken, best - the record after it. */
    save: (attempt: TrainerAttempt) => call<{ record: boolean; best: number }>('/results', {
        method: 'POST', body: JSON.stringify(attempt),
    }),
    records: () => call<{ records: Partial<Record<TrainerId, TrainerRecord>> }>('/records'),
    /** Latest trainer results - for the chart, oldest first. */
    history: (trainer: TrainerId) =>
        call<{ results: { level: number; score: number; time_ms: number; mistakes: number; created_at: string }[] }>(`/history/${trainer}`),
};
