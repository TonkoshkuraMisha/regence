// Big course (task 27.6): module codes are unique and match the level, branches are known, every step leads to an
// existing section; every level has filled modules and an exam.

import {describe, expect, it} from 'vitest';
import {BRANCHES, COURSE, courseProgressId, coverage, LEVEL_COUNT, moduleStatus, moduleTitleKey} from '../supercourse';
import type {CourseModule} from '../supercourse';
import type {Activity} from '../programs';
import {activityLink} from '../programs';
import {lessonById} from '../lessons';
import {BASICS} from '../basics/levels';
import {EXERCISES} from '../../components/learn/EndgameTrainer';
import {TRAINER_IDS} from '../../services/trainers';
import {MINI_GAMES} from '../../components/trainers/MiniGames';
import {STRUCTURES} from '../../services/library';
import {hasMessage} from '../../i18n';
import {CLASSIC_IDS, classicIdTitle, loadClassic} from '../classics';

const EXAM = ['F', 'A', 'B', 'C', 'D', 'E', 'G', 'H', 'I', 'J', 'endgame',
    'level0', 'level1', 'level2', 'level3', 'level4', 'level5'];  // level exams - 27.12

function exists(activity: Activity): boolean {
    switch (activity.kind) {
        case 'basics': return BASICS.some((s) => s.id === activity.id);
        case 'lesson': return lessonById(activity.id) !== undefined;
        case 'mates':
        case 'theme': return hasMessage(`themes.${activity.id}.name`);
        case 'endgame': return EXERCISES.some((e) => e.id === activity.id);
        case 'trainer': return (TRAINER_IDS as readonly string[]).includes(activity.id);
        case 'mini': return (MINI_GAMES as readonly string[]).includes(activity.id);
        case 'exam': return EXAM.includes(activity.id);
        case 'library': return !activity.structure || (STRUCTURES as readonly string[]).includes(activity.structure);
        case 'classics': return !activity.id || CLASSIC_IDS.includes(activity.id);
        default: return true;
    }
}

describe('Big course', () => {
    it('codes, levels and branches', () => {
        const codes = COURSE.map((m) => m.code);
        expect(new Set(codes).size).toBe(codes.length);
        for (const module of COURSE) {
            expect(module.level).toBeGreaterThanOrEqual(0);
            expect(module.level).toBeLessThan(LEVEL_COUNT);
            expect(BRANCHES).toContain(module.branch);
            expect(hasMessage(moduleTitleKey(module.code))).toBe(true);
            expect(courseProgressId(module.code)).toMatch(/^[a-z0-9][a-z0-9-]{1,63}$/);
        }
    });

    it('every step exists; every level has filled modules and an exam', () => {
        const missing = COURSE.flatMap((m) => m.steps.filter((s) => !exists(s)).map((s) => `${m.code}: ${JSON.stringify(s)}`));
        expect(missing).toEqual([]);
        for (let level = 0; level < LEVEL_COUNT; level++) {
            const modules = COURSE.filter((m) => m.level === level);
            expect(modules.filter((m) => m.steps.length > 0).length).toBeGreaterThan(5);
            expect(modules.some((m) => m.code === `X${level}`)).toBe(true);
        }
    });
});

describe('Must-know positions (27.9)', () => {
    it('three tiers from existing exercises, without repeats', async () => {
        const {MUST_KNOW} = await import('../mustKnow');
        const all = MUST_KNOW.flat();
        expect(MUST_KNOW).toHaveLength(3);
        expect(new Set(all).size).toBe(all.length);
        expect(all.filter((id) => !EXERCISES.some((e) => e.id === id))).toEqual([]);
        expect(all.every((id) => hasMessage(`endgames.items.${id}`))).toBe(true);
    });
});

describe('level exams (27.12)', () => {
    it('a level is passed when the estimate of its own exam is not below the threshold', async () => {
        const {examSections, levelExamPassed} = await import('../supercourse');
        expect(examSections(1)).toEqual(['level1']);
        expect(levelExamPassed(1, {level1: {estimate: 1000}})).toBe(true);
        expect(levelExamPassed(1, {level1: {estimate: 999}})).toBe(false);
        expect(levelExamPassed(2, {A: {estimate: 2000}, B: {estimate: 2000}})).toBe(false);  // the diagnostic does not count
        for (let level = 0; level < LEVEL_COUNT; level++) expect(examSections(level)).toEqual([`level${level}`]);
    });
});

describe('master games with stops (27.6)', () => {
    const games = COURSE.flatMap((module) => module.steps)
        .flatMap((step) => (step.kind === 'classics' && step.id ? [step] : []));
    const steps = games.map((step) => step.id!);

    it('the course links single games, and each opens its own page; a demo step - without stops', () => {
        expect(games.some((step) => !step.demo)).toBe(true);
        expect(games.some((step) => step.demo)).toBe(true);
        for (const step of games) {
            expect(activityLink(step).to).toBe(`/learn/classics/${step.id}${step.demo ? '?stops=off' : ''}`);
        }
        expect(activityLink({kind: 'classics'}).to).toBe('/learn/classics');
    });

    it('the label from the id matches the players and the year of the game file, and the game has stops', async () => {
        for (const id of steps) {
            const game = await loadClassic(id);
            expect(game).not.toBeNull();
            const surname = (player: string) => player.split(',')[0].trim();
            expect(classicIdTitle(id)).toBe(`${surname(game!.white)} – ${surname(game!.black)}, ${game!.year}`);
            expect(game!.stops.length).toBeGreaterThan(0);
        }
    });

    it('the step label key exists in both catalogs', () => {
        expect(hasMessage('programs.activities.classicGame')).toBe(true);
        expect(hasMessage('programs.activities.classicDemo')).toBe(true);
    });
});

describe('cell statuses and coverage for the author', () => {
    const at = (code: string, steps: number, draft = 0): CourseModule => ({
        code, level: Number(code.slice(1).split('.')[0]), branch: code[0] as CourseModule['branch'],
        steps: Array.from({length: steps}, () => ({kind: 'guess'}) as const),
        ...(draft ? {draft: Array.from({length: draft}, () => ({kind: 'guess'}) as const)} : {}),
    });

    it('ready steps outweigh drafts; with neither - empty', () => {
        expect(moduleStatus(at('T1.1', 2, 1))).toBe('ready');
        expect(moduleStatus(at('T1.2', 0, 1))).toBe('draft');
        expect(moduleStatus(at('T1.3', 0))).toBe('empty');
    });

    it('coverage counts modules by level and branch', () => {
        const table = coverage([at('T1.1', 1), at('T1.2', 0, 2), at('E1.1', 0), at('M3.1', 3)]);
        expect(table).toHaveLength(LEVEL_COUNT);
        expect(table[1][BRANCHES.indexOf('T')]).toEqual({ready: 1, draft: 1, empty: 0});
        expect(table[1][BRANCHES.indexOf('E')]).toEqual({ready: 0, draft: 0, empty: 1});
        expect(table[3][BRANCHES.indexOf('M')]).toEqual({ready: 1, draft: 0, empty: 0});
        expect(table[0].every((cell) => cell.ready + cell.draft + cell.empty === 0)).toBe(true);
    });

    it('in the real course all modules are ready, no drafts', () => {
        const total = coverage().flat().reduce((sum, cell) => sum + cell.ready, 0);
        expect(total).toBe(COURSE.length);
        expect(COURSE.every((m) => moduleStatus(m) === 'ready')).toBe(true);
    });
});

