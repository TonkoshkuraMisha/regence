// --- FILE: frontend/src/components/tournaments/LegendsWeek.tsx ---
// Weekly tournament against the legends (task 26.1): the announcement of this week's historic tournament and the table of the best
// runs. Data: services/timeMachine.ts getLegendsWeek (server: src/services/legends_week.py). Everyone plays their own run, so
// "Play" just starts the announced event through the same time-machine start as on the page below. LegendsAnnouncement is the
// one-line announcement for the tournaments lobby (TournamentsPage.tsx).

import {useEffect, useState} from 'react';
import {Link} from 'react-router-dom';
import {useI18n} from '../../i18n';
import {eventTitle, getLegendsWeek} from '../../services/timeMachine';
import type {LegendsRow, LegendsWeek as Week} from '../../services/timeMachine';

/** The week loaded once; a failure leaves the card out (the announcement is a convenience, not a requirement). */
function useLegendsWeek(): Week | null {
    const [week, setWeek] = useState<Week | null>(null);
    useEffect(() => {
        let alive = true;
        // A reply of another shape (an old server) is treated like a failure: no card.
        getLegendsWeek().then((w) => alive && Array.isArray(w?.rows) && setWeek(w)).catch(() => undefined);
        return () => {
            alive = false;
        };
    }, []);
    return week;
}

export function LegendsWeek({busy, onStart}: { busy: boolean; onStart: (eventKey: string) => void }) {
    const {t} = useI18n();
    const week = useLegendsWeek();
    if (!week) return null;
    const row = (r: LegendsRow) => (
        <li key={`${r.place}-${r.username}`} data-testid="legends-row" aria-current={r.me ? 'true' : undefined}
            className={`flex items-center gap-2 px-2 py-0.5 rounded ${r.me ? 'bg-amber-900/50 text-amber-100' : ''}`}>
            <span className="w-6 text-right text-boxwood/70">{r.place}</span>
            <span className="flex-1 truncate">{r.username}</span>
            <span className="text-sm">{t('timeMachine.legendsWeek.place', {place: r.tournament_place})}</span>
        </li>
    );
    return (
        <section className="bg-acacia p-4 rounded-lg border-2 border-amber-700 flex flex-col gap-2" data-testid="legends-week">
            <h2 className="text-lg font-bold text-amber-200">{t('timeMachine.legendsWeek.title')}</h2>
            <p className="font-semibold">{t('timeMachine.legendsWeek.thisWeek', {title: eventTitle(week.event_key, t)})}</p>
            <p className="text-sm text-boxwood/85">{t('timeMachine.legendsWeek.intro')}</p>
            <p className="text-xs text-boxwood/65">{t('timeMachine.legendsWeek.until', {date: week.ends_on})}</p>
            <button type="button" disabled={busy} onClick={() => onStart(week.event_key)} data-testid="legends-play"
                    className="self-start px-3 py-1.5 rounded-md bg-amber-700 text-white font-semibold disabled:opacity-50">
                {t('timeMachine.legendsWeek.play')}
            </button>
            {week.rows.length === 0 && (
                <p className="text-sm text-boxwood/70" data-testid="legends-empty">{t('timeMachine.legendsWeek.empty')}</p>
            )}
            {week.rows.length > 0 && (
                <ol className="flex flex-col text-sm">
                    {week.rows.map(row)}
                    {week.me && !week.rows.some((r) => r.me) && (
                        <>
                            <li aria-hidden className="text-center text-boxwood/50">…</li>
                            {row(week.me)}
                        </>
                    )}
                </ol>
            )}
        </section>
    );
}

/** One-line announcement for the lobby: this week's event with a link to the page where it is played. */
export function LegendsAnnouncement() {
    const {t} = useI18n();
    const week = useLegendsWeek();
    if (!week) return null;
    return (
        <p className="text-sm" data-testid="legends-announcement">
            <Link to="/time-machine" className="underline text-amber-300">
                {t('timeMachine.legendsWeek.announce', {title: eventTitle(week.event_key, t)})}
            </Link>
        </p>
    );
}
