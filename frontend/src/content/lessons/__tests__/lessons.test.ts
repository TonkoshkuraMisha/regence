// School content check in CI (task 14.1): every lesson passes validateLesson - moves are legal, every
// question has a correct answer, texts in several languages. The validator itself is tested on deliberately broken lessons.

import {describe, expect, it} from 'vitest';
import {COURSES, LESSONS, lessonById, nextLesson} from '..';
import type {Lesson} from '../format';
import {validateLesson} from '../validate';

describe('lesson content', () => {
    it('has at least one course and lesson', () => {
        expect(COURSES.length).toBeGreaterThan(0);
        expect(LESSONS.length).toBeGreaterThan(0);
    });

    it.each(LESSONS.map((lesson) => [lesson.id, lesson] as const))('lesson %s is valid', (_id, lesson) => {
        expect(validateLesson(lesson, COURSES)).toEqual([]);
    });

    it('lesson ids are unique, order within a course has no repeats', () => {
        const ids = LESSONS.map((l) => l.id);
        expect(new Set(ids).size).toBe(ids.length);
        for (const course of COURSES) {
            const orders = LESSONS.filter((l) => l.course === course.id).map((l) => l.order);
            expect(new Set(orders).size).toBe(orders.length);
        }
    });

    it('the registry finds a lesson and the next one', () => {
        const first = LESSONS[0];
        expect(lessonById(first.id)).toBe(first);
        expect(lessonById('no-such-lesson')).toBeUndefined();
        // Lessons are sorted by course and order: the last lesson has no next one.
        expect(nextLesson(LESSONS[LESSONS.length - 1])).toBeUndefined();
    });
});

describe('validator catches errors', () => {
    const base = (): Lesson => structuredClone(lessonById('tactics-double-attack')!);
    const problemsOf = (mutate: (l: Lesson) => void) => {
        const lesson = base();
        mutate(lesson);
        return validateLesson(lesson, COURSES).join('\n');
    };

    it('illegal demo move', () => {
        expect(problemsOf((l) => {
            const demo = l.steps.find((s) => s.type === 'demo')!;
            if (demo.type === 'demo') demo.actions.unshift({do: 'move', uci: 'e1e5'});
        })).toMatch(/illegal move e1e5/);
    });

    it('illegal or missing correct answer', () => {
        expect(problemsOf((l) => {
            const q = l.steps.find((s) => s.type === 'find_move')!;
            if (q.type === 'find_move') q.line[0].answers = ['a1a8'];
        })).toMatch(/correct answer a1a8 is illegal/);
        expect(problemsOf((l) => {
            const q = l.steps.find((s) => s.type === 'find_move')!;
            if (q.type === 'find_move') q.line[0].answers = [];
        })).toMatch(/no correct answer/);
    });

    it('reply to an illegal wrong move and a move that is both correct and wrong', () => {
        expect(problemsOf((l) => {
            const q = l.steps.find((s) => s.type === 'find_move')!;
            if (q.type === 'find_move') q.line[0].wrong = {h1h8: {en: 'x', uk: 'x'}, d5e7: {en: 'x', uk: 'x'}};
        })).toMatch(/h1h8 is illegal[\s\S]*d5e7 is both correct and wrong/);
    });

    it('choice question without a correct option', () => {
        expect(problemsOf((l) => {
            const q = l.steps.find((s) => s.type === 'choice')!;
            if (q.type === 'choice') q.options.forEach((o) => delete o.correct);
        })).toMatch(/no correct option/);
    });

    it('text missing one of the languages', () => {
        expect(problemsOf((l) => {
            (l.steps[0].text as Record<string, string>).uk = '';
        })).toMatch(/missing uk text/);
    });

    it('invalid FEN, unknown course, empty exam', () => {
        const problems = problemsOf((l) => {
            l.steps[0] = {...l.steps[0], fen: 'not a fen'} as Lesson['steps'][number];
            l.course = 'nope';
            l.exam = [];
        });
        expect(problems).toMatch(/invalid FEN/);
        expect(problems).toMatch(/no course nope/);
        expect(problems).toMatch(/the exam needs 1..5 questions/);
    });

    it('line continues without a computer reply', () => {
        expect(problemsOf((l) => {
            const q = l.exam.find((s) => s.type === 'find_move')!;
            if (q.type === 'find_move') delete q.line[0].reply;
        })).toMatch(/no computer reply/);
    });
});
