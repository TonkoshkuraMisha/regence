import {describe, expect, it} from 'vitest';
import {guessLevel} from '../guessLevel';

describe('guessLevel', () => {
    it('считает долю от максимума и уровень по порогам', () => {
        expect(guessLevel(200, 200)).toEqual({percent: 100, id: 'master'});
        expect(guessLevel(180, 200)).toEqual({percent: 90, id: 'master'});
        expect(guessLevel(140, 200)).toEqual({percent: 70, id: 'near'});
        expect(guessLevel(80, 200)).toEqual({percent: 40, id: 'confident'});
        expect(guessLevel(78, 200).id).toBe('learning');
    });

    it('пустая партия и выход за границы не ломают расчёт', () => {
        expect(guessLevel(0, 0)).toEqual({percent: 0, id: 'learning'});
        expect(guessLevel(500, 200).percent).toBe(100);
        expect(guessLevel(-5, 200).percent).toBe(0);
    });
});
