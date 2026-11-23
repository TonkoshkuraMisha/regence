// --- FILE: frontend/src/components/chessboard/LadderPanel.tsx ---
// Club ladder: rungs from a weak opponent to a strong one, the player's ladder rating and a button for a game against the next
// opponent. State is GET /bots/ladder, game start is POST /bots/ladder/start (the server picks the opponent and
// colour when "random"). The game itself runs as an ordinary bot game (useBotGame), the result arrives in the response to its
// save (/bots/save-game, the ladder field). The server checks fair play (src/services/ladder.py): a hint,
// analysis, take-back or opponent substitution means the game is not counted.

import {useCallback, useEffect, useState} from 'react';
import {CheckCircle2, CircleDashed, Lock, Swords} from 'lucide-react';
import {errorMessage} from '../../services/apiErrors';
import {ladderApi} from '../../services/ladder';
import type {LadderStart, LadderState} from '../../services/ladder';
import type {LadderOutcome} from './hooks/useBotGame';
import {useI18n} from '../../i18n';
import {renderUiMessage} from '../../i18n';
import type {UiMessage} from '../../i18n';
import {ladderOpponentName} from '../../config/players';
import {getToken} from '../../services/authToken';

export interface LadderPanelProps {
    /** A game (against a human or a bot) is already in progress: a new one cannot be started. */
    playDisabled: boolean;
    /** The server opened a game: the caller starts it on the board with the given opponent and colour. */
    onStart: (start: LadderStart) => void;
    /** Changes after every saved ladder game: the panel re-reads progress. */
    lastOutcome: LadderOutcome | null;
}

/**
 * Club ladder: a separate rating in games against bots without engine hints and take-backs,
 * opponents from weak to strong. The server opens the game and also checks its fairness.
 */
export function LadderPanel({playDisabled, onStart, lastOutcome}: LadderPanelProps) {
    const {t} = useI18n();
    const [state, setState] = useState<LadderState | null>(null);
    const [error, setError] = useState<UiMessage | null>(null);
    const [starting, setStarting] = useState(false);

    const token = getToken();

    const load = useCallback(async () => {
        if (!token) return;
        try {
            setState(await ladderApi.state());
            setError(null);
        } catch (err) {
            setError(errorMessage(err, 'ladder.loadFailed'));
        }
    }, [token]);

    // Progress is read when the tab opens and again after every saved ladder game (lastOutcome).
    useEffect(() => {
        load();
    }, [load, lastOutcome]);

    const start = async (color: 'white' | 'black' | 'random') => {
        if (!token) return;
        setStarting(true);
        try {
            onStart(await ladderApi.start(color));
            await load();
        } catch (err) {
            setError(errorMessage(err, 'ladder.startFailed'));
        } finally {
            setStarting(false);
        }
    };

    const current = state?.rungs.find((r) => r.status === 'current');

    return (
        <div className="flex flex-col gap-2 text-xs text-boxwood" data-testid="ladder-panel">
            <p className="text-boxwood/80 leading-snug">
                {t('ladder.intro')}
            </p>
            {error && <p role="alert" className="text-red-300">{renderUiMessage(error, t)}</p>}
            {state && (
                <>
                    <div className="flex items-center justify-between p-2 rounded-md bg-black/40 border border-amber-800/50">
                        <span>{t('ladder.rating')}</span>
                        <span className="font-mono text-base text-amber-300" data-testid="ladder-rating">{state.rating}</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 rounded bg-black/50 overflow-hidden">
                            <div className="h-full bg-amber-500"
                                 style={{width: `${Math.round((Math.min(state.step, state.total) / state.total) * 100)}%`}}/>
                        </div>
                        <span className="font-mono text-amber-300/90">{Math.min(state.step, state.total)}/{state.total}</span>
                    </div>

                    {current && (
                        <div className="p-2 rounded-md bg-black/40 border border-amber-600/50 flex flex-col gap-1.5">
                            <div className="flex items-center justify-between">
                                <span className="font-bold text-amber-200">{t('ladder.next', {name: ladderOpponentName(current.kind, current.id, t)})}</span>
                                <span className="font-mono text-amber-300">
                                    {current.measured ? t('common.measuredShort', {rating: current.rating}) : current.rating}
                                </span>
                            </div>
                            <div className="grid grid-cols-3 gap-1.5">
                                {(['white', 'random', 'black'] as const).map((color) => (
                                    <button key={color} type="button" disabled={playDisabled || starting}
                                            onClick={() => start(color)}
                                            className="py-1.5 font-bold rounded-md bg-amber-700 text-white hover:bg-amber-600 disabled:opacity-40 cursor-pointer">
                                        {t(color === 'white' ? 'common.playAsWhite' : color === 'black' ? 'common.playAsBlack' : 'common.playRandom')}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    <ol className="flex flex-col gap-0.5">
                        {state.rungs.map((r, i) => (
                            <li key={r.key}
                                className={`flex items-center gap-1.5 px-2 py-0.5 rounded ${
                                    r.status === 'current' ? 'bg-amber-900/50 text-amber-100' : 'text-boxwood/80'}`}>
                                <span className="w-4 text-right font-mono text-boxwood/50">{i + 1}</span>
                                {r.status === 'beaten' ? <CheckCircle2 size={12} className="text-emerald-400" aria-label={t('ladder.beaten')}/>
                                    : r.status === 'current' ? <Swords size={12} className="text-amber-300" aria-label={t('ladder.current')}/>
                                        : r.status === 'skipped' ? <CircleDashed size={12} className="text-boxwood/60" aria-label={t('ladder.skipped')}
                                                                                 data-testid={`ladder-skipped-${r.key}`}/>
                                            : <Lock size={12} className="text-boxwood/40" aria-label={t('ladder.locked')}/>}
                                <span className="flex-1 truncate">{ladderOpponentName(r.kind, r.id, t)}</span>
                                <span className="font-mono">{r.rating}</span>
                            </li>
                        ))}
                    </ol>
                </>
            )}
        </div>
    );
}
