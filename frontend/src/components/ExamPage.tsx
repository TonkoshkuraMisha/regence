// Diagnostic exam (task 22.0): /exam has 10 tests by section of the theme catalog (10 positions each, from easy to
// hard) and an endgame exam of 30 positions. The solution is played to the end (to mate or the last move of the
// combination): the server checks the correct move (/move), the opponent replies with a move from the solution, a point per correct move;
// a mistake or "I don't know" ends the position, the points earned on it stay. There are no hints; at the end a strength estimate,
// a level by rank and a review. The game rating does not change; the results are starting data for the skill map.
// Great Course level exams (27.12, /exam?test=level<n>) are timed: the time_limit_s deadline is sent by the server along with
// the questions, the clock runs on the page, and on expiry the test is submitted by itself (positions not reached are empty, without points).

import {useEffect, useRef, useState} from 'react';
import {Chess} from 'chess.js';
import {Link, useSearchParams} from 'react-router-dom';
import {ArrowLeft, CheckCircle2, ClipboardCheck, XCircle} from 'lucide-react';
import {renderUiMessage, useI18n} from '../i18n';
import type {MessageKey, UiMessage} from '../i18n';
import {getToken} from '../services/authToken';
import {errorMessage} from '../services/apiErrors';
import {examCall} from '../services/exam';
import {PuzzleBoard} from './puzzles/PuzzleBoard';

/** Levels by rank that the server assigns to a strength estimate (src/services/exam.py, LEVELS). */
export type ExamLevel = 'novice' | 'fourth' | 'third' | 'second' | 'first' | 'candidate' | 'master';

/** Response of GET /exam: the latest results by section, the overall estimate and the level. */
export interface ExamSummary {
    tests: string[];
    /** Great Course level exams (27.12): level0 ... level5. */
    level_tests?: string[];
    results: Record<string, { correct: number; total: number; estimate: number; level: ExamLevel; at: string | null }>;
    overall: number | null;
    level: ExamLevel | null;
    passed: number;
    of: number;
}

/** Test position: the task id, the position after the opponent's move, whose turn it is and this move (for highlighting). */
interface Question {
    id: number;
    fen: string;
    color: 'white' | 'black';
    previous_move: string;
    branch?: string;
}

/** Result of a submitted test and a per-position review. */
interface Graded {
    correct: number;
    total: number;
    estimate: number;
    level: ExamLevel;
    review: {
        id: number; answer: string; correct: boolean; solution: string; solution_san: string; rating: number;
        points?: number; max_points?: number;
    }[];
    /** Points: correct moves across all positions out of the possible ones. */
    points?: number;
    max_points?: number;
    /** Level exam: correct / total by course branch. */
    branches?: Record<string, { correct: number; total: number }> | null;
}

/** Server response to a move during a test. */
interface MoveResult {
    correct: boolean;
    reply: string | null;
    done: boolean;
    solved: boolean;
    points: number;
    max_points: number;
}

/** Pause before the opponent's reply and before the next position: time to see one's own move and the end of the combination. */
export const EXAM_REPLY_MS = 450;
export const EXAM_NEXT_MS = 1100;
/** Clock refresh step of the timed exam (ms). */
const CLOCK_TICK_MS = 500;

// Move squares from a UCI record.
const squares = (uci: string) => ({from: uci.slice(0, 2), to: uci.slice(2, 4)});

/** Position after a move (UCI); if parsing fails, the previous one. */
function afterMove(fen: string, uci: string): string {
    try {
        const game = new Chess(fen);
        game.move({from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4]});
        return game.fen();
    } catch {
        return fen;
    }
}

// Course level test code: level0 ... level5.
const LEVEL_TEST = /^level(\d)$/;

/** Test name: a diagnostic section, the endgame exam or a course level exam. */
export function examTitle(t: (key: string, params?: Record<string, string | number>) => string, section: string): string {
    const level = LEVEL_TEST.exec(section);
    if (level) return t('exam.levelTest', {n: Number(level[1])});
    return section === 'endgame' ? t('exam.endgameTest') : `${section}. ${t(`puzzles.sections.${section}`)}`;
}

const call = examCall;

/** Latest results by section, for the "level passed" mark in the Great Course (27.12). */
export const fetchExamSummary = () => call<ExamSummary>('');

// The same as examTitle, but for the typed translation function.
const sectionLabel = (t: (key: MessageKey, params?: Record<string, string | number>) => string, section: string) =>
    examTitle(t as unknown as (key: string, params?: Record<string, string | number>) => string, section);

/**
 * Exam: test choice, going through positions and a review. Moves go to the server one at a time (/move); timers
 * are kept in timers and cleared when leaving the page.
 */
export function ExamPage() {
    const {t} = useI18n();
    const logged = Boolean(getToken());
    const [summary, setSummary] = useState<ExamSummary | null>(null);
    const [section, setSection] = useState<string | null>(null);
    const [questions, setQuestions] = useState<Question[]>([]);
    // The player's moves for each completed position; the current position is played and board (the position after the played moves).
    const [answers, setAnswers] = useState<string[][]>([]);
    const [played, setPlayed] = useState<string[]>([]);
    const [board, setBoard] = useState<{ fen: string; last: string; mark?: boolean } | null>(null);
    const [points, setPoints] = useState(0);
    const [flash, setFlash] = useState<{ kind: 'right' | 'solved' | 'wrong'; gain: number } | null>(null);
    const [waiting, setWaiting] = useState(false);
    const timers = useRef<number[]>([]);
    const later = (fn: () => void, ms: number) => {
        timers.current.push(window.setTimeout(fn, ms));
    };
    const clearTimers = () => {
        timers.current.forEach((id) => window.clearTimeout(id));
        timers.current = [];
    };
    useEffect(() => clearTimers, []);
    const resetQuestion = () => {
        setPlayed([]);
        setBoard(null);
        setFlash(null);
        setWaiting(false);
    };
    const [graded, setGraded] = useState<Graded | null>(null);
    // A level exam is timed (time_limit_s from the server): the deadline from the start of the test; on expiry the test is submitted by itself,
    // positions the player did not reach go empty (without points). timedOut shows this in the result.
    const [deadline, setDeadline] = useState<number | null>(null);
    const [now, setNow] = useState(() => Date.now());
    const [timedOut, setTimedOut] = useState(false);
    // The test is submitted once: by the last position or by time, whichever happens first.
    const submitted = useRef(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<UiMessage | null>(null);

    const loadSummary = () => {
        if (!logged) return;
        call<ExamSummary>('').then(setSummary).catch((err) => setError(errorMessage(err, 'common.networkError')));
    };
    useEffect(loadSummary, [logged]); // eslint-disable-line react-hooks/exhaustive-deps

    // Entry from a course or programme: /exam?test=level3 starts this test at once.
    const [search] = useSearchParams();
    const requested = search.get('test');

    const start = async (next: string) => {
        setBusy(true);
        setError(null);
        setGraded(null);
        try {
            const data = await call<{ questions: Question[]; time_limit_s?: number | null }>(`/${next}/questions`);
            clearTimers();
            const startedAt = Date.now();
            setNow(startedAt);
            setDeadline(data.time_limit_s ? startedAt + data.time_limit_s * 1000 : null);
            setTimedOut(false);
            submitted.current = false;
            setSection(next);
            setQuestions(data.questions);
            setAnswers([]);
            setPoints(0);
            resetQuestion();
        } catch (err) {
            setError(errorMessage(err, 'common.networkError'));
        } finally {
            setBusy(false);
        }
    };

    useEffect(() => {
        if (logged && requested && !section) void start(requested);
    }, [logged, requested]); // eslint-disable-line react-hooks/exhaustive-deps

    /** Submit the test: moves for the completed positions, the rest empty (time ran out earlier). */
    const submit = async (done: string[][]) => {
        if (!section || submitted.current) return;
        submitted.current = true;
        setBusy(true);
        try {
            setGraded(await call<Graded>(`/${section}/submit`, {answers: questions.map((q, i) => ({id: q.id, moves: done[i] ?? []}))}));
            loadSummary();
        } catch (err) {
            submitted.current = false;
            setError(errorMessage(err, 'common.networkError'));
        } finally {
            setBusy(false);
        }
    };

    /** The position is finished (solved, a mistake or "I don't know"): record the moves and go on or submit the test. */
    const finish = async (moves: string[]) => {
        const next = [...answers, moves];
        setAnswers(next);
        resetQuestion();
        if (next.length < questions.length || !section) return;
        await submit(next);
    };

    const secondsLeft = deadline === null ? null : Math.max(0, Math.ceil((deadline - now) / 1000));
    useEffect(() => {
        if (deadline === null || graded) return;
        const id = window.setInterval(() => setNow(Date.now()), CLOCK_TICK_MS);
        return () => window.clearInterval(id);
    }, [deadline, graded]);
    // Time is up: submit what there is, together with the moves of the current position.
    useEffect(() => {
        if (secondsLeft !== 0 || !section || graded || submitted.current) return;
        clearTimers();
        setTimedOut(true);
        void submit([...answers, played]);
    }, [secondsLeft]); // eslint-disable-line react-hooks/exhaustive-deps

    const current = section && !graded ? questions[answers.length] : null;
    const position = current ? board ?? {fen: current.fen, last: current.previous_move} : null;

    const move = async (uci: string) => {
        if (!current || !position || !section || waiting || busy) return;
        const moves = [...played, uci];
        setWaiting(true);
        setError(null);
        let result: MoveResult;
        try {
            result = await call<MoveResult>(`/${section}/move`, {id: current.id, moves});
        } catch (err) {
            // The move is neither counted nor lost: the position is the same, one can repeat.
            setError(errorMessage(err, 'common.networkError'));
            setWaiting(false);
            return;
        }
        const mine = afterMove(position.fen, uci);
        setBoard({fen: mine, last: uci, mark: result.correct});
        // A different mate counts as the whole solution: points at once for all the remaining moves.
        const gain = result.correct ? Math.max(1, result.points - played.length) : 0;
        if (gain) setPoints((value) => value + gain);
        setFlash({kind: !result.correct ? 'wrong' : result.done ? 'solved' : 'right', gain});
        if (result.done || !result.reply) {
            later(() => void finish(moves), EXAM_NEXT_MS);
            return;
        }
        const reply = result.reply;
        later(() => {
            setPlayed(moves);
            setBoard({fen: afterMove(mine, reply), last: reply});
            setWaiting(false);
        }, EXAM_REPLY_MS);
    };

    const back = () => {
        clearTimers();
        setSection(null);
        setQuestions([]);
        setAnswers([]);
        setPoints(0);
        resetQuestion();
        setGraded(null);
        setDeadline(null);
        setTimedOut(false);
        submitted.current = false;
    };

    const clock = secondsLeft === null ? null : `${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, '0')}`;

    return (
        <div className="w-full max-w-4xl mx-auto p-3 flex flex-col gap-4 text-boxwood-light" data-testid="exam-page">
            <header className="flex items-center gap-2">
                <ClipboardCheck className="text-amber-400"/>
                <h1 className="text-2xl font-bold text-amber-200">{t('exam.title')}</h1>
            </header>
            {!section && <p className="text-boxwood/85">{t('exam.intro')}</p>}
            {!logged && <p className="text-amber-300" data-testid="exam-login">{t('exam.loginRequired')}</p>}
            {error && <p role="alert" className="text-rose-300">{renderUiMessage(error, t)}</p>}

            {!section && summary && (
                <>
                    <p className="font-bold text-amber-300" data-testid="exam-overall">
                        {summary.overall && summary.level
                            ? t('exam.overall', {level: t(`exam.levels.${summary.level}`), rating: summary.overall, passed: summary.passed, of: summary.of})
                            : t('exam.noResults')}
                    </p>
                    <ul className="grid sm:grid-cols-2 gap-2">
                        {summary.tests.map((test) => {
                            const result = summary.results[test];
                            return (
                                <li key={test} className="bg-acacia rounded-lg border-2 border-acacia-dark p-3 flex flex-col gap-1.5 text-sm" data-testid={`exam-test-${test}`}>
                                    <span className="font-bold text-amber-200">{sectionLabel(t, test)}</span>
                                    <span className="text-xs text-boxwood/80">
                                        {result ? t('exam.lastResult', {correct: result.correct, total: result.total, level: t(`exam.levels.${result.level}`)})
                                            : t('exam.notTaken')}
                                    </span>
                                    <button type="button" disabled={busy} onClick={() => void start(test)} data-testid={`exam-start-${test}`}
                                            className="self-start px-3 py-1 rounded bg-amber-700 text-white font-bold text-xs disabled:opacity-50">
                                        {t(result ? 'exam.retake' : 'exam.start')}
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                    {summary.level_tests && summary.level_tests.length > 0 && (
                        <>
                            <h2 className="font-bold text-amber-300 mt-1">{t('exam.levelTests')}</h2>
                            <ul className="grid sm:grid-cols-3 gap-2">
                                {summary.level_tests.map((test) => {
                                    const result = summary.results[test];
                                    return (
                                        <li key={test} className="bg-acacia rounded-lg border-2 border-acacia-dark p-3 flex flex-col gap-1.5 text-sm" data-testid={`exam-test-${test}`}>
                                            <span className="font-bold text-amber-200">{sectionLabel(t, test)}</span>
                                            <span className="text-xs text-boxwood/80">
                                                {result ? t('exam.lastResult', {correct: result.correct, total: result.total, level: t(`exam.levels.${result.level}`)})
                                                    : t('exam.notTaken')}
                                            </span>
                                            <button type="button" disabled={busy} onClick={() => void start(test)} data-testid={`exam-start-${test}`}
                                                    className="self-start px-3 py-1 rounded bg-amber-700 text-white font-bold text-xs disabled:opacity-50">
                                                {t(result ? 'exam.retake' : 'exam.start')}
                                            </button>
                                        </li>
                                    );
                                })}
                            </ul>
                        </>
                    )}
                </>
            )}

            {section && (
                <button type="button" onClick={back} className="self-start text-sm text-amber-400 hover:underline flex items-center gap-1">
                    <ArrowLeft size={14}/> {t('exam.backToList')}
                </button>
            )}

            {current && position && (
                <div className="flex flex-col lg:flex-row gap-5 items-start" data-testid="exam-question">
                    <div className="w-full max-w-[480px]">
                        <PuzzleBoard key={current.id} fen={position.fen} orientation={current.color}
                                     interactive={!busy && !waiting} onMove={(uci) => void move(uci)}
                                     lastMove={squares(position.last)}
                                     mark={position.mark === undefined ? null : {square: position.last.slice(2, 4), ok: position.mark}}/>
                    </div>
                    <div className="flex flex-col gap-2 text-sm">
                        <p className="font-bold text-amber-200">{sectionLabel(t, section!)}</p>
                        <p data-testid="exam-progress">{t('exam.progress', {n: answers.length + 1, total: questions.length})}</p>
                        {clock && <p className="font-mono font-bold text-amber-200" data-testid="exam-clock">{t('exam.timeLeft', {time: clock})}</p>}
                        <p className="font-bold text-amber-300" data-testid="exam-points">{t('exam.pointsNow', {points})}</p>
                        <p className="text-boxwood/80">{t(current.color === 'white' ? 'exam.whiteToMove' : 'exam.blackToMove')}</p>
                        <p className="text-xs text-boxwood/70">{t('exam.playToEnd')}</p>
                        <p className={`min-h-5 font-bold ${flash?.kind === 'wrong' ? 'text-rose-300' : 'text-emerald-300'}`}
                           data-testid="exam-flash" aria-live="polite">
                            {flash?.kind === 'right' && t('exam.moveRight', {gain: flash.gain})}
                            {flash?.kind === 'solved' && t('exam.solved', {gain: flash.gain})}
                            {flash?.kind === 'wrong' && t('exam.moveWrong')}
                        </p>
                        <button type="button" onClick={() => void finish(played)} disabled={busy || waiting} data-testid="exam-skip"
                                className="self-start px-3 py-1 rounded bg-black/30 border border-amber-900/50 text-xs disabled:opacity-50">{t('exam.skip')}</button>
                    </div>
                </div>
            )}

            {graded && (
                <section className="flex flex-col gap-2" data-testid="exam-result">
                    {timedOut && <p className="text-amber-300" data-testid="exam-time-up">{t('exam.timeUp')}</p>}
                    <p className="text-lg font-bold text-amber-200">
                        {t('exam.result', {correct: graded.correct, total: graded.total, level: t(`exam.levels.${graded.level}`), rating: graded.estimate})}
                    </p>
                    {graded.max_points !== undefined && graded.max_points > 0 && (
                        <p className="font-bold text-amber-300" data-testid="exam-result-points">
                            {t('exam.pointsTotal', {points: graded.points ?? 0, max: graded.max_points})}
                        </p>
                    )}
                    {graded.branches && (
                        <ul className="flex flex-wrap gap-2 text-sm" data-testid="exam-branches">
                            {Object.entries(graded.branches).map(([branch, score]) => (
                                <li key={branch} className="px-2 py-1 rounded bg-black/30 border border-amber-900/50">
                                    {t(`supercourse.branches.${branch}` as MessageKey)}: {score.correct}/{score.total}
                                </li>
                            ))}
                        </ul>
                    )}
                    <ol className="flex flex-col gap-1 text-sm">
                        {graded.review.map((r, i) => (
                            <li key={r.id} className="flex items-center gap-2">
                                {r.correct ? <CheckCircle2 size={16} className="text-emerald-400"/> : <XCircle size={16} className="text-rose-400"/>}
                                <span>
                                    {t('exam.reviewLine', {n: i + 1, move: r.solution_san, rating: r.rating})}
                                    {r.max_points !== undefined && ` · ${t('exam.reviewScore', {points: r.points ?? 0, max: r.max_points})}`}
                                </span>
                            </li>
                        ))}
                    </ol>
                    <Link to="/puzzles" className="self-start text-sm text-amber-400 hover:underline">{t('exam.train')}</Link>
                </section>
            )}
        </div>
    );
}
