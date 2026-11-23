// --- FILE: frontend/src/components/puzzles/TimedLeaders.tsx ---
// Timed run leaderboard (task 26.1): a week (Monday to Monday, UTC) and all-time records, separately
// for 3- and 5-minute runs. Data is GET /puzzles/timed/leaders (src/services/puzzle_leaders.py): the top 20 and one's own
// row if the player is below the top. Shown on the run choice screen and after it; refreshKey changes when a run
// has ended, so that the new score gets into the table at once.

import {useEffect, useState} from 'react';
import {useI18n} from '../../i18n';
import {puzzlesApi} from '../../services/puzzles';
import type {LeaderRow, LeaderScope, TimedLeaders as Leaders} from '../../services/puzzles';

export function TimedLeaders({refreshKey}: { refreshKey: unknown }) {
    const {t} = useI18n();
    const [minutes, setMinutes] = useState<3 | 5>(3);
    const [scope, setScope] = useState<LeaderScope>('week');
    const [board, setBoard] = useState<Leaders | null>(null);

    useEffect(() => {
        let cancelled = false;
        puzzlesApi.timedLeaders(minutes, scope).then((r) => { if (!cancelled) setBoard(r); })
            .catch(() => { if (!cancelled) setBoard(null); });
        return () => { cancelled = true; };
    }, [minutes, scope, refreshKey]);

    const row = (r: LeaderRow) => (
        <li key={`${r.place}-${r.username}`} data-testid="leader-row" aria-current={r.me ? 'true' : undefined}
            className={`flex items-center gap-2 px-2 py-0.5 rounded ${r.me ? 'bg-amber-900/50 text-amber-100' : ''}`}>
            <span className="w-6 text-right text-boxwood/70">{r.place}</span>
            <span className="flex-1 truncate">{r.username}</span>
            <span className="font-mono">{r.score}</span>
        </li>
    );

    return (
        <div className="flex flex-col gap-1.5 text-sm" data-testid="timed-leaders">
            <span className="font-bold text-amber-200">{t('puzzles.leaders.title')}</span>
            <div className="flex flex-wrap gap-1.5">
                {([3, 5] as const).map((m) => (
                    <button key={m} type="button" aria-pressed={minutes === m} data-testid={`leaders-minutes-${m}`} onClick={() => setMinutes(m)}
                            className={`px-2 py-0.5 rounded border ${minutes === m ? 'bg-amber-800 border-amber-400 text-white' : 'border-amber-900/50'}`}>
                        {t('puzzles.leaders.minutes', {minutes: m})}
                    </button>
                ))}
                {(['week', 'all'] as const).map((s) => (
                    <button key={s} type="button" aria-pressed={scope === s} data-testid={`leaders-scope-${s}`} onClick={() => setScope(s)}
                            className={`px-2 py-0.5 rounded border ${scope === s ? 'bg-amber-800 border-amber-400 text-white' : 'border-amber-900/50'}`}>
                        {t(s === 'week' ? 'puzzles.leaders.week' : 'puzzles.leaders.all')}
                    </button>
                ))}
            </div>
            {board && board.rows.length === 0 && <p className="text-boxwood/70" data-testid="leaders-empty">{t('puzzles.leaders.empty')}</p>}
            {board && board.rows.length > 0 && (
                <ol className="flex flex-col">
                    {board.rows.map(row)}
                    {board.me && !board.rows.some((r) => r.me) && (
                        <>
                            <li aria-hidden className="text-center text-boxwood/50">…</li>
                            {row(board.me)}
                        </>
                    )}
                </ol>
            )}
        </div>
    );
}
