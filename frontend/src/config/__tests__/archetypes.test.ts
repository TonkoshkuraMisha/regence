// The error rate of weak workshop opponents — the same curve as on the server (task 10.5).

import {describe, expect, it} from 'vitest';
import {DEFAULT_CONFIG} from '../../services/personalities';
import {errorRate, strengthNote} from '../archetypes';

describe('workshop opponent strength', () => {
    it('the error rate by the calibration curve — a straight line up to 1500', () => {
        expect(errorRate(600)).toBeCloseTo(0.43);
        expect(errorRate(1000)).toBeCloseTo(0.2389, 4);
        expect(errorRate(1320)).toBeCloseTo(0.086);
        expect(errorRate(1450)).toBeCloseTo(0.0239, 4);
        expect(errorRate(1500)).toBe(0);
        expect(errorRate(2000)).toBe(0);
    });

    it('the label: mistakes up to 1500, exact strength above', () => {
        expect(strengthNote({...DEFAULT_CONFIG, target_elo: 1320})).toContain('9%');
        expect(strengthNote({...DEFAULT_CONFIG, target_elo: 1500})).not.toMatch(/%/);
    });
});
