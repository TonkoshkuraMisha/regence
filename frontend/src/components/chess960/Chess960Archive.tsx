// --- FILE: frontend/src/components/chess960/Chess960Archive.tsx ---
// Viewer of a finished Fischer random game (task 21.3): /play/960/game/:gameId. The chess library of the client does not know
// the 960 rules, so the server replays the stored PGN (GET /api/v1/chess960/archive/{id}, src/services/chess960.py) and sends the
// position after every ply; the page only steps through them (buttons and arrow keys). "Analyse" asks the server for an engine
// evaluation of every position (UCI_Chess960, GET .../analysis; engine work - the limit and fair play apply) and draws the
// curve and the largest swings. GameViewer redirects here when the opened game has the Chess960 variant header.
// The same page shows a player's imported Fischer game (task 24.1, /import/game/:gameId/960, the `imported` prop): the
// positions come from GET /imports/games/{id}/chess960, the evaluation from the game's review (made in the background after
// the import, or started by the button) - services/gameImport.ts and services/analysis.ts.

import {useCallback, useEffect, useMemo, useState} from 'react';
import {Link, useParams} from 'react-router-dom';
import {ArrowLeft, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Shuffle} from 'lucide-react';
import {renderUiMessage, useI18n} from '../../i18n';
import type {UiMessage} from '../../i18n';
import {errorMessage} from '../../services/apiErrors';
import {analysisApi} from '../../services/analysis';
import {chess960Analysis, chess960Archive} from '../../services/chess960';
import {importApi} from '../../services/gameImport';
import type {ImportedGameView} from '../../services/gameImport';
import type {FullGameAnalysisReport} from '../gameViewer/viewerModel';
import type {Analysis960, Archive960} from '../../services/chess960';
import {PuzzleBoard} from '../puzzles/PuzzleBoard';
import {numberedMoves} from '../../services/moveNumbers';
import {displayFen} from './Chess960LiveGame';

/** Evaluation limit of the curve in centipawns: larger values (mates) are drawn flat so that the middle of the game stays readable. */
const CURVE_CAP_CP = 800;
/** A move that lowers the evaluation for the mover's side by at least this many centipawns is listed as a swing. */
const SWING_CP = 150;
/** At most this many largest swings are listed. */
const MAX_SWINGS = 5;
/** Magnitude from which an evaluation is a mate (src/services/chess960.py, MATE_SCORE_CP). */
const MATE_CP = 10000;

/** Evaluation text for the viewer: "+0.35", "-1.20"; a mate is shown as "+M" / "-M". */
export function formatScore(cp: number): string {
    if (Math.abs(cp) >= MATE_CP) return cp > 0 ? '+M' : '-M';
    const pawns = (cp / 100).toFixed(2);
    return cp > 0 ? `+${pawns}` : pawns;
}

/** One ply that lowered the mover's evaluation by SWING_CP or more. */
export interface Swing {
    ply: number; // index into the moves (0 = the first move)
    loss: number; // centipawns lost by the side that moved
}

/** The largest mistakes of both sides: the drop of the mover's evaluation between two neighbouring positions. */
export function swingsOf(scores: number[]): Swing[] {
    const swings: Swing[] = [];
    for (let ply = 0; ply + 1 < scores.length; ply += 1) {
        const white = ply % 2 === 0;
        const loss = white ? scores[ply] - scores[ply + 1] : scores[ply + 1] - scores[ply];
        if (loss >= SWING_CP) swings.push({ply, loss});
    }
    return swings.sort((a, b) => b.loss - a.loss).slice(0, MAX_SWINGS);
}

/** Engine data of the viewer; an imported game's review also gives both sides' accuracy. */
export interface ArchiveAnalysis extends Analysis960 {
    accuracy?: {white: number; black: number};
}

/**
 * The curve of an imported game from its review: the review holds the evaluation after every move, the start position's
 * evaluation is recovered from the first move's loss (before = after + loss for the side that moved).
 */
export function scoresFromReport(report: FullGameAnalysisReport): ArchiveAnalysis {
    const first = report.moves[0];
    const start = first ? first.eval_cp + (first.color === 'white' ? first.cp_loss : -first.cp_loss) : 0;
    return {game_id: report.game_id, scores: [start, ...report.moves.map((move) => move.eval_cp)], complete: true,
        accuracy: {white: report.white.accuracy, black: report.black.accuracy}};
}

/** The engine data of an imported game: the ready review, otherwise the review started now (limits apply). */
async function importedAnalysis(id: string): Promise<ArchiveAnalysis> {
    const report = (await analysisApi.cached('imported', id)) ?? await analysisApi.run('imported', id);
    return scoresFromReport(report);
}

/**
 * Viewer page: board, stepping, the move list and the optional engine curve. imported - the game is one of the player's
 * imported games (the names and the site are shown in the title).
 */
export function Chess960Archive({imported = false}: { imported?: boolean }) {
    const {t} = useI18n();
    const {gameId} = useParams<{ gameId: string }>();
    const [record, setRecord] = useState<Archive960 | null>(null);
    const [analysis, setAnalysis] = useState<ArchiveAnalysis | null>(null);
    const [meta, setMeta] = useState<ImportedGameView | null>(null);
    const [index, setIndex] = useState(0);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<UiMessage | null>(null);

    useEffect(() => {
        let cancelled = false;
        setRecord(null);
        setAnalysis(null);
        setError(null);
        const id = gameId ?? '';
        const load = imported ? Promise.all([importApi.chess960(id), importApi.game(id)])
            : chess960Archive(id).then((loaded) => [loaded, null] as const);
        load.then(([loaded, view]) => {
            if (cancelled) return;
            setRecord(loaded);
            setMeta(view);
            setIndex(loaded.moves.length);
        }).catch((err) => {
            if (!cancelled) setError(errorMessage(err, 'common.networkError'));
        });
        return () => {
            cancelled = true;
        };
    }, [gameId, imported]);

    const last = record ? record.moves.length : 0;
    const go = useCallback((to: number) => setIndex(Math.max(0, Math.min(last, to))), [last]);

    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            if (event.key === 'ArrowLeft') go(index - 1);
            else if (event.key === 'ArrowRight') go(index + 1);
            else if (event.key === 'Home') go(0);
            else if (event.key === 'End') go(last);
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [go, index, last]);

    const analyse = async () => {
        setBusy(true);
        setError(null);
        try {
            setAnalysis(imported ? await importedAnalysis(gameId ?? '') : await chess960Analysis(gameId ?? ''));
        } catch (err) {
            setError(errorMessage(err, 'common.networkError'));
        } finally {
            setBusy(false);
        }
    };

    const swings = useMemo(() => (analysis ? swingsOf(analysis.scores) : []), [analysis]);
    const move = index > 0 && record ? record.moves[index - 1] : null;
    const points = useMemo(() => {
        if (!analysis || analysis.scores.length < 2) return '';
        const step = 100 / (analysis.scores.length - 1);
        return analysis.scores.map((cp, i) => {
            const clamped = Math.max(-CURVE_CAP_CP, Math.min(CURVE_CAP_CP, cp));
            return `${(i * step).toFixed(2)},${(50 - (clamped / CURVE_CAP_CP) * 50).toFixed(2)}`;
        }).join(' ');
    }, [analysis]);

    return (
        <div className="w-full max-w-5xl mx-auto p-3 flex flex-col gap-4 text-boxwood-light" data-testid="chess960-archive">
            <Link to={imported ? '/import' : '/'} className="text-sm text-amber-400 hover:underline flex items-center gap-1">
                <ArrowLeft size={14}/> {t(imported ? 'chess960.archive.toImports' : 'chess960.live.toLobby')}
            </Link>
            <header className="flex items-center gap-2">
                <Shuffle className="text-amber-400"/>
                <h1 className="text-2xl font-bold text-amber-200" data-testid="c960a-title">
                    {meta ? t('chess960.archive.importedTitle', {site: t(`gameImport.source.${meta.source}`), white: meta.white, black: meta.black})
                        : t('chess960.archive.title', {id: gameId ?? ''})}
                </h1>
            </header>
            {error && <p role="alert" className="text-sm text-rose-300">{renderUiMessage(error, t)}</p>}
            {!record && !error && <p>{t('chess960.loading')}</p>}
            {record && (
                <div className="flex flex-col lg:flex-row gap-5 items-start">
                    <div className="w-full max-w-[480px] flex flex-col gap-2">
                        <PuzzleBoard fen={displayFen(record.fens[index])} orientation="white" interactive={false} onMove={() => undefined}
                                     lastMove={move ? {from: move.slice(0, 2), to: move.slice(2, 4)} : null}/>
                        <div className="flex justify-center gap-2">
                            <button type="button" onClick={() => go(0)} aria-label={t('chess960.archive.first')} data-testid="c960a-first"><ChevronsLeft/></button>
                            <button type="button" onClick={() => go(index - 1)} aria-label={t('chess960.archive.prev')} data-testid="c960a-prev"><ChevronLeft/></button>
                            <button type="button" onClick={() => go(index + 1)} aria-label={t('chess960.archive.next')} data-testid="c960a-next"><ChevronRight/></button>
                            <button type="button" onClick={() => go(last)} aria-label={t('chess960.archive.last')} data-testid="c960a-last"><ChevronsRight/></button>
                        </div>
                    </div>
                    <div className="flex-1 min-w-0 flex flex-col gap-2 text-sm">
                        <p className="text-amber-300" data-testid="c960a-position">{t('chess960.archive.ply', {n: index, total: last})}{record.result ? ` · ${record.result}` : ''}</p>
                        <p className="font-mono text-xs break-words" data-testid="c960a-moves">{numberedMoves(record.sans).join(' ')}</p>
                        {analysis && (
                            <p data-testid="c960a-score">{t('chess960.archive.score')}: {formatScore(analysis.scores[Math.min(index, analysis.scores.length - 1)])}</p>
                        )}
                        <button type="button" onClick={() => void analyse()} disabled={busy || !!analysis} data-testid="c960a-analyse"
                                className="self-start px-3 py-1.5 rounded bg-amber-700 text-white font-bold disabled:opacity-50">
                            {busy ? t('chess960.archive.analysing') : t('chess960.archive.analyse')}
                        </button>
                        {analysis && (
                            <>
                                <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-24 bg-black/30 rounded" role="img"
                                     aria-label={t('chess960.archive.curve')} data-testid="c960a-curve">
                                    <line x1="0" y1="50" x2="100" y2="50" stroke="currentColor" strokeOpacity="0.3" strokeWidth="0.5"/>
                                    <polyline points={points} fill="none" stroke="#fbbf24" strokeWidth="1.2" vectorEffect="non-scaling-stroke"/>
                                </svg>
                                {!analysis.complete && <p className="text-xs text-boxwood/70">{t('chess960.archive.partial')}</p>}
                                {analysis.accuracy && (
                                    <p className="text-xs" data-testid="c960a-accuracy">{t('chess960.archive.accuracy', {
                                        white: Math.round(analysis.accuracy.white), black: Math.round(analysis.accuracy.black)})}</p>
                                )}
                                {swings.length > 0 && (
                                    <ul className="text-xs" data-testid="c960a-swings">
                                        {swings.map((swing) => (
                                            <li key={swing.ply}>
                                                <button type="button" className="text-amber-300 hover:underline" onClick={() => go(swing.ply + 1)}>
                                                    {t('chess960.archive.swing', {move: record.sans[swing.ply], n: Math.floor(swing.ply / 2) + 1,
                                                        loss: (swing.loss / 100).toFixed(1)})}
                                                </button>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
