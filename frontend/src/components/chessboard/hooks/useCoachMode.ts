// --- FILE: frontend/src/components/chessboard/hooks/useCoachMode.ts ---
// Playing with the coach (task 11.3), only in a bot game and on the free board. After the player's move the server evaluates the
// move in the background (POST /analysis/check-move); the game does not stop meanwhile (owner's decision 18.11: the coach
// suggests but does not block). If the move is bad for the player's level, advice appears next to the board: "Why?",
// "Switch" (optionally together with the bot's reply already made), "Got it" and "Disagree". Warnings are
// limited to MAX_WARNINGS_PER_GAME per game and no more often than once per MIN_MOVES_BETWEEN_WARNINGS of one's own moves. A stepped hint (task 11.4,
// POST /analysis/hint): a hint in words -> which piece to move -> the move with an arrow; a step counter. Any use of the
// coach makes the game a training one (rule 2): the assisted mark goes to the server when a bot game is saved.
// "Disagree" is POST /analysis/dispute: the position goes into the queue of disputed evaluations. The server rejects the move check and the hint
// while the player has a game against a human in progress, and limits them by the coach quota. Whether the coach is on
// and the chosen level are remembered in localStorage (keys regence_coach_enabled, regence_coach_level); until the player
// chooses a level, it is determined by rating. In a ladder or tournament game Chessboard does not call the move check, and
// the coach panel is locked.

import {useCallback, useRef, useState} from 'react';
import type {Chess} from 'chess.js';
import {API_BASE_URL} from '../../../config/api';
import {readApiError} from '../../../services/apiErrors';
import type {CoachComment} from '../../../services/coach';
import type {UiMessage} from '../../../i18n';
import {getToken} from '../../../services/authToken';

export type CoachLevel = 'novice' | 'amateur' | 'strong';
export const COACH_LEVELS: readonly CoachLevel[] = ['novice', 'amateur', 'strong'];

export const COACH_ENABLED_KEY = 'regence_coach_enabled';
export const COACH_LEVEL_KEY = 'regence_coach_level';

/**
 * Response of POST /analysis/check-move (src/services/move_check.py). Evaluations are in hundredths of a pawn from the mover's point of view;
 * available=false means the engine could not evaluate the move, so there will be no warning.
 */
export interface MoveCheck {
    available: boolean;
    cp_loss?: number;
    classification?: string;
    symbol?: string;
    eval_before?: number;
    eval_after?: number;
    best_move_uci?: string;
    reply_uci?: string;
    missed_tactic?: boolean;
    coach?: CoachComment | null;
}

/**
 * How many times per game the coach warns about a move and after how many of one's own moves since the previous warning it
 * may warn again (owner's decision 18.11: "several times per game, not at every step"). When a warning is not allowed,
 * the move is not even sent for checking, so the coach quota is not spent.
 */
export const MAX_WARNINGS_PER_GAME = 3;
export const MIN_MOVES_BETWEEN_WARNINGS = 4;

/** Whether a warning is allowed now: there is still allowance for the game and enough moves have passed since the previous warning. */
export function warningAllowed(shown: number, movesSinceLast: number | null): boolean {
    return shown < MAX_WARNINGS_PER_GAME && (movesSinceLast === null || movesSinceLast >= MIN_MOVES_BETWEEN_WARNINGS);
}

/** Position after which the advantage is so large that a "loss" does not change the result: no warning. */
const STILL_WINNING_CP = 600;
/** Loss at which a missed capture is mentioned even with a decisive advantage. */
const MISSED_WHILE_WINNING_CP = 200;

/**
 * Whether to warn the player: a beginner only about gross blunders (a loss of 300 hundredths of a pawn or more), an amateur about mistakes
 * (from 150) and missed captures (from 50), a strong player also about inaccuracies (from 100; with a missed capture, from 30). While
 * the advantage is decisive (not less than 600 after the move and a loss under 500), small losses do not disturb. The thresholds are only
 * here, on the client: the server sends numbers and this function makes the decision about warning.
 */
export function shouldWarn(check: MoveCheck, level: CoachLevel): boolean {
    if (!check.available) return false;
    const loss = check.cp_loss ?? 0;
    const missed = Boolean(check.missed_tactic);
    // While the advantage is decisive, trifles do not disturb, but a missed costly capture (200 cp or more) is worth mentioning:
    // that is how one learns to convert a won position, not only to avoid blunders.
    const stillWinning = (check.eval_after ?? 0) >= STILL_WINNING_CP && loss < 500;
    if (stillWinning && !(missed && loss >= MISSED_WHILE_WINNING_CP)) return false;
    if (level === 'novice') return loss >= 300;
    if (level === 'amateur') return loss >= 150 || (missed && loss >= 50);
    return loss >= 100 || (missed && loss >= 30);
}

/** Level by the player's rating, until they have chosen one themselves. */
export function levelForRating(rating: number): CoachLevel {
    if (rating < 1200) return 'novice';
    if (rating < 1900) return 'amateur';
    return 'strong';
}

// Reading and writing the setting in localStorage; unavailable storage (private mode) is not an error.
function readStored<T extends string>(key: string, allowed: readonly T[]): T | null {
    try {
        const value = localStorage.getItem(key);
        return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : null;
    } catch {
        return null;
    }
}

function store(key: string, value: string): void {
    try {
        localStorage.setItem(key, value);
    } catch {
        // private mode: the setting is simply not remembered
    }
}

/** The player's move that is being checked or about which the player decides what to do. */
export interface PendingCheck {
    /** checking: waiting for the server response; warning: the move is bad, the player decides. */
    status: 'checking' | 'warning';
    /** Position before the move, for "Switch". */
    previousGame: Chess;
    /** Position before the move and the move itself, for "Disagree". */
    fenBefore: string;
    uci: string;
    /** FEN after the move: a server response for another position (the player has moved on) is dropped. */
    fenAfter: string;
    check?: MoveCheck;
}

export interface UseCoachModeResult {
    enabled: boolean;
    setEnabled: (enabled: boolean) => void;
    level: CoachLevel;
    setLevel: (level: CoachLevel) => void;
    pending: PendingCheck | null;
    /** Show the explanation ("Why?"): the coach's text and arrows. */
    explanation: CoachComment | null;
    showWhy: () => void;
    /** Move kept: the game continues. */
    keepMove: () => void;
    /** "Switch": returns the position before the move (the caller restores the board and clocks). */
    takeBack: () => Chess | null;
    /** Last shown hint step (its text, arrows and highlight). */
    advice: CoachComment | null;
    adviceLoading: boolean;
    /** Next hint step for the position (a new position starts from the first again). */
    requestHint: (fen: string) => Promise<void>;
    /** 0 means no hints for this position yet, 1-3 is the shown step. */
    hintStep: number;
    /** The move is already shown: nothing more to hint. */
    hintFinal: boolean;
    /** Hint steps used in the game. */
    hintsUsed: number;
    /** "Disagree": the position goes for review, the move stays. */
    dispute: () => void;
    /** The dispute is sent: show thanks until the next move. */
    disputeSent: boolean;
    /** Whether the coach was used in this game: the game is a training one. */
    assisted: boolean;
    error: UiMessage | null;
    /** Called after every player move: with the coach on, sends the move for checking. */
    onPlayerMove: (previousGame: Chess, fenBefore: string, uci: string, fenAfter: string) => void;
    /** New game: counters and the training-game mark start from zero. */
    reset: () => void;
    /** A move was made, and the previous arrows and explanation no longer apply. */
    clearOverlay: () => void;
}

// The token is passed if the player is signed in: the server uses it to count per-player limits and to check the fair play rule.
function authHeaders(): Record<string, string> {
    const token = getToken();
    return token ? {'Content-Type': 'application/json', Authorization: `Bearer ${token}`} : {'Content-Type': 'application/json'};
}

/**
 * State of playing with the coach for the main board. playerRating is the player's rating (blitz from GET /profile/me), from which
 * the level is chosen until the player chooses one. The hook does not control the board: the caller reports the move
 * (onPlayerMove) and itself restores the position via takeBack. The coach never stops the game.
 */
export function useCoachMode(playerRating: number): UseCoachModeResult {
    const [enabled, setEnabledState] = useState<boolean>(() => readStored(COACH_ENABLED_KEY, ['1', '0']) === '1');
    const [chosenLevel, setChosenLevel] = useState<CoachLevel | null>(() => readStored(COACH_LEVEL_KEY, COACH_LEVELS));
    const [pending, setPending] = useState<PendingCheck | null>(null);
    const [explanation, setExplanation] = useState<CoachComment | null>(null);
    const [advice, setAdvice] = useState<CoachComment | null>(null);
    const [adviceLoading, setAdviceLoading] = useState(false);
    const [hintsUsed, setHintsUsed] = useState(0);
    const [hintStep, setHintStep] = useState(0);
    const [hintFinal, setHintFinal] = useState(false);
    const [disputeSent, setDisputeSent] = useState(false);
    // Position and step of the last hint: a repeated request for the same position gives the next step.
    const hintRef = useRef<{ fen: string; step: number } | null>(null);
    const [assisted, setAssisted] = useState(false);
    const [error, setError] = useState<UiMessage | null>(null);
    // A copy of pending for asynchronous code: a server response is matched against the move that awaits checking right now.
    const pendingRef = useRef<PendingCheck | null>(null);
    // Warning frequency (MAX_WARNINGS_PER_GAME, MIN_MOVES_BETWEEN_WARNINGS): how many were shown in the game and the number
    // of one's own move of the last one; moves is the counter of one's own moves in the game.
    const warnRef = useRef<{ shown: number; lastMove: number | null; moves: number }>({shown: 0, lastMove: null, moves: 0});
    const level = chosenLevel ?? levelForRating(playerRating);

    const updatePending = useCallback((next: PendingCheck | null) => {
        pendingRef.current = next;
        setPending(next);
    }, []);

    const setEnabled = useCallback((value: boolean) => {
        setEnabledState(value);
        store(COACH_ENABLED_KEY, value ? '1' : '0');
        if (!value) updatePending(null);
    }, [updatePending]);

    const setLevel = useCallback((value: CoachLevel) => {
        setChosenLevel(value);
        store(COACH_LEVEL_KEY, value);
    }, []);

    const clearOverlay = useCallback(() => {
        setExplanation(null);
        setAdvice(null);
        setHintStep(0);
        setHintFinal(false);
        setDisputeSent(false);
        hintRef.current = null;
    }, []);

    // Move check runs in the background: the game does not wait (the bot replies, the clocks run). A bad move produces advice next to the board, not
    // a stop; "Switch" is at the player's discretion. A move is sent for checking only if a warning is allowed
    // now (warningAllowed). The game is marked as training when a move is sent for checking. A network error or server refusal
    // (limit, engine busy) is shown as a message, the move stays.
    const onPlayerMove = useCallback((previousGame: Chess, fenBefore: string, uci: string, fenAfter: string) => {
        clearOverlay();
        updatePending(null);
        if (!enabled) return;
        const warn = warnRef.current;
        warn.moves += 1;
        if (!warningAllowed(warn.shown, warn.lastMove === null ? null : warn.moves - warn.lastMove)) return;
        setAssisted(true);
        setError(null);
        updatePending({status: 'checking', previousGame, fenBefore, uci, fenAfter});
        void (async () => {
            let check: MoveCheck | null = null;
            try {
                const res = await fetch(`${API_BASE_URL}/api/v1/analysis/check-move`, {
                    method: 'POST', headers: authHeaders(), body: JSON.stringify({fen: fenBefore, move: uci}),
                });
                if (res.ok) check = await res.json();
                else setError(await readApiError(res));
            } catch {
                setError({key: 'coachMode.unavailable'});
            }
            // The player has played on (free board): a response for the old position is not needed.
            if (pendingRef.current?.fenAfter !== fenAfter) return;
            if (check && shouldWarn(check, level)) {
                warnRef.current.shown += 1;
                warnRef.current.lastMove = warnRef.current.moves;
                updatePending({status: 'warning', previousGame, fenBefore, uci, fenAfter, check});
            } else {
                updatePending(null);
            }
        })();
    }, [enabled, level, clearOverlay, updatePending]);

    const showWhy = useCallback(() => {
        const current = pendingRef.current;
        if (current?.check?.coach) setExplanation(current.check.coach);
    }, []);

    const keepMove = useCallback(() => {
        updatePending(null);
        setExplanation(null);
    }, [updatePending]);

    const takeBack = useCallback((): Chess | null => {
        const current = pendingRef.current;
        if (!current) return null;
        updatePending(null);
        setExplanation(null);
        return current.previousGame;
    }, [updatePending]);

    const dispute = useCallback(() => {
        const current = pendingRef.current;
        if (!current) return;
        const body = {fen: current.fenBefore, move: current.uci, cp_loss: current.check?.cp_loss ?? null};
        updatePending(null);
        setExplanation(null);
        setDisputeSent(true);
        // Sent without waiting: the player continues the game, and a queue failure does not concern them.
        void fetch(`${API_BASE_URL}/api/v1/analysis/dispute`, {
            method: 'POST', headers: authHeaders(), body: JSON.stringify(body),
        }).catch(() => undefined);
    }, [updatePending]);

    // The client picks the step (1-3), but which step is shown and whether it is the last one comes from the server response
    // (step, final). Every received step counts in hintsUsed and makes the game a training one.
    const requestHint = useCallback(async (fen: string) => {
        const previous = hintRef.current;
        const step = previous && previous.fen === fen ? Math.min(3, previous.step + 1) : 1;
        setAdviceLoading(true);
        setError(null);
        setExplanation(null);
        try {
            const res = await fetch(`${API_BASE_URL}/api/v1/analysis/hint`, {
                method: 'POST', headers: authHeaders(), body: JSON.stringify({fen, step}),
            });
            if (res.ok) {
                const body = await res.json();
                hintRef.current = {fen, step: body.step};
                setAdvice(body);
                setHintStep(body.step);
                setHintFinal(Boolean(body.final));
                setHintsUsed((n) => n + 1);
                setAssisted(true);
            } else {
                setError(await readApiError(res));
            }
        } catch {
            setError({key: 'coachMode.unavailable'});
        } finally {
            setAdviceLoading(false);
        }
    }, []);

    const reset = useCallback(() => {
        updatePending(null);
        setExplanation(null);
        setAdvice(null);
        setHintStep(0);
        setHintFinal(false);
        setDisputeSent(false);
        hintRef.current = null;
        setHintsUsed(0);
        setAssisted(false);
        setError(null);
        warnRef.current = {shown: 0, lastMove: null, moves: 0};
    }, [updatePending]);

    return {
        enabled, setEnabled, level, setLevel, pending,
        explanation, showWhy, keepMove, takeBack,
        advice, adviceLoading, requestHint, hintStep, hintFinal, hintsUsed, dispute, disputeSent, assisted, error,
        onPlayerMove, reset, clearOverlay,
    };
}
