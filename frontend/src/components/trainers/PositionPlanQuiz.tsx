// --- FILE: frontend/src/components/trainers/PositionPlanQuiz.tsx ---
// "Plan in this position" (task 27.9): a position from a master game and three concrete plans ("Break in the centre: d5",
// "Reroute a knight: Nf1"); one is the plan the master played. After the answer: the engine evaluation of every option's first
// move (prepared in advance, no engine here), the game's next moves, and a free board where the game can be stepped through
// or the position played out (usePositionExplorer).
// Data: frontend/src/trainers/positionPlans.ts over content/positionPlans.json (scripts/dev/build_position_plans.py);
// category names - positionPlans.* in the catalogues. Launched from TrainersPage.tsx (trainer position_plan); 10 points per answer.

import {useMemo, useState} from 'react';
import {useI18n} from '../../i18n';
import {PuzzleBoard} from '../puzzles/PuzzleBoard';
import {ExplorerControls, usePositionExplorer} from '../puzzles/usePositionExplorer';
import {sanMoves, solutionSan} from '../puzzles/puzzleNotation';
import {planAttempt} from '../../trainers/positionPlans';
import type {PlanOption} from '../../trainers/positionPlans';

/** Points for a right answer (as in the other quiz trainers). */
const POINTS = 10;

/** An evaluation in pawns with a sign: 37 -> "+0.4". */
const pawns = (cp: number) => `${cp > 0 ? '+' : ''}${(cp / 100).toFixed(1)}`;

/** Game props: seed of the attempt and onFinish(score, mistakes). */
interface Props {
    seed: number;
    onFinish: (score: number, mistakes: number) => void;
}

/** An attempt of PLAN_ROUNDS questions over the prepared set. */
export function PositionPlanQuiz({seed, onFinish}: Props) {
    const {t} = useI18n();
    const questions = useMemo(() => planAttempt(seed), [seed]);
    const [index, setIndex] = useState(0);
    const [picked, setPicked] = useState<number | null>(null);
    const [score, setScore] = useState({correct: 0, wrong: 0});
    const explorer = usePositionExplorer();
    const shown = questions[index];
    if (!shown) return <p className="text-sm text-rose-300">{t('trainers.memory.noPositions')}</p>;
    const {question, options, answer} = shown;
    const white = question.fen.split(' ')[1] === 'w';
    const label = (option: PlanOption) => t('trainers.positionPlan.option', {
        plan: t(`positionPlans.${option.plan}`), move: sanMoves(question.fen, [option.move])[0],
    });

    const choose = (i: number) => {
        if (picked !== null) return;
        setPicked(i);
        setScore((s) => (i === answer ? {...s, correct: s.correct + 1} : {...s, wrong: s.wrong + 1}));
    };
    const next = () => {
        if (index + 1 >= questions.length) {
            onFinish(score.correct * POINTS, score.wrong);
            return;
        }
        setIndex((i) => i + 1);
        setPicked(null);
        explorer.stop();
    };
    // Steps through the game: the board shows the position after one more ply of the stored continuation.
    const gameStep = () => {
        const plies = explorer.active ? explorer.plies + 1 : 1;
        explorer.start(question.fen, question.continuation.slice(0, Math.min(plies, question.continuation.length)));
    };
    const game = t(question.year ? 'trainers.positionPlan.game' : 'trainers.positionPlan.gameNoYear', {
        white: question.white, black: question.black, year: question.year ?? '',
    });

    return (
        <div className="flex flex-col gap-3" data-testid="position-plan-quiz">
            <div className="flex flex-wrap items-baseline gap-3">
                <span className="font-bold text-amber-200">{t('trainers.calc.question', {n: index + 1, total: questions.length})}</span>
                <span className="text-sm" data-testid="quiz-score">{t('trainers.coord.score', {score: score.correct, mistakes: score.wrong})}</span>
            </div>
            <p className="text-lg">{t(white ? 'trainers.positionPlan.promptWhite' : 'trainers.positionPlan.promptBlack')}</p>
            <div className="w-full max-w-[420px]">
                <PuzzleBoard fen={explorer.fen ?? question.fen} orientation={white ? 'white' : 'black'} interactive={picked !== null}
                             sound={false} lastMove={explorer.lastMove}
                             onMove={(uci) => {
                                 if (explorer.active) explorer.play(uci);
                                 else explorer.start(question.fen, [uci]);
                             }}/>
                <ExplorerControls explorer={explorer}/>
            </div>
            <div className="grid gap-2">
                {options.map((option, i) => {
                    const tone = picked === null ? 'bg-black/40 border-amber-800/60 hover:border-amber-400'
                        : i === answer ? 'bg-emerald-800 border-emerald-400' : i === picked ? 'bg-rose-900 border-rose-500' : 'bg-black/30 border-transparent opacity-60';
                    return (
                        <button key={option.move} type="button" onClick={() => choose(i)} data-testid={`plan-option-${i}`}
                                className={`px-3 py-2 rounded-lg border text-left text-sm ${tone}`}>
                            {label(option)}
                            {picked !== null && <span className="ml-2 text-boxwood/80" data-testid={`plan-score-${i}`}>{pawns(option.score)}</span>}
                        </button>
                    );
                })}
            </div>
            {picked !== null && (
                <div className="flex flex-col gap-2 text-sm" data-testid="plan-verdict">
                    <p className={picked === answer ? 'text-emerald-300' : 'text-rose-300'}>
                        {t(picked === answer ? 'trainers.positionPlan.right' : 'trainers.positionPlan.wrong', {plan: label(options[answer])})}
                    </p>
                    <p className="text-boxwood/80">{t('trainers.positionPlan.scores')}</p>
                    <p className="text-amber-200" data-testid="plan-game">{game} {solutionSan(question.fen, question.continuation)}</p>
                    <div className="flex flex-wrap items-center gap-3">
                        <button type="button" onClick={gameStep} data-testid="plan-game-step"
                                className="px-3 py-1 rounded border border-amber-700 text-amber-200">{t('trainers.positionPlan.gameStep')}</button>
                        <button type="button" onClick={next} data-testid="quiz-next" className="px-4 py-2 rounded bg-amber-700 text-white font-bold">
                            {t(index + 1 >= questions.length ? 'trainers.memory.finish' : 'trainers.memory.next')}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
