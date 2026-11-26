// --- FILE: frontend/src/components/trainers/BlindGames.tsx ---
// Blindfold puzzles and "Where is the piece?" (task 19.6): BLIND_ROUNDS tasks per attempt. The position is shown until the player
// presses "Memorised"; then moves are announced one by one, and the answer is given on an empty board (squares and coordinates visible).
// Data: classic games (content/classics) and pure rules trainers/blindPuzzles.ts; the answer is scored by scoreStop. Launched from TrainersPage.tsx.

import {useEffect, useMemo, useState} from 'react';
import {useI18n} from '../../i18n';
import {PuzzleBoard} from '../puzzles/PuzzleBoard';
import {CoordBoard} from './CoordinateGames';
import {scoreStop} from '../../content/classics';
import {blindTask, whereQuestion} from '../../trainers/blindPuzzles';
import {useClassics} from './trainerGame';
import type {TrainerGameProps} from './trainerGame';

/** Tasks in one attempt. */
export const BLIND_ROUNDS = 5;
/** Pause between announced moves (ms): time to hold the position in one's head. */
const MOVE_STEP_MS = 1400;
/** An answer below this score (out of 100) counts as a mistake. */
const PASS_SCORE = 80;
/** chess.js piece letter -> piece name key in the message catalogue. */
const PIECE_NAMES = {k: 'king', q: 'queen', r: 'rook', b: 'bishop', n: 'knight', p: 'pawn'} as const;

/**
 * Phases: look (position in view) -> moves (moves one by one, board hidden) -> answer (a move or a square on an empty board) -> review.
 * An answer below PASS_SCORE points counts as a mistake.
 */
export function BlindGame({mode, level, seed, onFinish}: TrainerGameProps & { mode: 'move' | 'where' }) {
    const {t} = useI18n();
    const games = useClassics();
    const [round, setRound] = useState(0);
    const [phase, setPhase] = useState<'look' | 'moves' | 'answer' | 'review'>('look');
    const [shown, setShown] = useState(0);
    const [from, setFrom] = useState<string | null>(null);
    const [verdict, setVerdict] = useState<{ score: number; reply: string } | null>(null);
    const [total, setTotal] = useState({score: 0, mistakes: 0});

    const task = useMemo(() => (games ? blindTask(games, level, seed, round) : null), [games, level, seed, round]);
    const question = useMemo(() => (task && mode === 'where' ? whereQuestion(task, seed + round) : null), [task, mode, seed, round]);

    useEffect(() => {
        if (phase !== 'moves' || !task) return;
        if (shown >= task.moves.length) {
            setPhase('answer');
            return;
        }
        const id = window.setTimeout(() => setShown((n) => n + 1), MOVE_STEP_MS);
        return () => window.clearTimeout(id);
    }, [phase, shown, task]);

    if (!games) return <p className="text-sm text-boxwood/70">{t('trainers.memory.loading')}</p>;
    if (!task) return <p className="text-sm text-rose-300">{t('trainers.memory.noPositions')}</p>;

    const judge = (score: number, reply: string) => {
        setVerdict({score, reply});
        setTotal((s) => ({score: s.score + score, mistakes: s.mistakes + (score < PASS_SCORE ? 1 : 0)}));
        setPhase('review');
    };
    const onSquare = (square: string) => {
        if (phase !== 'answer') return;
        if (mode === 'where') {
            judge(square === question!.square ? 100 : 0, square);
            return;
        }
        if (!from) {
            setFrom(square);
            return;
        }
        if (from === square) {
            setFrom(null);
            return;
        }
        const uci = `${from}${square}`;
        const promotion = task.stop.move.length === 5 && task.stop.move.startsWith(uci) ? task.stop.move[4] : '';
        judge(scoreStop(task.stop, uci + promotion).score, uci + promotion);
    };
    const next = () => {
        if (round + 1 >= BLIND_ROUNDS) {
            onFinish(total.score, total.mistakes);
            return;
        }
        setRound((r) => r + 1);
        setPhase('look');
        setShown(0);
        setFrom(null);
        setVerdict(null);
    };
    const best = task.stop.move;
    const options = {side: task.side, coordinates: true, seconds: 30 as const};

    return (
        <div className="flex flex-col gap-3" data-testid={`blind-game-${mode}`}>
            <span className="font-bold text-amber-200">{t('trainers.memory.round', {n: round + 1, total: BLIND_ROUNDS})}</span>
            {phase === 'look' && (
                <>
                    <div className="w-full max-w-[420px]">
                        <PuzzleBoard fen={task.startFen} orientation={task.side} interactive={false} onMove={() => undefined} sound={false}/>
                    </div>
                    <p className="text-sm">{t('trainers.blind.look', {n: task.moves.length})}</p>
                    <button type="button" onClick={() => setPhase('moves')} data-testid="blind-ready"
                            className="self-start px-4 py-2 rounded bg-amber-700 text-white font-bold">{t('trainers.blind.ready')}</button>
                </>
            )}
            {(phase === 'moves' || phase === 'answer') && (
                <ol className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-lg" data-testid="blind-moves">
                    {task.moves.slice(0, shown).map((move, i) => <li key={i} className={i === shown - 1 ? 'text-amber-200 font-bold' : ''}>{move}</li>)}
                </ol>
            )}
            {phase === 'answer' && (
                <>
                    <p className="font-bold text-amber-200" data-testid="blind-question">
                        {mode === 'move'
                            ? t(task.side === 'white' ? 'trainers.blind.moveWhite' : 'trainers.blind.moveBlack')
                            : t('trainers.blind.where', {
                                piece: t(`trainers.blind.pieces.${question!.color === 'w' ? 'white' : 'black'}.${PIECE_NAMES[question!.type]}`),
                            })}
                    </p>
                    <CoordBoard options={options} highlight={from} onSquare={onSquare}/>
                </>
            )}
            {phase === 'review' && verdict && (
                <div className="flex flex-col gap-2" data-testid="blind-review">
                    <div className="w-full max-w-[420px]">
                        <PuzzleBoard fen={task.finalFen} orientation={task.side} interactive={false} onMove={() => undefined} sound={false}
                                     arrows={mode === 'move' ? [{from: best.slice(0, 2), to: best.slice(2, 4), color: 'green'}] : []}
                                     highlights={mode === 'where' ? [question!.square] : []}/>
                    </div>
                    <p className="text-lg">
                        <b className={verdict.score >= PASS_SCORE ? 'text-emerald-300' : 'text-rose-300'} data-testid="blind-score">{verdict.score}</b>{' '}
                        {mode === 'move'
                            ? t('trainers.blind.moveVerdict', {yours: verdict.reply, best})
                            : t('trainers.blind.whereVerdict', {square: question!.square})}
                    </p>
                    <p className="text-xs text-boxwood/70">{t('trainers.memory.gameLine', {white: task.game.white, black: task.game.black, year: task.game.year ?? ''})}</p>
                    <button type="button" onClick={next} data-testid="blind-next" className="self-start px-4 py-2 rounded bg-amber-700 text-white font-bold">
                        {t(round + 1 >= BLIND_ROUNDS ? 'trainers.memory.finish' : 'trainers.memory.next')}
                    </button>
                </div>
            )}
        </div>
    );
}
