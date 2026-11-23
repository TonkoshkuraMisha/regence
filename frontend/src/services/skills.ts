// --- FILE: frontend/src/services/skills.ts ---
// Player skill map: a summary of puzzle sections, mistakes, openings, courses and the diagnostic exam.
// Endpoint GET /api/v1/skills (src/api/skills.py) — sign-in only. Used by SkillMap.tsx (profile).
// The request and errors go through apiRequest (http.ts).

import {apiRequest} from './http';
import {getToken} from './authToken';

/** Response of GET /skills: a summary of puzzle sections, mistakes, openings, courses and the diagnostic exam. */
export interface SkillMapData {
    username: string;
    puzzle_rating: number;
    sections: { section: string; attempts: number; score: number | null }[];
    weakest_themes: { theme: string; section: string; attempts: number; score: number }[];
    mistakes: { total: number; fixed: number; themes: { theme: string; count: number }[] };
    trainers: { trainer: string; attempts: number; best: number; max_level: number }[];
    openings: { repertoires: number; new: number; learning: number; learned: number };
    endgames: { done: number; total: number };
    mates: { done: number; total: number };
    /** Diagnostic exam (22.0). */
    exam?: { overall: number | null; level: string | null; passed: number; of: number };
}

/** Skill map of the current player; without a token or on any failure (server, network) — null: the block is simply not rendered. */
export async function fetchSkillMap(): Promise<SkillMapData | null> {
    if (!getToken()) return null;
    return apiRequest<SkillMapData>('/skills').catch(() => null);
}
