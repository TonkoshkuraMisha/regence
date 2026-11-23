// Training programs (task 22.3): each has 8 weeks of 5 sessions, and every exercise leads to an existing section.

import {describe, expect, it} from 'vitest';
import {activityLink, PROGRAMS, SESSIONS_PER_PROGRAM, sessionsOf} from '../programs';
import {lessonById} from '../lessons';
import {BASICS} from '../basics/levels';
import {EXERCISES} from '../../components/learn/EndgameTrainer';
import {TRAINER_IDS} from '../../services/trainers';
import {MINI_GAMES} from '../../components/trainers/MiniGames';
import {hasMessage} from '../../i18n';

const EXAM = ['F', 'A', 'B', 'C', 'D', 'E', 'G', 'H', 'I', 'J', 'endgame'];

describe('training programs', () => {
    it('8 weeks x 5 sessions', () => {
        expect(PROGRAMS.map((p) => p.id)).toEqual(['first_steps', 'to_1200', 'club', 'advanced']);
        for (const program of PROGRAMS) {
            expect(program.weeks).toHaveLength(8);
            expect(program.weeks.every((week) => week.length === 5)).toBe(true);
            expect(sessionsOf(program)).toHaveLength(SESSIONS_PER_PROGRAM);
        }
    });

    it('every exercise exists', () => {
        const missing: string[] = [];
        for (const program of PROGRAMS) {
            for (const activity of sessionsOf(program).flat()) {
                const ok = (() => {
                    switch (activity.kind) {
                        case 'basics': return BASICS.some((s) => s.id === activity.id);
                        case 'lesson': return lessonById(activity.id) !== undefined;
                        case 'mates':
                        case 'theme': return hasMessage(`themes.${activity.id}.name`);
                        case 'endgame': return EXERCISES.some((e) => e.id === activity.id);
                        case 'trainer': return (TRAINER_IDS as readonly string[]).includes(activity.id);
                        case 'mini': return (MINI_GAMES as readonly string[]).includes(activity.id);
                        case 'exam': return EXAM.includes(activity.id);
                        default: return true;
                    }
                })();
                if (!ok) missing.push(`${program.id}: ${activity.kind} ${'id' in activity ? activity.id : ''}`);
            }
        }
        expect(missing).toEqual([]);
    });

    it('links: a puzzle theme opens with training', () => {
        expect(activityLink({kind: 'theme', id: 'fork'})).toEqual({to: '/puzzles', state: {train: {theme: 'fork', blind: false}}});
        expect(activityLink({kind: 'endgame', id: 'lucena'}).to).toBe('/learn/endgames/lucena');
        expect(activityLink({kind: 'play'}).to).toBe('/');
    });
});
