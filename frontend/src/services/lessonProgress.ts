// --- FILE: frontend/src/services/lessonProgress.ts ---
// Server-side progress of school lessons (task 14.1): GET /api/v1/learn/progress and PUT /api/v1/learn/progress/{lesson id}
// (src/api/learn.py, table lesson_progress). Without login progress is not stored. The lessons themselves are client data
// (content/lessons/*.json), so the server accepts any lesson id and stores only numbers for it.
// The same storage under their own ids is used by "Basics", "Classics", the endgame trainer, the mates course, the Big Course
// and training programs: each section has its own function building the record id (progressId, courseProgressId).

import {API_BASE_URL} from '../config/api';

/** Progress of one lesson as stored by the server. Progress only grows: repeating a lesson does not reset it. */
export interface LessonProgress {
    lesson_id: string;
    /** Furthest completed step (0-based) and the number of lesson steps. */
    step: number;
    steps_total: number;
    completed: boolean;
    /** Best result of the control questions; null — the lesson has none or they are not passed yet. */
    exam_score: number | null;
    exam_total: number | null;
}

/** PUT body: what the client reports after a step or lesson completion. */
export interface ProgressUpdate {
    step: number;
    steps_total: number;
    completed?: boolean;
    exam_score?: number;
    exam_total?: number;
}

const BASE = `${API_BASE_URL}/api/v1/learn/progress`;

/** All progress records of the player. An error is a plain exception without player text: what to do with it is decided by the section. */
export async function fetchLessonProgress(token: string): Promise<LessonProgress[]> {
    const res = await fetch(BASE, {headers: {Authorization: `Bearer ${token}`}});
    if (!res.ok) throw new Error(`progress ${res.status}`);
    return res.json();
}

/** Save lesson progress; the response is the server record after merging with the previous one (step and result do not decrease). */
export async function saveLessonProgress(token: string, lessonId: string, update: ProgressUpdate): Promise<LessonProgress> {
    const res = await fetch(`${BASE}/${encodeURIComponent(lessonId)}`, {
        method: 'PUT',
        headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'},
        body: JSON.stringify(update),
    });
    if (!res.ok) throw new Error(`progress ${res.status}`);
    return res.json();
}
