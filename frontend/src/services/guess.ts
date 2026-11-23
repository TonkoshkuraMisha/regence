// --- FILE: frontend/src/services/guess.ts ---
// "Guess the master's move" (task 14.3): positions from master games, selected by the engine (src/api/guess.py).
// All requests go to /api/v1/guess, available to guests too. Points for an answer are computed by the server (src/services/guess.py) from
// the engine lines saved at selection time — the engine itself is not run on answering.

import type {CoachComment} from './coach';
import {apiRequest} from './http';

/** Position to guess. The master's move is not included — it arrives only in the answer (GuessAnswer). */
/** Move option in the "multiple choice" mode. */
export interface GuessCandidate {
    uci: string;
    san: string;
}

export interface GuessPosition {
    id: number;
    /** Options to choose from (the master's move among them) — only if requested (beginner mode). */
    candidates?: GuessCandidate[];
    /** Archive game and 0-based ply number of the master's move (that many plies were played before the position). */
    game_id: number;
    ply: number;
    fen: string;
    /** Side to move — the player guesses for this side. */
    side: 'white' | 'black';
    move_number: number;
    /** Difficulty — position rating: changes with answers of logged-in players, like a puzzle rating. */
    difficulty: number;
    /** Series — several moments of one game in a row; null — a single position. */
    series_id: number | null;
    series_index: number;
    series_length: number;
    white: string;
    black: string;
    event: string | null;
    /** Only the game year ("1927") from the Date header. */
    date: string | null;
    /** Last moves of the game before the position (SAN) and the ply number of the first of them — for the move ribbon. */
    previous: string[];
    first_previous_ply: number;
    last_move: string | null;
}

/** Server answer to the player's move: points, master's move, engine lines and the mentor's explanation (CoachComment fields). */
export interface GuessAnswer extends CoachComment {
    /** Points 0–100: master's move — 100, almost as good as the best — 80, further — by loss in centipawns. */
    score: number;
    loss_cp: number;
    master_move: string;
    master_san: string;
    /** Up to three best engine moves with evaluation in centipawns. */
    lines: { uci: string; san: string; cp: number }[];
    /** Theme codes of registry 13.0 (themes.<code>.name); empty — themes not determined. */
    themes?: string[];
    /** Next position of the same series; null — the series ended or the position is single. */
    next_id: number | null;
}

/** Post-game question: code and option codes (the text is assembled by the client). */
export interface QuizQuestion {
    id: string;
    options: string[];
}

export interface QuizResult {
    score: number;
    total: number;
    results: Record<string, boolean>;
    correct: Record<string, string>;
}

/** Wrong move before the last attempt: no result, can try again ("three attempts" mode). */
export interface GuessRetry {
    retry: true;
    attempts_left: number;
    loss_cp: number;
}

export function isRetry(result: GuessAnswer | GuessRetry): result is GuessRetry {
    return 'retry' in result && result.retry === true;
}

/** Attempts per position; the server accepts the same number (src/services/guess.py, MAX_ATTEMPTS). */
export const MAX_ATTEMPTS = 3;

const request = <T>(path: string, init: RequestInit = {}) => apiRequest<T>(`/guess${path}`, init);

export const guessApi = {
    /** Next position near the player's strength (for a guest — near 1500); null — positions not selected yet. */
    next: (series: boolean, candidates = false) =>
        request<{ position: GuessPosition | null }>(`/next?${new URLSearchParams({series: String(series), candidates: String(candidates)})}`),
    /** Position by id; candidates — with options to choose from. */
    position: (id: number, candidates = false) => request<GuessPosition>(`/position/${id}${candidates ? '?candidates=true' : ''}`),
    /** Answer: with the attempt number the server replies "once more" to a mistake until the last attempt; hints — hints taken (penalty). */
    answer: (id: number, move: string, attempt?: number, hints = 0) => request<GuessAnswer | GuessRetry>(`/position/${id}/answer`, {
        method: 'POST', body: JSON.stringify({move, attempt, hints}),
    }),
    /** Hint by steps: 1 — a nudge, 2 — the piece, 3 — an arrow of the master's move. */
    hint: (id: number, step: number) => request<CoachComment>(`/position/${id}/hint?step=${step}`),
    /** Post-game questions for the "whole" game (src/services/guess_quiz.py). */
    quiz: (gameId: number) => request<{ questions: QuizQuestion[] }>(`/game/${gameId}/quiz`),
    checkQuiz: (gameId: number, answers: Record<string, string>) => request<QuizResult>(`/game/${gameId}/quiz`, {
        method: 'POST', body: JSON.stringify({answers}),
    }),
    /** Games with selected moments: {game id: id of the first position}; the server looks at no more than 100 ids per request. */
    ofGames: (gameIds: number[]) => request<{ games: Record<string, number> }>(`/games?ids=${gameIds.join(',')}`),
    /** Selected moments of one game — for the "Guess the move" button in the viewer; empty list — no button. */
    ofGame: (gameId: number) => request<{ positions: { id: number; ply: number; series_id: number | null }[] }>(`/game/${gameId}`),
};

/** "Understanding accuracy" of a session: average score per answer (0–100); null — no answers yet. */
export function understanding(scores: number[]): number | null {
    return scores.length ? Math.round(scores.reduce((sum, s) => sum + s, 0) / scores.length) : null;
}
