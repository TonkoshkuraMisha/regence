// Auto-credit of course steps (owner plan 18.11, task 6): which step counts as done by the server facts,
// when a module closes by itself, and that an incomplete server reply breaks nothing.

import {afterEach, describe, expect, it, vi} from 'vitest';
import {activityDone, fetchCourseFacts, moduleAutoDone, moduleCheckable, programAutoCount} from '../courseProgress';
import type {CourseFacts} from '../courseProgress';
import type {CourseModule} from '../../content/supercourse';
import {setToken} from '../authToken';

const FACTS: CourseFacts = {
    lessons: ['tactics-pin', 'basics-check-mate', 'mates-back-rank-mate', 'endgame-kq-center', 'mini-pawn-war'],
    themes: ['fork'],
    trainers: ['coord_find'],
    exams: {level1: 1050, level2: 1150, A: 900},
};

afterEach(() => {
    vi.unstubAllGlobals();
    setToken(null);
});

describe('step done', () => {
    it('by progress records — with the same keys that the sections write', () => {
        expect(activityDone({kind: 'lesson', id: 'tactics-pin'}, FACTS)).toBe(true);
        expect(activityDone({kind: 'basics', id: 'checkMate'}, FACTS)).toBe(true);
        expect(activityDone({kind: 'mates', id: 'back_rank_mate'}, FACTS)).toBe(true);
        expect(activityDone({kind: 'endgame', id: 'kq_center'}, FACTS)).toBe(true);
        expect(activityDone({kind: 'mini', id: 'pawn_war'}, FACTS)).toBe(true);
        expect(activityDone({kind: 'lesson', id: 'tactics-skewer'}, FACTS)).toBe(false);
    });

    it('themes and trainers — by the server norm; the level exam — by the level target', () => {
        expect(activityDone({kind: 'theme', id: 'fork'}, FACTS)).toBe(true);
        expect(activityDone({kind: 'theme', id: 'pin'}, FACTS)).toBe(false);
        expect(activityDone({kind: 'trainer', id: 'coord_find'}, FACTS)).toBe(true);
        expect(activityDone({kind: 'exam', id: 'level1'}, FACTS)).toBe(true);   // 1050 ≥ 1000
        expect(activityDone({kind: 'exam', id: 'level2'}, FACTS)).toBe(false);  // 1150 < 1200
        expect(activityDone({kind: 'exam', id: 'A'}, FACTS)).toBe(true);        // diagnostics: passed
        expect(activityDone({kind: 'exam', id: 'B'}, FACTS)).toBe(false);
    });

    it('steps without an objective result are not checked', () => {
        expect(activityDone({kind: 'repertoire'}, FACTS)).toBeNull();
        expect(activityDone({kind: 'library', structure: 'iqp'}, FACTS)).toBeNull();
        expect(activityDone({kind: 'guess'}, FACTS)).toBeNull();
    });
});

describe('module', () => {
    const mixed: CourseModule = {code: 'T1.2', level: 1, branch: 'T',
        steps: [{kind: 'lesson', id: 'tactics-pin'}, {kind: 'theme', id: 'fork'}, {kind: 'repertoire'}]};
    const half: CourseModule = {...mixed, steps: [{kind: 'lesson', id: 'tactics-pin'}, {kind: 'theme', id: 'pin'}]};
    const manual: CourseModule = {code: 'O1.3', level: 1, branch: 'O', steps: [{kind: 'repertoire'}]};

    it('closes by itself when all checkable steps are done; uncheckable ones do not interfere', () => {
        expect(moduleAutoDone(mixed, FACTS)).toBe(true);
        expect(moduleAutoDone(half, FACTS)).toBe(false);
        expect(moduleAutoDone(manual, FACTS)).toBe(false);
        expect(moduleCheckable(mixed)).toBe(true);
        expect(moduleCheckable(manual)).toBe(false);
    });
});

describe('training program (22.3)', () => {
    const facts: CourseFacts = {lessons: ['tactics-pin'], themes: ['pin'], trainers: [], exams: {}};
    const sessions = [
        [{kind: 'lesson', id: 'tactics-pin'} as const, {kind: 'theme', id: 'pin'} as const],
        [{kind: 'theme', id: 'pin'} as const],
        [{kind: 'workout'} as const],
        [{kind: 'theme', id: 'pin'} as const],
    ];
    it('counts in a row from the passed one and stops at an uncheckable activity', () => {
        expect(programAutoCount(sessions, 0, facts)).toBe(2);
        expect(programAutoCount(sessions, 3, facts)).toBe(4);
        expect(programAutoCount(sessions, 0, {...facts, themes: []})).toBe(0);
    });
});

describe('server reply', () => {
    it('without login — null; missing fields — empty', async () => {
        expect(await fetchCourseFacts()).toBeNull();
        setToken('jwt');
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, json: async () => ({themes: ['fork']})}) as Response));
        expect(await fetchCourseFacts()).toEqual({lessons: [], themes: ['fork'], trainers: [], exams: {}});
    });
});
