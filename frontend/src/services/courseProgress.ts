// --- FILE: frontend/src/services/courseProgress.ts ---
// Auto-credit of Grand Course steps (owner's plan 18.11, task 6): GET /learn/course-progress returns what has been done by
// exercise kinds (the norms are computed by the server — src/services/course_progress.py), and here it is matched to the steps
// of a module. The progress record keys are the same functions the sections write them with (alphabet, mates course, endgame, mini-games).
// A master game step with an id is done when the game was played to the end (record classics-<id>, ClassicsPage).
// A step without an objective outcome (library, repertoire, the whole master games collection, «guess the move», warm-up, play) is not checked:
// a module made only of such steps is marked by the player, as before. The same rules credit the sessions of training
// programs (22.3, programAutoCount): a session is a set of the same exercises.

import {API_BASE_URL} from '../config/api';
import {LEVEL_EXAM_TARGET} from '../content/supercourse';
import type {CourseModule} from '../content/supercourse';
import type {Activity} from '../content/programs';
import {progressId as basicsProgressId} from '../content/basics/levels';
import {mateProgressId} from '../components/learn/MateCourse';
import {progressId as endgameProgressId} from '../components/learn/EndgameTrainer';
import {miniProgressId} from '../components/trainers/MiniGames';
import {progressId as classicsProgressId} from '../content/classics';
import {getToken} from './authToken';

export interface CourseFacts {
    /** ids of completed lesson_progress records (lessons, alphabet, mates, endgame, mini-games). */
    lessons: string[];
    /** Puzzle themes credited by the level's norm. */
    themes: string[];
    /** Trainers in which there is a finished attempt. */
    trainers: string[];
    /** The latest strength assessment per exam section. */
    exams: Record<string, number>;
}

/** What the player has completed; without login — null (no auto-credit). */
export async function fetchCourseFacts(): Promise<CourseFacts | null> {
    const token = getToken();
    if (!token) return null;
    const res = await fetch(`${API_BASE_URL}/api/v1/learn/course-progress`, {headers: {Authorization: `Bearer ${token}`}});
    if (!res.ok) throw new Error(`course progress ${res.status}`);
    // Missing fields (a response from a server of another version) are empty: auto-credit then simply marks nothing.
    const body = (await res.json()) as Partial<CourseFacts> | null;
    return {
        lessons: Array.isArray(body?.lessons) ? body.lessons : [],
        themes: Array.isArray(body?.themes) ? body.themes : [],
        trainers: Array.isArray(body?.trainers) ? body.trainers : [],
        exams: body?.exams && typeof body.exams === 'object' && !Array.isArray(body.exams) ? body.exams : {},
    };
}

const NO_FACTS: CourseFacts = {lessons: [], themes: [], trainers: [], exams: {}};

/** Whether the module has checkable steps: if not, the player marks the module themselves (the «completed» button). */
export function moduleCheckable(module: CourseModule): boolean {
    return module.steps.some((step) => activityDone(step, NO_FACTS) !== null);
}

const LEVEL_EXAM = /^level(\d)$/;

/** Whether the step is completed: true / false; null — the step has no objective outcome, it is not checked. */
export function activityDone(activity: Activity, facts: CourseFacts): boolean | null {
    const lessons = new Set(facts.lessons);
    switch (activity.kind) {
        case 'lesson': return lessons.has(activity.id);
        case 'basics': return lessons.has(basicsProgressId(activity.id));
        case 'mates': return lessons.has(mateProgressId(activity.id));
        case 'endgame': return lessons.has(endgameProgressId(activity.id));
        case 'mini': return lessons.has(miniProgressId(activity.id));
        case 'theme': return facts.themes.includes(activity.id);
        case 'trainer': return facts.trainers.includes(activity.id);
        case 'classics': return activity.id ? lessons.has(classicsProgressId(activity.id)) : null;
        case 'exam': {
            const estimate = facts.exams[activity.id];
            if (estimate === undefined) return false;
            // A level exam is passed at an assessment not below the level's target; a diagnostic section — once taken.
            const level = LEVEL_EXAM.exec(activity.id);
            return level ? estimate >= LEVEL_EXAM_TARGET[Number(level[1])] : true;
        }
        default: return null;
    }
}

/**
 * The module is closed automatically: it has checkable steps and all of them are done. Uncheckable steps do not prevent closing;
 * a module made only of uncheckable steps is not closed automatically.
 */
export function moduleAutoDone(module: CourseModule, facts: CourseFacts): boolean {
    return stepsAutoDone(module.steps, facts);
}

/** An exercise set is closed automatically: there are checkable ones and all are done (the shared rule of a course module and a program session). */
export function stepsAutoDone(steps: Activity[], facts: CourseFacts): boolean {
    const checked = steps.map((step) => activityDone(step, facts)).filter((done) => done !== null);
    return checked.length > 0 && checked.every(Boolean);
}

/**
 * Auto-credit of a training program (22.3): program progress is the number of sessions in order, so starting from those already completed
 * (done) consecutive sessions closed automatically are credited (stepsAutoDone). A session without checkable exercises
 * stops the count — the player marks it with a button.
 */
export function programAutoCount(sessions: Activity[][], done: number, facts: CourseFacts): number {
    let count = done;
    while (count < sessions.length && stepsAutoDone(sessions[count], facts)) count += 1;
    return count;
}
