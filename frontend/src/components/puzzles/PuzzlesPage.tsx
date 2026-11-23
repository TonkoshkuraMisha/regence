// --- FILE: frontend/src/components/puzzles/PuzzlesPage.tsx ---
// The "Techniques" mode (task 13.4) is TrainingPanel: a path by a registry theme with steps and mixed sets.
// The "Exercises" mode (task 13.7) is GeneratedDrills: generator positions "kind x piece", levels, "one minute".
// The "Defence" mode (task 13.6) is DefenseTrainer: "What is threatened?", "Don't blunder", "Only defence".
// The "My mistakes" mode (task 13.5) is positions before mistakes in the player's games with repetition at intervals.
// Puzzle page (task 13.3): solving by rating or theme, the daily puzzle, a timed mode (3/5 minutes, three mistakes
// end it, a personal record), a hint, "Show solution", a result with the rating change, history and a rating graph,
// "Review with the coach": the puzzle position on the free board with the coach on.
// Layout (owner's plan 18.11): the modes are three groups of tabs with an explanation (PuzzleModePicker, puzzleModes.ts);
// until a puzzle is loaded, instead of a board with the starting setup there are cards of all modes by group, the selected one
// large and with a "Start" button;
// the rating graph has labelled axes (the rating on the left, the dates of the first and last puzzle at the bottom).
// Data is services/puzzles.ts (/api/v1/puzzles/*, with sign-in only; puzzles, rating and the run are computed by the server,
// src/services/puzzles.py) and the theme registry services/themes.ts. Route /puzzles (App.tsx); entry from other sections is
// via location.state {train, mode} (the daily warm-up, task 22.2).
// By mode the page shows the puzzle board or an embedded trainer (techniques, exercises, defence).

import {useCallback, useEffect, useRef, useState} from 'react';
import {Link, useLocation, useNavigate} from 'react-router-dom';
import {Chess} from 'chess.js';
import {format, parseISO} from 'date-fns';
import {Puzzle as PuzzleIcon, Lightbulb, Flag, ArrowRight, GraduationCap} from 'lucide-react';
import {hasMessage, renderUiMessage, useI18n} from '../../i18n';
import type {UiMessage} from '../../i18n';
import {errorMessage} from '../../services/apiErrors';
import {DEFENSE_DRILL_THEMES, puzzlesApi} from '../../services/puzzles';
import type {DrillKind} from '../../services/puzzles';
import type {
    DefenseKind, HintResponse, PersonalAnswer, PersonalSummary, PersonalView, PuzzleProfile, PuzzleResult, PuzzleView,
    TimedResult, TimedRun, TrainingTarget,
} from '../../services/puzzles';
import {fetchThemeRegistry, themeText} from '../../services/themes';
import type {ThemeRegistry, ThemeSection} from '../../services/themes';
import {DefenseTrainer} from './DefenseTrainer';
import {GeneratedDrills} from './GeneratedDrills';
import {PuzzleBoard} from './PuzzleBoard';
import {sanMoves, solutionSan, toMove} from './puzzleNotation';
import {TimedLeaders} from './TimedLeaders';
import {TrainingPanel} from './TrainingPanel';
import {SolutionReplay} from './SolutionReplay';
import type {ReplayView} from './SolutionReplay';
import {ExplorerControls, usePositionExplorer} from './usePositionExplorer';
import {PuzzleModePicker} from './PuzzleModePicker';
import {MODE_GROUPS, MODE_ICONS, MODES} from './puzzleModes';
import type {Mode} from './puzzleModes';
import {Card, CardGrid, Section} from '../ui';

// The save mode is "Save the game" (27.9): a mixed set of puzzles with the goal "draw" (perpetual check, stalemate, fortress, equality).
/** Goal of the "Save the game" training: a set of puzzles with the "draw" goal without hiding the theme name. */
const SAVE_TARGET: TrainingTarget = {goal: 'draw', blind: false};
/** Puzzle stage: idle -> loading -> opponent (the opponent's first move) -> solving -> waiting (waiting for the server) -> done. */
type Phase = 'idle' | 'loading' | 'opponent' | 'solving' | 'waiting' | 'done';

/** Pause before the opponent's first move in a puzzle, ms. */
const OPPONENT_DELAY_MS = 500;
/** Pause before the opponent's reply to the solver's correct move, ms. */
const REPLY_DELAY_MS = 400;
/** Step of showing the solution move by move, ms. */
const SOLUTION_STEP_MS = 700;

// Re-export: the puzzles.test.tsx test takes solutionSan from the puzzle page.
export {solutionSan};

/** Client error to an interface message: a server code or a generic network error. */
/** Rounding step of the rating scale bounds and the margin above and below the extreme points. */
const CHART_STEP = 10;
const CHART_MARGIN = 5;

/**
 * Rating graph in puzzles by attempt history (puzzlesApi.me -> history, newest first). On the left is the rating scale
 * (top, middle, bottom), at the bottom are the dates of the first and last attempt on the graph.
 */
export function RatingChart({history}: { history: PuzzleProfile['history'] }) {
    const {t, dateLocale} = useI18n();
    const points = [...history].reverse();
    if (points.length < 2) return null;
    const values = points.map((h) => h.rating_after);
    const low = Math.floor((Math.min(...values) - CHART_MARGIN) / CHART_STEP) * CHART_STEP;
    const high = Math.ceil((Math.max(...values) + CHART_MARGIN) / CHART_STEP) * CHART_STEP;
    const middle = Math.round((low + high) / 2);
    const y = (value: number) => 40 - ((value - low) / (high - low)) * 40;
    const path = values.map((value, i) => `${((i / (values.length - 1)) * 100).toFixed(2)},${y(value).toFixed(2)}`).join(' ');
    const day = (iso: string | null) => (iso ? format(parseISO(iso), 'd MMM', {locale: dateLocale}) : '');
    return (
        <div className="grid grid-cols-[auto_1fr] gap-x-2 text-[10px] font-mono text-boxwood/70">
            <div className="flex flex-col justify-between h-24 text-right" aria-hidden data-testid="puzzle-chart-scale">
                <span>{high}</span><span>{middle}</span><span>{low}</span>
            </div>
            <svg viewBox="0 0 100 40" className="w-full h-24 border-l border-b border-amber-900/60" role="img"
                 aria-label={t('puzzles.chart')} data-testid="puzzle-chart" preserveAspectRatio="none">
                <line x1="0" x2="100" y1={y(middle)} y2={y(middle)} stroke="rgba(251, 191, 36, 0.15)"
                      strokeDasharray="2 2" vectorEffect="non-scaling-stroke"/>
                <polyline points={path} fill="none" stroke="rgb(251, 191, 36)" strokeWidth="1.5"
                          vectorEffect="non-scaling-stroke"/>
            </svg>
            <span/>
            <div className="flex justify-between" aria-hidden>
                <span>{day(points[0].created_at)}</span><span>{day(points[points.length - 1].created_at)}</span>
            </div>
        </div>
    );
}

/** Name of the opponent bot from the catalog (a historical master); an unknown id is shown as is. */
function botShortName(id: string, t: ReturnType<typeof useI18n>['t']): string {
    const key = `bots.profiles.${id}.shortName`;
    return hasMessage(key) ? t(key) : id;
}

export default function PuzzlesPage() {
    const {t, dateLocale} = useI18n();
    const navigate = useNavigate();
    const [mode, setMode] = useState<Mode>('rated');
    const [theme, setTheme] = useState<string | null>(null);
    const [registry, setRegistry] = useState<ThemeRegistry | null>(null);
    const [puzzle, setPuzzle] = useState<PuzzleView | null>(null);
    const [fen, setFen] = useState(new Chess().fen());
    const [startFen, setStartFen] = useState<string | null>(null);
    const [phase, setPhase] = useState<Phase>('idle');
    // "Candidates" (27.9): before moving, mark 2-3 candidate moves; after solving, whether the correct move was among them.
    const [candidatesOn, setCandidatesOn] = useState(false);
    const [candidates, setCandidates] = useState<string[]>([]);
    const [candidateFrom, setCandidateFrom] = useState<string | null>(null);
    const [candidatesReady, setCandidatesReady] = useState(false);
    const [bestFirst, setBestFirst] = useState<string | null>(null);
    const [lastMove, setLastMove] = useState<{ from: string; to: string } | null>(null);
    const [hint, setHint] = useState<HintResponse | null>(null);
    const [mark, setMark] = useState<{ square: string; ok: boolean } | null>(null);
    const [result, setResult] = useState<PuzzleResult | null>(null);
    const [solution, setSolution] = useState<string | null>(null);
    const [profile, setProfile] = useState<PuzzleProfile | null>(null);
    const [run, setRun] = useState<TimedRun | null>(null);
    const [secondsLeft, setSecondsLeft] = useState(0);
    const [timedResult, setTimedResult] = useState<TimedResult | null>(null);
    const [error, setError] = useState<UiMessage | null>(null);
    const [target, setTarget] = useState<TrainingTarget | null>(null);
    const [personal, setPersonal] = useState<PersonalView | null>(null);
    // Review of a personal mistake on the board: the move from the game and the strong move (task B.3).
    const [personalReplay, setPersonalReplay] = useState<ReplayView | null>(null);
    const [personalAnswer, setPersonalAnswer] = useState<PersonalAnswer | null>(null);
    const [personalSummary, setPersonalSummary] = useState<PersonalSummary | null>(null);
    const [trainingKey, setTrainingKey] = useState(0);
    const [defenseKind, setDefenseKind] = useState<DefenseKind>('threat');
    const [drillKind, setDrillKind] = useState<DrillKind>('capture');
    const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
    const gameRef = useRef(new Chess());

    const later = (fn: () => void, ms: number) => {
        timers.current.push(setTimeout(fn, ms));
    };
    useEffect(() => () => timers.current.forEach(clearTimeout), []);

    // Free board after a puzzle (owner's decision 18.11): the review starts with the player's first move after the puzzle ends
    // and resets as soon as the next one starts.
    const explorer = usePositionExplorer();
    const explorerActive = explorer.active;
    const stopExplorer = explorer.stop;
    useEffect(() => {
        if (phase !== 'done' && explorerActive) stopExplorer();
    }, [phase, explorerActive, stopExplorer]);

    const refreshProfile = useCallback(() => {
        puzzlesApi.me().then(setProfile).catch(() => undefined);
    }, []);

    useEffect(() => {
        refreshProfile();
        fetchThemeRegistry().then(setRegistry).catch(() => undefined);
    }, [refreshProfile]);

    const apply = (uci: string) => {
        const move = gameRef.current.move(toMove(uci));
        setFen(gameRef.current.fen());
        setLastMove({from: move.from, to: move.to});
    };

    const present = useCallback((view: PuzzleView) => {
        timers.current.forEach(clearTimeout);
        timers.current = [];
        gameRef.current = new Chess(view.fen);
        setPuzzle(view);
        setFen(view.fen);
        setLastMove(null);
        setHint(null);
        setMark(null);
        setResult(null);
        setSolution(null);
        setCandidates([]);
        setCandidateFrom(null);
        setCandidatesReady(false);
        setBestFirst(null);
        setPhase('opponent');
        later(() => {
            apply(view.first_move);
            setStartFen(gameRef.current.fen());
            setPhase('solving');
        }, OPPONENT_DELAY_MS);
    }, []);

    const load = useCallback(async (nextMode: Mode = mode, nextTarget: TrainingTarget | null = target) => {
        setError(null);
        setPhase('loading');
        try {
            if (nextMode === 'personal') {
                setPuzzle(null);
                setPersonalAnswer(null);
                setPersonalReplay(null);
                setMark(null);
                setPersonalSummary(await puzzlesApi.personalSummary());
                let view: PersonalView | null = null;
                try {
                    view = await puzzlesApi.personalNext();
                } catch {
                    view = null;  // nothing to repeat now: the summary will say when the next one is
                }
                setPersonal(view);
                if (view) {
                    gameRef.current = new Chess(view.fen);
                    setFen(view.fen);
                    setLastMove(view.previous_move
                        ? {from: view.previous_move.slice(0, 2), to: view.previous_move.slice(2, 4)} : null);
                    setStartFen(view.fen);
                    setPhase('solving');
                } else {
                    setPhase('idle');
                }
            } else if (nextMode === 'themes') {
                if (nextTarget) present(await puzzlesApi.train(nextTarget));
                else setPhase('idle');
            } else if (nextMode === 'save') {
                present(await puzzlesApi.train(SAVE_TARGET));
            } else if (nextMode === 'timed') {
                const view = await puzzlesApi.timedNext();
                setRun(view.run);
                present(view);
            } else {
                present(nextMode === 'daily' ? await puzzlesApi.daily() : await puzzlesApi.next(theme));
            }
        } catch (err) {
            setError(errorMessage(err, 'common.networkError'));
            setPhase('idle');
        }
    }, [mode, theme, target, present]);

    const finishTimed = useCallback(async () => {
        try {
            setTimedResult(await puzzlesApi.timedFinish());
            refreshProfile();
        } catch (err) {
            setError(errorMessage(err, 'common.networkError'));
        }
        setRun(null);
        setPhase('idle');
    }, [refreshProfile]);

    // Run timer: shows the time, but the end is still fixed by the server.
    useEffect(() => {
        if (!run) return;
        setSecondsLeft(run.seconds_left);
        const interval = setInterval(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000);
        return () => clearInterval(interval);
    }, [run?.run_id]); // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        if (run && secondsLeft === 0 && phase !== 'loading') void finishTimed();
    }, [secondsLeft]); // eslint-disable-line react-hooks/exhaustive-deps

    const onResult = (res: PuzzleResult, line: string[] | null, fenBefore: string) => {
        setResult(res);
        setPhase('done');
        if (line?.length) setBestFirst((first) => first ?? line[0]);
        if (line) {
            // A wrong move is taken back, the solution is shown on the board move by move.
            later(() => {
                gameRef.current.undo();
                setFen(gameRef.current.fen());
                line.forEach((uci, i) => later(() => apply(uci), SOLUTION_STEP_MS * (i + 1)));
            }, SOLUTION_STEP_MS);
            setSolution(solutionSan(fenBefore, line));
        }
        if (res.run) {
            setRun(res.run);
            if (res.run.over) later(() => void finishTimed(), SOLUTION_STEP_MS);
            else later(() => void load('timed'), res.solved ? REPLY_DELAY_MS * 2 : SOLUTION_STEP_MS * 2);
        } else {
            refreshProfile();
            if (res.training) setTrainingKey((k) => k + 1);
        }
    };

    const onPersonalMove = async (uci: string) => {
        if (!personal) return;
        const fenBefore = gameRef.current.fen();
        apply(uci);
        setPhase('waiting');
        try {
            const answer = await puzzlesApi.personalAnswer(personal.id, uci);
            setMark({square: uci.slice(2, 4), ok: answer.correct});
            setPersonalAnswer(answer);
            setSolution(`${solutionSan(fenBefore, [answer.solution])}`);
            setPhase('done');
            if (!answer.correct) {
                later(() => {
                    gameRef.current.undo();
                    setFen(gameRef.current.fen());
                    later(() => apply(answer.solution), SOLUTION_STEP_MS);
                }, SOLUTION_STEP_MS);
            }
        } catch (err) {
            gameRef.current.undo();
            setFen(gameRef.current.fen());
            setError(errorMessage(err, 'common.networkError'));
            setPhase('solving');
        }
    };

    const onMove = async (uci: string) => {
        // The puzzle is solved (or the solution is shown): the board is free, the player's first move starts a review from the current position.
        if (phase === 'done') {
            if (explorer.active) explorer.play(uci);
            else explorer.start(fen, [uci]);
            return;
        }
        if (mode === 'personal' && phase === 'solving') {
            await onPersonalMove(uci);
            return;
        }
        if (!puzzle || phase !== 'solving') return;
        const fenBefore = gameRef.current.fen();
        const firstMove = fenBefore === startFen;
        apply(uci);
        setPhase('waiting');
        setHint(null);
        try {
            const answer = await puzzlesApi.move(puzzle.id, uci);
            setMark({square: uci.slice(2, 4), ok: answer.correct});
            if (firstMove && answer.correct) setBestFirst(uci);
            if (answer.done && answer.result) {
                onResult(answer.result, answer.correct ? null : answer.solution, fenBefore);
            } else if (answer.reply) {
                const reply = answer.reply;
                later(() => {
                    apply(reply);
                    setMark(null);
                    setPhase('solving');
                }, REPLY_DELAY_MS);
            }
        } catch (err) {
            gameRef.current.undo();
            setFen(gameRef.current.fen());
            setError(errorMessage(err, 'common.networkError'));
            setPhase('solving');
        }
    };

    const askHint = async () => {
        if (!puzzle) return;
        try {
            setHint(await puzzlesApi.hint(puzzle.id));
        } catch (err) {
            setError(errorMessage(err, 'common.networkError'));
        }
    };

    const giveUp = async () => {
        if (!puzzle) return;
        try {
            const body = await puzzlesApi.giveUp(puzzle.id);
            if (gameRef.current.fen() === startFen && body.solution.length) setBestFirst((first) => first ?? body.solution[0]);
            setResult(body.result);
            setSolution(solutionSan(gameRef.current.fen(), body.solution));
            setPhase('done');
            body.solution.forEach((uci, i) => later(() => apply(uci), SOLUTION_STEP_MS * (i + 1)));
            refreshProfile();
        } catch (err) {
            setError(errorMessage(err, 'common.networkError'));
        }
    };

    const startTimed = async (minutes: 3 | 5) => {
        setError(null);
        setTimedResult(null);
        try {
            setRun(await puzzlesApi.timedStart(minutes));
            setMode('timed');
            await load('timed');
        } catch (err) {
            setError(errorMessage(err, 'common.networkError'));
        }
    };

    const chooseMode = (next: Mode) => {
        setMode(next);
        setTimedResult(null);
        setTarget(null);
        setPersonal(null);
        if (next !== 'personal') setPersonalSummary(null);
        if (next !== 'timed' && next !== 'themes' && next !== 'defense' && next !== 'drills') void load(next);
        if (next === 'themes' || next === 'defense' || next === 'drills') setPhase('idle');
    };

    const startTraining = (next: TrainingTarget) => {
        // "What is threatened?" and "Don't blunder" are defence exercises (13.6), not database puzzles.
        const drill = next.theme ? DEFENSE_DRILL_THEMES[next.theme] : undefined;
        if (drill) {
            setDefenseKind(drill);
            setMode('defense');
            return;
        }
        setMode('themes');
        setTarget(next);
        void load('themes', next);
    };

    // Entry from the daily warm-up (task 22.2): straight to theme training or "your mistakes".
    const location = useLocation();
    const entry = location.state as { train?: TrainingTarget; mode?: Mode } | null;
    useEffect(() => {
        if (entry?.train) startTraining(entry.train);
        else if (entry?.mode && MODES.includes(entry.mode)) chooseMode(entry.mode);
    }, [location.key]); // eslint-disable-line react-hooks/exhaustive-deps

    const analyzePosition = (fen: string) => navigate('/', {state: {analyzeFen: fen}});
    const analyze = () => {
        if (startFen) analyzePosition(startFen);
    };

    const dueDays = (iso: string | null) => (iso
        ? Math.max(1, Math.round((new Date(iso).getTime() - Date.now()) / 86_400_000)) : 0);

    const turnText = puzzle ? t(puzzle.color === 'white' ? 'puzzles.yourMoveWhite' : 'puzzles.yourMoveBlack') : '';
    const showThemes = (mode !== 'timed' && !(target?.blind)) || phase === 'done';
    const training = result?.training ?? null;

    const header = (
        <>
            <h1 className="flex items-center gap-2 text-lg font-bold text-amber-400">
                <PuzzleIcon size={18}/> {t('puzzles.title')}
            </h1>
            {profile && (
                <p data-testid="puzzle-profile">
                    {t('puzzles.profile', {rating: profile.rating, games: profile.games, streak: profile.streak})}
                </p>
            )}
            {/* While mode cards are on the left, the tabs do not repeat them; defence and exercises have no cards. */}
            {(puzzle || personal || mode === 'defense' || mode === 'drills') && <PuzzleModePicker mode={mode} onChange={chooseMode}/>}
        </>
    );

    if (mode === 'drills') {
        return <GeneratedDrills key={drillKind} header={header} initialKind={drillKind} onAnalyze={analyzePosition}/>;
    }

    const candidatesAllowed = mode === 'rated' || mode === 'themes' || mode === 'daily';
    // Until candidates are marked, clicks on the board mark a move "from -> to" instead of making it.
    const marking = candidatesOn && candidatesAllowed && phase === 'solving' && !candidatesReady && fen === startFen;
    const markCandidate = (square: string) => {
        if (!candidateFrom) {
            setCandidateFrom(square);
            return;
        }
        const uci = `${candidateFrom}${square}`;
        setCandidateFrom(null);
        if (candidateFrom === square) return;
        setCandidates((list) => (list.includes(uci) ? list.filter((c) => c !== uci) : list.length >= 3 ? list : [...list, uci]));
    };

    const nextButton = (
        <button type="button" onClick={() => void load()} data-testid="puzzle-next"
                disabled={phase === 'loading' || phase === 'opponent'}
                className="self-start flex items-center gap-1 px-3 py-1.5 rounded bg-amber-700 hover:bg-amber-600 text-white font-bold disabled:opacity-40 cursor-pointer">
            <ArrowRight size={15}/> {t(puzzle ? 'puzzles.next' : 'puzzles.start')}
        </button>
    );
    // Modes where a puzzle is taken with the "Start" button; the others have their own start (a run, a path through techniques, a mistakes queue).
    const startsWithButton = mode === 'rated' || mode === 'daily' || mode === 'save';

    if (mode === 'defense') {
        return (
            <DefenseTrainer key={defenseKind} header={header} initialKind={defenseKind}
                            onDefensiveMove={() => startTraining({theme: 'defensive_move', blind: false})}
                            onAnalyze={analyzePosition}/>
        );
    }

    return (
        <div className="w-full max-w-6xl mx-auto p-3 sm:p-4 flex flex-col lg:flex-row gap-4" data-testid="puzzles-page">
            <div className="w-full lg:w-[min(70vh,640px)] shrink-0 flex flex-col gap-2">
                {!puzzle && !personal ? (
                    // Before the first puzzle, all modes are cards by group; the selected one is larger and has a "Start" button.
                    <div className="flex flex-col gap-4" data-testid="puzzle-mode-cards">
                        {MODE_GROUPS.map((group) => (
                            <Section key={group.id} title={t(`puzzles.modeGroups.${group.id}`)}>
                                <CardGrid cols={2}>
                                    {group.modes.map((m) => {
                                        const Icon = MODE_ICONS[m];
                                        const current = m === mode;
                                        return (
                                            <Card key={m} variant={current ? 'hero' : 'default'}
                                                  testId={`puzzle-mode-${m}`}
                                                  icon={<Icon size={current ? 24 : 20}/>}
                                                  title={t(`puzzles.modes.${m}`)} description={t(`puzzles.modeInfo.${m}`)}
                                                  onClick={current ? undefined : () => chooseMode(m)}
                                                  footer={current && startsWithButton ? nextButton : undefined}/>
                                        );
                                    })}
                                </CardGrid>
                            </Section>
                        ))}
                    </div>
                ) : <>
                <PuzzleBoard fen={personalReplay?.fen ?? explorer.fen ?? fen} orientation={personal?.color ?? puzzle?.color ?? 'white'}
                             interactive={phase === 'solving' || (phase === 'done' && !personalReplay && !run)}
                             lastMove={personalReplay ? personalReplay.lastMove : explorer.active ? explorer.lastMove : lastMove}
                             hint={personalReplay || explorer.active ? null : hint}
                             mark={personalReplay || explorer.active ? null : mark}
                             arrows={personalReplay?.arrows ?? (candidatesOn && candidatesAllowed
                                 ? candidates.map((c) => ({from: c.slice(0, 2), to: c.slice(2, 4), color: c === bestFirst ? 'green' as const : 'blue' as const}))
                                 : undefined)}
                             highlights={marking && candidateFrom ? [candidateFrom] : undefined}
                             onSquare={marking ? markCandidate : undefined}
                             onMove={(uci) => void onMove(uci)}/>
                <ExplorerControls explorer={explorer}/>
                </>}
                {candidatesOn && candidatesAllowed && puzzle && (
                    <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="candidates-panel">
                        {marking ? (
                            <>
                                <span>{t('puzzles.candidates.mark', {n: candidates.length})}</span>
                                <button type="button" disabled={candidates.length < 2} onClick={() => setCandidatesReady(true)}
                                        data-testid="candidates-ready"
                                        className="px-3 py-1 rounded bg-amber-700 text-white font-bold disabled:opacity-50">{t('puzzles.candidates.solve')}</button>
                            </>
                        ) : phase === 'done' && bestFirst ? (
                            <span className={candidates.includes(bestFirst) ? 'text-emerald-300' : 'text-amber-300'} data-testid="candidates-verdict">
                                {t(candidates.includes(bestFirst) ? 'puzzles.candidates.found' : 'puzzles.candidates.missed')}
                            </span>
                        ) : (
                            <span className="text-boxwood/80">{t('puzzles.candidates.marked', {n: candidates.length})}</span>
                        )}
                    </div>
                )}
                <div className="flex flex-wrap items-center gap-2 text-sm" role="status" data-testid="puzzle-status">
                    {phase === 'opponent' && <span className="text-boxwood/80">{t('puzzles.opponentMoving')}</span>}
                    {(phase === 'solving' || phase === 'waiting') && personal && (
                        <span className="font-bold text-amber-300">{t('puzzles.personal.task')}</span>
                    )}
                    {(phase === 'solving' || phase === 'waiting') && !personal && <span className="font-bold text-amber-300">{turnText}</span>}
                    {phase === 'done' && result && (
                        <span className={`font-bold ${result.solved ? 'text-emerald-400' : 'text-rose-400'}`}
                              data-testid="puzzle-outcome">
                            {t(result.solved ? 'puzzles.solved' : 'puzzles.failed')}
                            {!result.run && ` ${t('puzzles.delta', {delta: result.delta > 0 ? `+${result.delta}` : String(result.delta)})}`}
                        </span>
                    )}
                </div>
            </div>

            <aside className="flex-1 min-w-0 flex flex-col gap-3 text-sm text-boxwood-light">
                <section className="bg-acacia-dark p-3 rounded-md border border-amber-700/40 flex flex-col gap-2">
                    {header}

                    {candidatesAllowed && (
                        <label className="flex items-center gap-1.5 cursor-pointer" title={t('puzzles.candidates.hint')}>
                            <input type="checkbox" className="accent-amber-600" checked={candidatesOn} data-testid="candidates-toggle"
                                   onChange={(e) => setCandidatesOn(e.target.checked)}/>
                            {t('puzzles.candidates.toggle')}
                        </label>
                    )}
                    {mode === 'rated' && (
                        <label className="flex flex-col gap-1">
                            <span>{t('puzzles.theme')}</span>
                            <select value={theme ?? ''} data-testid="puzzle-theme"
                                    onChange={(e) => setTheme(e.target.value || null)}
                                    className="bg-black/40 border border-amber-900/50 rounded px-2 py-1">
                                <option value="">{t('puzzles.allThemes')}</option>
                                {registry?.sections.map((section) => (
                                    <optgroup key={section} label={t(`puzzles.sections.${section as ThemeSection}`)}>
                                        {registry.themes.filter((th) => th.section === section).map((th) => (
                                            <option key={th.code} value={th.code}>{themeText(th.code, 'name', t)}</option>
                                        ))}
                                    </optgroup>
                                ))}
                            </select>
                        </label>
                    )}

                    {mode === 'timed' && !run && (
                        <div className="flex flex-col gap-1.5" data-testid="puzzle-timed-setup">
                            <p className="text-boxwood/80">{t('puzzles.timedRules')}</p>
                            <div className="flex gap-2">
                                {([3, 5] as const).map((minutes) => (
                                    <button key={minutes} type="button" data-testid={`puzzle-timed-${minutes}`}
                                            onClick={() => void startTimed(minutes)}
                                            className="flex-1 py-1.5 rounded bg-amber-800 hover:bg-amber-700 text-white font-bold cursor-pointer">
                                        {t('puzzles.timedStart', {minutes})}
                                        {profile && <span className="block text-[10px] font-normal">{t('puzzles.record', {score: profile.best[String(minutes) as '3' | '5']})}</span>}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}
                    {mode === 'timed' && !run && <TimedLeaders refreshKey={timedResult}/>}
                    {run && (
                        <div className="flex items-center justify-between font-mono" data-testid="puzzle-run">
                            <span>{t('puzzles.timeLeft', {time: `${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, '0')}`})}</span>
                            <span>{t('puzzles.score', {score: run.solved})}</span>
                            <span aria-label={t('puzzles.mistakes', {count: run.mistakes})}>
                                {'✗'.repeat(run.mistakes)}{'·'.repeat(Math.max(0, 3 - run.mistakes))}
                            </span>
                        </div>
                    )}
                    {timedResult && (
                        <p className="font-bold text-amber-200" data-testid="puzzle-timed-result">
                            {t('puzzles.timedOver', {score: timedResult.score, best: timedResult.best})}
                            {timedResult.new_record && ` ${t('puzzles.newRecord')}`}
                        </p>
                    )}

                    {mode === 'save' && (
                        <p className="text-amber-200 leading-snug" data-testid="save-intro">{t('puzzles.save.intro')}</p>
                    )}

                    {mode === 'themes' && target && (
                        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="training-target">
                            <span className="font-bold text-amber-200">
                                {target.theme
                                    ? themeText(target.theme, 'name', t)
                                    : t('puzzles.training.mixedOf', {section: t(`puzzles.sections.${target.section as ThemeSection}`)})}
                                {target.blind && ` · ${t('puzzles.training.blind')}`}
                            </span>
                            <button type="button" onClick={() => {
                                setTarget(null);
                                setPhase('idle');
                                setPuzzle(null);
                            }} data-testid="training-back"
                                    className="text-xs px-2 py-0.5 rounded bg-black/40 border border-amber-900/50 hover:border-amber-500 cursor-pointer">
                                {t('puzzles.training.back')}
                            </button>
                        </div>
                    )}
                    {training && (
                        <p className="text-amber-200" data-testid="training-progress">
                            {training.mastered && training.advanced
                                ? t('puzzles.training.justMastered')
                                : training.advanced
                                    ? t('puzzles.training.advanced', {stage: training.stage})
                                    : t('puzzles.training.progress', {
                                        stage: training.stage,
                                        clean: training.recent.split('').filter((c) => c === '1').length,
                                        window: training.window, pass: training.pass,
                                    })}
                        </p>
                    )}

                    {mode === 'personal' && personalSummary && (
                        <div className="flex flex-col gap-1.5" data-testid="personal-panel">
                            <p data-testid="personal-summary">
                                {t('puzzles.personal.summary', {
                                    due: personalSummary.due, active: personalSummary.active,
                                    mastered: personalSummary.mastered,
                                })}
                            </p>
                            {!personal && phase === 'idle' && (
                                <p className="text-amber-200" data-testid="personal-empty">
                                    {personalSummary.active === 0
                                        ? t('puzzles.personal.none')
                                        : t('puzzles.personal.allDone', {days: dueDays(personalSummary.next_due_at)})}
                                </p>
                            )}
                            {!personal && phase === 'idle' && (
                                <p className="text-sm text-boxwood/85" data-testid="personal-import-hint">
                                    {t('puzzles.personal.importHint')}{' '}
                                    <Link to="/import" className="underline text-amber-300 hover:text-amber-200">
                                        {t('puzzles.personal.importLink')}
                                    </Link>
                                </p>
                            )}
                            {personalAnswer && (
                                <p className={personalAnswer.correct ? 'text-emerald-300' : 'text-rose-300'}
                                   data-testid="personal-result">
                                    {t(personalAnswer.correct ? 'puzzles.personal.right' : 'puzzles.personal.wrong')}
                                    {' '}
                                    {personalAnswer.done
                                        ? t('puzzles.personal.mastered')
                                        : t('puzzles.personal.again', {days: dueDays(personalAnswer.next_due_at)})}
                                </p>
                            )}
                            {personal?.opponent && (
                                <p className="text-xs text-boxwood/80" data-testid="personal-from">
                                    {t('puzzles.personal.from', {
                                        opponent: personal.opponent_is_bot
                                            ? botShortName(personal.opponent, t) : personal.opponent,
                                        date: personal.played_at
                                            ? format(parseISO(personal.played_at), 'd MMM yyyy', {locale: dateLocale}) : '',
                                    })}
                                </p>
                            )}
                            {personalAnswer && personal && (
                                <SolutionReplay key={personal.id} startFen={personal.fen} onShow={setPersonalReplay}
                                                onAnalyze={analyzePosition} lines={[
                                    ...(personalAnswer.played !== personalAnswer.solution ? [{
                                        id: 'played', moves: [personalAnswer.played], color: 'red' as const,
                                        label: t('puzzles.review.refutation', {move: sanMoves(personal.fen, [personalAnswer.played])[0]}),
                                    }] : []),
                                    {
                                        id: 'best', moves: [personalAnswer.solution], color: 'green' as const,
                                        label: t('puzzles.review.good', {move: sanMoves(personal.fen, [personalAnswer.solution])[0]}),
                                    },
                                ]}/>
                            )}
                            {personalAnswer && personal && (
                                <p className="text-xs text-boxwood/80" data-testid="personal-played">
                                    {t('puzzles.personal.inGame', {
                                        move: solutionSan(personal.fen, [personalAnswer.played]),
                                        best: solution ?? '',
                                    })}
                                </p>
                            )}
                            <div className="flex flex-wrap gap-2">
                                {phase === 'done' && (
                                    <button type="button" onClick={() => void load('personal')} data-testid="personal-next"
                                            className="flex items-center gap-1 px-3 py-1.5 rounded bg-amber-800 hover:bg-amber-700 text-white font-bold cursor-pointer">
                                        <ArrowRight size={15}/> {t('puzzles.next')}
                                    </button>
                                )}
                                {personal && (
                                    <button type="button" onClick={() => navigate(personal.imported_game_id
                                        ? `/import/game/${personal.imported_game_id}` : `/game/${personal.game_id}`)}
                                            data-testid="personal-open-game"
                                            className="px-3 py-1.5 rounded bg-black/40 border border-amber-900/50 hover:border-amber-500 cursor-pointer">
                                        {t('puzzles.personal.openGame')}
                                    </button>
                                )}
                            </div>
                        </div>
                    )}

                    {mode !== 'timed' && mode !== 'personal' && (mode !== 'themes' || target) && (
                        <div className="flex flex-wrap gap-2">
                            {puzzle && nextButton}
                            {phase === 'solving' && (
                                <>
                                    <button type="button" onClick={() => void askHint()} data-testid="puzzle-hint"
                                            disabled={(hint?.hints_used ?? 0) >= 2}
                                            className="flex items-center gap-1 px-3 py-1.5 rounded bg-black/40 border border-amber-900/50 hover:border-amber-500 disabled:opacity-40 cursor-pointer">
                                        <Lightbulb size={15}/> {t('puzzles.hint')}
                                    </button>
                                    <button type="button" onClick={() => void giveUp()} data-testid="puzzle-give-up"
                                            className="flex items-center gap-1 px-3 py-1.5 rounded bg-black/40 border border-amber-900/50 hover:border-amber-500 cursor-pointer">
                                        <Flag size={15}/> {t('puzzles.giveUp')}
                                    </button>
                                </>
                            )}
                            {phase === 'done' && startFen && (
                                <button type="button" onClick={analyze} data-testid="puzzle-analyze"
                                        className="flex items-center gap-1 px-3 py-1.5 rounded bg-emerald-900/80 hover:bg-emerald-800 text-emerald-100 font-bold cursor-pointer">
                                    <GraduationCap size={15}/> {t('puzzles.analyze')}
                                </button>
                            )}
                        </div>
                    )}
                    {hint && <p className="text-sky-300" data-testid="puzzle-hint-text">{t(hint.to ? 'puzzles.hintMove' : 'puzzles.hintPiece')}</p>}
                    {error && <p className="text-rose-300" role="alert">{renderUiMessage(error, t)}</p>}
                </section>

                {mode === 'themes' && !target && (
                    <section className="bg-acacia-dark p-3 rounded-md border border-amber-700/40">
                        <TrainingPanel onTrain={startTraining} refreshKey={trainingKey}
                                       onDrill={(kind) => {
                                           setDrillKind(kind);
                                           setMode('drills');
                                       }}/>
                    </section>
                )}

                {puzzle && (
                    <section className="bg-acacia-dark p-3 rounded-md border border-amber-700/40 flex flex-col gap-1.5"
                             data-testid="puzzle-info">
                        <p>
                            {t('puzzles.puzzleRating', {rating: puzzle.rating})}
                            {puzzle.daily && ` · ${t('puzzles.dailyBadge')}`}
                            {puzzle.stage ? ` · ${t('puzzles.training.stageBadge', {stage: puzzle.stage})}` : ''}
                        </p>
                        {showThemes && puzzle.themes.length > 0 && (
                            <div className="flex flex-wrap gap-1" data-testid="puzzle-themes">
                                {puzzle.themes.map((code) => (
                                    <span key={code} title={themeText(code, 'short', t)}
                                          className="px-1.5 py-0.5 rounded bg-black/40 border border-amber-900/50 text-xs">
                                        {themeText(code, 'name', t)}
                                    </span>
                                ))}
                            </div>
                        )}
                        {solution && (
                            <p className="text-xs text-boxwood/80" data-testid="puzzle-solution">
                                {t('puzzles.solution', {moves: solution})}
                            </p>
                        )}
                    </section>
                )}

                {profile && profile.history.length > 0 && (
                    <section className="bg-acacia-dark p-3 rounded-md border border-amber-700/40 flex flex-col gap-1.5"
                             data-testid="puzzle-history">
                        <h2 className="font-bold text-amber-400">{t('puzzles.history')}</h2>
                        <RatingChart history={profile.history}/>
                        <ul className="grid grid-cols-2 sm:grid-cols-3 gap-1 text-xs font-mono">
                            {profile.history.slice(0, 12).map((h, i) => (
                                <li key={`${h.puzzle_id}-${i}`} className={h.solved ? 'text-emerald-400' : 'text-rose-400'}>
                                    {h.solved ? '✓' : '✗'} {h.puzzle_rating} → {h.rating_after}
                                </li>
                            ))}
                        </ul>
                    </section>
                )}
            </aside>
        </div>
    );
}
