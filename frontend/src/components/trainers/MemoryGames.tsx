// --- FILE: frontend/src/components/trainers/MemoryGames.tsx ---
// Memory trainers (task 19.3).
// * RestoreGame - "Restore the position": MEMORY_ROUNDS positions; a timed display by level, placement from memory (a palette, as in the
//   position editor), review: your placement and the original with the mistakes highlighted. Score - the sum of percentages.
// * RecallGame - "Remember the game": the game moves are played back, then they must be repeated; three misses on a move - the move
//   is shown itself. Score - 10 for each move on the first try.
// Data: classic games (content/classics) and endgame positions (content/endgames.json); rules - trainers/memory.ts. Launched from TrainersPage.tsx.

import {useEffect, useMemo, useRef, useState} from 'react';
import {Chess} from 'chess.js';
import {Eraser} from 'lucide-react';
import {useI18n} from '../../i18n';
import {PuzzleBoard} from '../puzzles/PuzzleBoard';
import {fenOf} from '../tools/PositionEditor';
import endgames from '../../content/endgames.json';
import {memoryLevel, pickGame, pickPosition, placementOfFen, positionPool, recallPlies, scorePlacement} from '../../trainers/memory';
import type {Placement, PlacementScore} from '../../trainers/memory';
import {useClassics} from './trainerGame';
import type {TrainerGameProps} from './trainerGame';
import {ReservedSlot} from '../ReservedSlot';

/** Positions in one "Restore the position" attempt. */
export const MEMORY_ROUNDS = 3;
/** Pause between shown game moves (ms). */
const RECALL_STEP_MS = 900;
/** Palette brushes: uppercase - white pieces, lowercase - black. */
const PIECES = ['K', 'Q', 'R', 'B', 'N', 'P', 'k', 'q', 'r', 'b', 'n', 'p'] as const;
/** Piece glyphs on the palette buttons. */
const GLYPHS: Record<string, string> = {K: '♔', Q: '♕', R: '♖', B: '♗', N: '♘', P: '♙', k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟'};

/** Countdown of seconds while active; at zero calls onDone (the fresh callback is taken from a ref so the interval is not recreated). */
function useCountdown(seconds: number, active: boolean, onDone: () => void): number {
    const [left, setLeft] = useState(seconds);
    const done = useRef(onDone);
    done.current = onDone;
    useEffect(() => {
        if (!active) return;
        setLeft(seconds);
        const started = Date.now();
        const id = window.setInterval(() => {
            const remaining = Math.max(0, seconds - Math.floor((Date.now() - started) / 1000));
            setLeft(remaining);
            if (remaining === 0) {
                window.clearInterval(id);
                done.current();
            }
        }, 200);
        return () => window.clearInterval(id);
    }, [seconds, active]);
    return left;
}

/** Round phases: show (a timed display by level) -> place (placement from memory) -> review. Round score - the percentage of correct squares. */
export function RestoreGame({level, seed, onFinish}: TrainerGameProps) {
    const {t} = useI18n();
    const games = useClassics();
    const pool = useMemo(() => (games ? positionPool(games, endgames as { fen: string }[]) : null), [games]);
    const [round, setRound] = useState(0);
    const [phase, setPhase] = useState<'show' | 'place' | 'review'>('show');
    const [answer, setAnswer] = useState<Placement>({});
    const [brush, setBrush] = useState<string>('P');
    const [result, setResult] = useState<PlacementScore | null>(null);
    const totals = useRef({score: 0, mistakes: 0});
    const target = useMemo(() => (pool ? pickPosition(pool, level, seed + round * 101) : null), [pool, level, seed, round]);
    const {seconds} = memoryLevel(level);
    const left = useCountdown(seconds, phase === 'show' && Boolean(target), () => setPhase('place'));

    if (!pool) return <p className="text-sm text-boxwood/70">{t('trainers.memory.loading')}</p>;
    if (!target) return <p className="text-sm text-rose-300">{t('trainers.memory.noPositions')}</p>;
    const targetPlacement = placementOfFen(target);

    const check = () => {
        const scored = scorePlacement(targetPlacement, answer);
        totals.current = {score: totals.current.score + scored.score, mistakes: totals.current.mistakes + scored.wrong.length};
        setResult(scored);
        setPhase('review');
    };
    const next = () => {
        if (round + 1 >= MEMORY_ROUNDS) {
            onFinish(totals.current.score, totals.current.mistakes);
            return;
        }
        setRound((r) => r + 1);
        setAnswer({});
        setResult(null);
        setPhase('show');
    };
    const place = (square: string) => setAnswer((current) => {
        const nextPlacement = {...current};
        if (brush === 'x' || nextPlacement[square] === brush) delete nextPlacement[square];
        else nextPlacement[square] = brush;
        return nextPlacement;
    });

    return (
        <div className="flex flex-col gap-3" data-testid="restore-game">
            <ReservedSlot lines={2.5} className="flex flex-wrap items-baseline gap-4">
                <span className="font-bold text-amber-200">{t('trainers.memory.round', {n: round + 1, total: MEMORY_ROUNDS})}</span>
                {phase === 'show' && <span className="font-mono text-lg" data-testid="memory-left">{t('trainers.memory.remember', {seconds: left})}</span>}
                {phase === 'place' && <span>{t('trainers.memory.placeHint', {n: Object.keys(targetPlacement).length})}</span>}
            </ReservedSlot>
            {phase === 'show' && (
                <div className="w-full max-w-[460px]">
                    <PuzzleBoard fen={target} orientation="white" interactive={false} onMove={() => undefined} sound={false}/>
                </div>
            )}
            {phase === 'place' && (
                <div className="w-full max-w-[460px] flex flex-col gap-2">
                    <PuzzleBoard fen={fenOf(answer, 'w', '-')} orientation="white" interactive onMove={() => undefined} onSquare={place} sound={false}/>
                    <div className="grid grid-cols-7 gap-1" role="radiogroup" aria-label={t('tools.editor.palette')}>
                        {PIECES.map((p) => (
                            <button key={p} type="button" role="radio" aria-checked={brush === p} onClick={() => setBrush(p)} data-testid={`brush-${p}`}
                                    aria-label={p}
                                    className={`text-2xl leading-none py-1 rounded border ${brush === p ? 'bg-amber-700 border-amber-300' : 'bg-black/30 border-amber-900/50'}`}>
                                {GLYPHS[p]}
                            </button>
                        ))}
                        <button type="button" role="radio" aria-checked={brush === 'x'} onClick={() => setBrush('x')} data-testid="brush-erase"
                                aria-label={t('tools.editor.erase')}
                                className={`flex items-center justify-center rounded border ${brush === 'x' ? 'bg-amber-700 border-amber-300' : 'bg-black/30 border-amber-900/50'}`}>
                            <Eraser size={18}/>
                        </button>
                    </div>
                    <button type="button" onClick={check} data-testid="memory-check" className="self-start px-4 py-2 rounded bg-amber-700 text-white font-bold">
                        {t('trainers.memory.check')}
                    </button>
                </div>
            )}
            {phase === 'review' && result && (
                <div className="flex flex-col gap-3" data-testid="memory-review">
                    <div className="flex flex-col sm:flex-row gap-4">
                        <figure className="flex-1 max-w-[360px]">
                            <figcaption className="text-sm text-boxwood/75 mb-1">{t('trainers.memory.yours')}</figcaption>
                            <PuzzleBoard fen={fenOf(answer, 'w', '-')} orientation="white" interactive={false} onMove={() => undefined}
                                         highlights={result.wrong} sound={false}/>
                        </figure>
                        <figure className="flex-1 max-w-[360px]">
                            <figcaption className="text-sm text-boxwood/75 mb-1">{t('trainers.memory.original')}</figcaption>
                            <PuzzleBoard fen={target} orientation="white" interactive={false} onMove={() => undefined} highlights={result.wrong} sound={false}/>
                        </figure>
                    </div>
                    <p className="text-lg">
                        <b className="text-amber-300" data-testid="memory-round-score">{result.score}%</b>{' '}
                        {t('trainers.memory.reviewLine', {correct: result.correct.length, wrong: result.wrong.length})}
                    </p>
                    <button type="button" onClick={next} data-testid="memory-next" className="self-start px-4 py-2 rounded bg-amber-700 text-white font-bold">
                        {t(round + 1 >= MEMORY_ROUNDS ? 'trainers.memory.finish' : 'trainers.memory.next')}
                    </button>
                </div>
            )}
        </div>
    );
}

/** Phases: watch (the start of the game is played back move by move) -> play (repeat the moves); the player sees only the position before their move. */
export function RecallGame({level, seed, onFinish}: TrainerGameProps) {
    const {t} = useI18n();
    const games = useClassics();
    const game = useMemo(() => (games ? pickGame(games, level, seed) : null), [games, level, seed]);
    const plies = recallPlies(level);
    const moves = useMemo(() => game?.moves.slice(0, plies) ?? [], [game, plies]);
    const [phase, setPhase] = useState<'watch' | 'play'>('watch');
    const [shown, setShown] = useState(0);
    const [played, setPlayed] = useState(0);
    const [misses, setMisses] = useState(0);
    const [score, setScore] = useState(0);
    const [mistakes, setMistakes] = useState(0);
    const [mark, setMark] = useState<{ square: string; ok: boolean } | null>(null);

    useEffect(() => {
        if (phase !== 'watch' || moves.length === 0) return;
        if (shown >= moves.length) {
            const id = window.setTimeout(() => setPhase('play'), RECALL_STEP_MS);
            return () => window.clearTimeout(id);
        }
        const id = window.setTimeout(() => setShown((n) => n + 1), RECALL_STEP_MS);
        return () => window.clearTimeout(id);
    }, [phase, shown, moves.length]);

    const fenAfter = (count: number) => {
        const board = new Chess();
        for (const uci of moves.slice(0, count)) board.move({from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4]});
        return board.fen();
    };

    if (!games) return <p className="text-sm text-boxwood/70">{t('trainers.memory.loading')}</p>;
    if (!game) return <p className="text-sm text-rose-300">{t('trainers.memory.noPositions')}</p>;

    const advance = (firstTry: boolean, nextMistakes: number) => {
        const nextScore = score + (firstTry ? 10 : 0);
        setScore(nextScore);
        setMisses(0);
        const count = played + 1;
        setPlayed(count);
        if (count >= moves.length) onFinish(nextScore, nextMistakes);
    };

    const onMove = (uci: string) => {
        const expected = moves[played];
        const same = uci.slice(0, 4) === expected.slice(0, 4) && (uci[4] ?? 'q') === (expected[4] ?? 'q');
        if (same) {
            setMark({square: expected.slice(2, 4), ok: true});
            advance(misses === 0, mistakes);
            return;
        }
        const nextMistakes = mistakes + 1;
        setMistakes(nextMistakes);
        setMark({square: uci.slice(2, 4), ok: false});
        if (misses + 1 >= 3) advance(false, nextMistakes);   // third miss - the move is shown by itself
        else setMisses((m) => m + 1);
    };

    const last = (count: number) => (count > 0 ? {from: moves[count - 1].slice(0, 2), to: moves[count - 1].slice(2, 4)} : null);
    return (
        <div className="flex flex-col gap-3" data-testid="recall-game">
            <ReservedSlot lines={3.5} className="flex flex-col gap-1">
                <p className="text-sm">
                    {t('trainers.memory.gameLine', {white: game.white, black: game.black, year: game.year ?? ''})}
                </p>
                {phase === 'watch' ? (
                    <span className="font-bold text-amber-200" data-testid="recall-watch">{t('trainers.memory.watch', {n: shown, total: moves.length})}</span>
                ) : (
                    <span className="font-bold text-amber-200" data-testid="recall-play">
                        {t('trainers.memory.repeat', {n: played + 1, total: moves.length})} · {t('trainers.coord.score', {score: score / 10, mistakes})}
                    </span>
                )}
            </ReservedSlot>
            {phase === 'watch' ? (
                <>
                    <div className="w-full max-w-[460px]">
                        <PuzzleBoard fen={fenAfter(shown)} orientation="white" interactive={false} onMove={() => undefined} lastMove={last(shown)}/>
                    </div>
                </>
            ) : (
                <>
                    <div className="w-full max-w-[460px]">
                        <PuzzleBoard fen={fenAfter(played)} orientation="white" interactive={played < moves.length} onMove={onMove}
                                     lastMove={last(played)} mark={mark}/>
                    </div>
                </>
            )}
        </div>
    );
}
