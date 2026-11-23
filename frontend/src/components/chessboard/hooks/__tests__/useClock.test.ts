// Game clock: the exact time ticks every 50 ms, but a re-render happens only when the digits on the clock change
// (previously the whole Chessboard re-rendered 20 times a second).

import {act, renderHook} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {displayBucket, formatTime, useClock} from '../useClock';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function clock(initialMs: number) {
    let renders = 0;
    const hook = renderHook(() => {
        renders += 1;
        return useClock({isTicking: true, isParticipant: true, currentTurn: 'white', myColor: 'white', onLowTime: vi.fn()});
    });
    act(() => hook.result.current.setWhiteTimeMs(initialMs));
    const before = renders;
    return {hook, rendersSince: () => renders - before};
}

/** Ticks one at a time, each in its own act(): otherwise React would merge all the updates into one re-render. */
function tickFor(ms: number) {
    for (let elapsed = 0; elapsed < ms; elapsed += 50) {
        act(() => {
            vi.advanceTimersByTime(50);
        });
    }
}

describe('useClock', () => {
    it('hourglass clock: the mover\'s time is added to the opponent (handicap, task 21.1)', () => {
        const hook = renderHook(() => useClock({isTicking: true, isParticipant: true, currentTurn: 'white', myColor: 'white',
            onLowTime: vi.fn(), hourglass: true}));
        act(() => {
            hook.result.current.setWhiteTimeMs(60_000);
            hook.result.current.setBlackTimeMs(60_000);
        });
        tickFor(2_000);
        expect(formatTime(hook.result.current.whiteTimeMs)).toBe('00:58');
        expect(formatTime(hook.result.current.blackTimeMs)).toBe('01:02');
    });

    it('outside time trouble — a re-render once a second, not every 50 ms', () => {
        const {hook, rendersSince} = clock(60_000);
        tickFor(3_000);
        expect(rendersSince()).toBeLessThanOrEqual(4);  // was 60: every 50 ms tick
        expect(formatTime(hook.result.current.whiteTimeMs)).toBe('00:57');
    });

    it('in time trouble — tenths, a re-render every 100 ms', () => {
        const {hook, rendersSince} = clock(10_000);
        tickFor(1_000);
        expect(rendersSince()).toBeGreaterThanOrEqual(9);
        expect(rendersSince()).toBeLessThanOrEqual(11);
        expect(formatTime(hook.result.current.whiteTimeMs)).toBe('00:09.0');
    });

    it('the flag falls exactly at zero, an increment takes the exact time into account', () => {
        const {hook} = clock(1_000);
        act(() => {
            vi.advanceTimersByTime(1_500);
        });
        expect(hook.result.current.whiteTimeMs).toBe(0);

        act(() => hook.result.current.setWhiteTimeMs(60_400));
        act(() => {
            vi.advanceTimersByTime(300);  // the digits did not change (00:60 → 00:60), the state was not updated
        });
        act(() => hook.result.current.applyIncrement('white', 2));
        expect(hook.result.current.whiteTimeMs).toBe(62_100);  // 60 400 − 300 + 2 000 — from the exact time
    });

    it('the display step matches formatTime', () => {
        expect(displayBucket(30_000)).not.toBe(displayBucket(29_999));
        expect(displayBucket(45_100)).toBe(displayBucket(45_900));
        expect(displayBucket(5_150)).toBe(displayBucket(5_199));
        expect(displayBucket(5_150)).not.toBe(displayBucket(5_050));
    });
});
