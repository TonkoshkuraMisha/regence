// --- FILE: frontend/src/components/chessboard/GameSummaryPanel.tsx ---
// Game result window: against a bot (task 11.5) and against a human (after the game ends): the review starts by itself after the game is saved, then the game type,
// accuracy, key moves with the coach's explanation and the recommended next opponent. The review is POST
// /analysis/game/{id} (the engine evaluates every move; the server serves a finished review from the database). The game type and key
// moves are the summary field of the response (src/services/game_summary.py), the labels are the summary.* catalog. The opponent recommendation
// is computed by Chessboard (services/gameSummary.ts) and passed as a prop. When the review is ready, the "Club coach" cards
// (CoachCards: a puzzle from one's own mistake, a repertoire deviation, a lesson on the mistake's theme). In a game against a human
// there is no opponent recommendation; the review is requested only after the game ends: during one's own game against a human the server
// will not provide it (fair play, forbid_engine_help_during_game).

import {useEffect, useState} from 'react';
import {Trophy} from 'lucide-react';
import {renderUiMessage, useI18n} from '../../i18n';
import type {UiMessage} from '../../i18n';
import {errorMessage} from '../../services/apiErrors';
import {analysisApi} from '../../services/analysis';
import {coachText} from '../../services/coach';
import type {CoachComment} from '../../services/coach';
import {isSummaryKind} from '../../services/gameSummary';
import type {GameSummary} from '../../services/gameSummary';
import {CoachCards} from './CoachCards';

// Parts of the review response this panel needs (the full response is FullGameAnalysisResponse on the server).
interface ReportMove {
    ply: number;
    move_number: number;
    color: 'white' | 'black';
    san: string;
    coach?: CoachComment | null;
}

interface Report {
    white: { accuracy: number };
    black: { accuracy: number };
    moves: ReportMove[];
    summary?: GameSummary | null;
}

interface Props {
    /** Game id: for a bot game, the /bots/save-game response (no panel until the game is saved); for a human game, the game id. */
    gameId: number;
    playerColor: 'white' | 'black';
    /** Name and strength of the recommended opponent (already in the player's language); null means nobody to recommend. */
    recommendation: { name: string; rating: number } | null;
    /** "Play" against the recommended opponent; not needed without a recommendation. */
    onPlayRecommended?: () => void;
}

/** Move with its number: "12. Nf3" for White, "12... Nf6" for Black. */
function moveLabel(move: ReportMove): string {
    return `${move.move_number}${move.color === 'white' ? '.' : '…'} ${move.san}`;
}

/** Game result: requests the review of the saved game itself and shows its main points. */
export function GameSummaryPanel({gameId, playerColor, recommendation, onPlayRecommended}: Props) {
    const {t} = useI18n();
    const [report, setReport] = useState<Report | null>(null);
    const [error, setError] = useState<UiMessage | null>(null);

    // The review is requested when the panel appears and when the game changes. The cancelled flag drops a response that arrives
    // after the panel is closed or for an already different game. A server refusal (engine busy, review limit exhausted)
    // is shown as text by the error code.
    useEffect(() => {
        let cancelled = false;
        setReport(null);
        setError(null);
        analysisApi.run<Report>('played', gameId, 'summary.failed')
            .then((data) => !cancelled && setReport(data))
            .catch((err) => !cancelled && setError(errorMessage(err, 'summary.failed')));
        return () => {
            cancelled = true;
        };
    }, [gameId]);

    const opponentColor = playerColor === 'white' ? 'black' : 'white';
    // An unknown game type (the server is newer than the client): the result without type and key moves, accuracy only.
    const summary = report?.summary && isSummaryKind(report.summary.kind) ? report.summary : null;
    // The server numbers key moves by ply starting from one; in the moves array they are indexed from zero.
    const moveAt = (ply: number | null | undefined) => (ply ? report?.moves[ply - 1] ?? null : null);
    const moments: { label: 'summary.turningPoint' | 'summary.yourBest' | 'summary.yourWorst'; move: ReportMove }[] = [];
    if (summary) {
        const turning = moveAt(summary.turning_point_ply);
        if (turning) moments.push({label: 'summary.turningPoint', move: turning});
        const best = moveAt(summary[playerColor].best_ply);
        if (best) moments.push({label: 'summary.yourBest', move: best});
        const worst = moveAt(summary[playerColor].worst_ply);
        if (worst && worst !== turning) moments.push({label: 'summary.yourWorst', move: worst});
    }

    return (
        <section aria-label={t('summary.title')} data-testid="game-summary"
                 className="bg-acacia-dark p-2.5 rounded-md border border-amber-600/50 text-xs text-boxwood-light flex flex-col gap-2">
            <div className="flex items-center gap-1.5 font-bold text-amber-400">
                <Trophy size={14}/> {t('summary.title')}
            </div>
            {!report && !error && <p className="animate-pulse text-amber-300">{t('summary.loading')}</p>}
            {error && <p className="text-rose-300" role="status">{renderUiMessage(error, t)}</p>}
            {report && (
                <>
                    {summary && (
                        <div data-testid="summary-kind">
                            <p className="font-bold text-amber-200">{t(`summary.kinds.${summary.kind}.name`)}</p>
                            <p className="text-boxwood/80 leading-snug">{t(`summary.kinds.${summary.kind}.text`)}</p>
                        </div>
                    )}
                    <p data-testid="summary-accuracy">
                        {t('summary.accuracy', {
                            mine: report[playerColor].accuracy, theirs: report[opponentColor].accuracy,
                        })}
                    </p>
                    {moments.map(({label, move}) => (
                        <div key={`${label}-${move.ply}`} data-testid={`summary-moment-${move.ply}`}>
                            <p className="font-bold">{t(label, {move: moveLabel(move)})}</p>
                            {move.coach && <p className="text-boxwood/80 leading-snug">{coachText(move.coach, t)}</p>}
                        </div>
                    ))}
                    <CoachCards gameId={gameId}/>
                </>
            )}
            {recommendation && (
                <div className="flex items-center justify-between gap-2 pt-1 border-t border-amber-900/40">
                    <span data-testid="summary-recommendation">
                        {t('summary.recommend', {name: recommendation.name, rating: recommendation.rating})}
                    </span>
                    <button type="button" onClick={onPlayRecommended} data-testid="summary-play"
                            className="px-2 py-1 rounded bg-amber-800 hover:bg-amber-700 text-white font-bold cursor-pointer">
                        {t('summary.play')}
                    </button>
                </div>
            )}
        </section>
    );
}
