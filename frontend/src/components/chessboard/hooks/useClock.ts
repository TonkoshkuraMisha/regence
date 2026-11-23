// --- FILE: frontend/src/components/chessboard/hooks/useClock.ts ---
// Game clock on the main board. The hook only counts down for the side to move. Where the time comes from:
// in a game against a human and for a spectator, from the server (white_time_ms and black_time_ms in the match_found, move_made,
// berserk, game_over events; useGameSocket sets them via setWhiteTimeMs and setBlackTimeMs), between events the clock runs
// locally and is reconciled with the server on every move; the flag in such a game is fixed by the server. In a bot game the clock is entirely
// on the client: useBotGame sets the initial time and increment, and it also declares a loss on time.

import {useCallback, useEffect, useRef, useState} from 'react';

export type ClockColor = 'white' | 'black';

export interface UseClockOptions {
    /** The clock runs visually (player, bot, spectator): the game is active and not finished. */
    isTicking: boolean;
    /**
     * The audible low-time warning plays only for a participant of the game, not a spectator:
     * this condition is stricter than isTicking (a spectator's clock runs but there is no sound), so it is passed separately.
     */
    isParticipant: boolean;
    currentTurn: ClockColor;
    myColor: ClockColor;
    onLowTime: () => void;
    /** "Hourglass clock" (handicap, task 21.1): the time the mover spends is added to the opponent. */
    hourglass?: boolean;
}

export interface UseClockResult {
    whiteTimeMs: number;
    blackTimeMs: number;
    setWhiteTimeMs: React.Dispatch<React.SetStateAction<number>>;
    setBlackTimeMs: React.Dispatch<React.SetStateAction<number>>;
    /** Resets the "warning already played" flag, before a new game. */
    resetLowTimeWarning: () => void;
    /**
     * Increment for the side that made the move (a negative value removes the increment, on a take-back).
     * Needed only by a bot game: in a game against a human the server sends the time after the move already with the increment.
     */
    applyIncrement: (moverColor: ClockColor, incrementSeconds: number) => void;
}

/**
 * Step at which the digits on the clock change (as in formatTime): seconds, and in time trouble (< 30 s) tenths.
 * Time gets into React state only when the visible value changes: before, every 50 ms
 * the whole Chessboard re-rendered: board, move log, panels (20 times a second in any game).
 */
export function displayBucket(ms: number): number {
    const value = Math.max(0, ms);
    return value >= 30000 ? Math.floor(value / 1000) : -1 - Math.floor(value / 100);
}

/** Exact time in a ref, in state its copy at the display step; the setter changes both. */
function useClockValue(initial: number) {
    const exactRef = useRef(initial);
    const [shown, setShown] = useState(initial);
    const set: React.Dispatch<React.SetStateAction<number>> = useCallback((value) => {
        const next = typeof value === 'function' ? value(exactRef.current) : value;
        exactRef.current = next;
        setShown(next);
    }, []);
    /** Clock tick: the exact time always changes, the state only when the digits on the clock change. */
    const tick = useCallback((delta: number) => {
        const before = exactRef.current;
        const after = Math.max(0, before - delta);
        exactRef.current = after;
        if (displayBucket(after) !== displayBucket(before) || after === 0) setShown(after);
    }, []);
    return [shown, set, tick] as const;
}

/**
 * Game clock: ticking every 50 ms for the side currently to move, an audible warning
 * about time trouble (no more than 10 s, once per game) and crediting the increment per move. It knows nothing about
 * the game's source (PvP/bot/spectator), only whether the clock runs and whose turn it is. The initial 3 minutes are
 * a placeholder until the first game: the caller sets the real time with the setters.
 */
export function useClock({isTicking, isParticipant, currentTurn, myColor, onLowTime, hourglass = false}: UseClockOptions): UseClockResult {
    const [whiteTimeMs, setWhiteTimeMs, tickWhite] = useClockValue(180000);
    const [blackTimeMs, setBlackTimeMs, tickBlack] = useClockValue(180000);
    // The low-time warning has already sounded in this game (resetLowTimeWarning resets it).
    const lowTimeWarnedRef = useRef(false);

    // Tick: the time actually elapsed since the previous tick (not "50 ms") is taken off the mover's clock, so the clock does not
    // lag when the tab is in the background and the browser slows timers. A change of turn restarts the countdown.
    useEffect(() => {
        if (!isTicking) return;

        let lastTick = Date.now();

        const interval = setInterval(() => {
            const now = Date.now();
            const delta = now - lastTick;
            lastTick = now;

            if (currentTurn === 'white') {
                tickWhite(delta);
                if (hourglass) tickBlack(-delta);
            } else {
                tickBlack(delta);
                if (hourglass) tickWhite(-delta);
            }
        }, 50);

        return () => clearInterval(interval);
    }, [isTicking, currentTurn, tickWhite, tickBlack, hourglass]);

    // Audible low-time warning (< 10 seconds on the player's clock)
    useEffect(() => {
        if (!isParticipant || lowTimeWarnedRef.current) return;
        const myRemainingMs = myColor === 'white' ? whiteTimeMs : blackTimeMs;
        if (myRemainingMs > 0 && myRemainingMs <= 10000) {
            lowTimeWarnedRef.current = true;
            onLowTime();
        }
    }, [whiteTimeMs, blackTimeMs, isParticipant, myColor, onLowTime]);

    const resetLowTimeWarning = useCallback(() => {
        lowTimeWarnedRef.current = false;
    }, []);

    const applyIncrement = useCallback((moverColor: ClockColor, incrementSeconds: number) => {
        const incMs = Math.round(incrementSeconds * 1000);
        if (moverColor === 'white') {
            setWhiteTimeMs(prev => prev + incMs);
        } else {
            setBlackTimeMs(prev => prev + incMs);
        }
    }, []);

    return {whiteTimeMs, blackTimeMs, setWhiteTimeMs, setBlackTimeMs, resetLowTimeWarning, applyIncrement};
}

/** Formats the remaining time as mm:ss (h:mm:ss from an hour), with tenths in time trouble < 30 s; zero is "00:00". */
export function formatTime(ms: number): string {
    const totalMs = Math.max(0, ms);
    const totalSecs = Math.floor(totalMs / 1000);
    const hours = Math.floor(totalSecs / 3600);
    const mins = Math.floor((totalSecs % 3600) / 60);
    const secs = totalSecs % 60;

    if (hours > 0) {
        return `${hours}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }

    if (totalMs < 30000 && totalMs > 0) {
        const tenths = Math.floor((totalMs % 1000) / 100);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${tenths}`;
    }

    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}
