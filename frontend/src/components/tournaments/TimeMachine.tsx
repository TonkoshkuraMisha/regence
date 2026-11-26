// --- FILE: frontend/src/components/tournaments/TimeMachine.tsx ---
// "Time Machine" (task 28.3): /time-machine - famous tournaments of the past by year. The player enters a tournament
// as an additional participant with the full historic line-up; games between masters are played by the server.
// RealResult - "how it really was": the real final table next to the player's tournament.
// Data: services/timeMachine.ts - getTimeMachine (event catalogue with line-ups) and startHistoricEvent (creating a
// tournament with the chosen time control); titles and stories - catalogue timeMachine.events.<key>.*. Route - App.tsx;
// RealResult is also shown by TournamentsPage.tsx (TournamentView of a historic tournament). Entering a tournament is open to any
// registered player, without strength thresholds.

import {useEffect, useState} from 'react';
import {Link, useNavigate} from 'react-router-dom';
import {Hourglass} from 'lucide-react';
import {renderUiMessage, uiMessage, useI18n} from '../../i18n';
import type {MessageKey, UiMessage} from '../../i18n';
import {errorMessage} from '../../services/apiErrors';
import {getToken} from '../../services/authToken';
import {ALL_TIME_CONTROLS} from '../../config/timeControls';
import {
    eventTitle, fieldName, fieldShortName, getTimeMachine, guestAbout, scoreText, startHistoricEvent,
} from '../../services/timeMachine';
import type {FieldEntry, HistoricEvent} from '../../services/timeMachine';
import {LegendsSeason, LegendsWeek} from './LegendsWeek';

// Shared look of a page section card.
const sectionClass = 'bg-acacia p-4 rounded-lg border-2 border-acacia-dark';
/**
 * Timeline periods - by eras of tournament life: the first tournaments, the classics of the end of the century, the years before the world war and
 * the interwar time. A period starts at the given year and lasts until the next one; the last - to the end of the timeline.
 */
export const PERIOD_STARTS = [1851, 1881, 1901, 1915];

/** Number of the period the tournament year belongs to. */
export function periodOf(year: number): number {
    let index = 0;
    for (let i = 0; i < PERIOD_STARTS.length; i++) if (year >= PERIOD_STARTS[i]) index = i;
    return index;
}

/** Period label: "1881-1900"; for the last one - up to the year of the timeline's last tournament. */
export function periodLabel(index: number, lastYear: number): string {
    const end = index + 1 < PERIOD_STARTS.length ? PERIOD_STARTS[index + 1] - 1 : Math.max(lastYear, PERIOD_STARTS[index]);
    return `${PERIOD_STARTS[index]}–${end}`;
}
/** Default control is 10 minutes: a big tournament has many games. */
const DEFAULT_CONTROL = 'rapid-10+0';

/** The real tournament table: place, participant, points. In a knockout tournament - places and those eliminated in the first round. */
function RealTable({field}: { field: FieldEntry[] }) {
    const {t} = useI18n();
    return (
        <ol className="text-sm columns-1 sm:columns-2 gap-x-8" data-testid="real-table">
            {field.map((entry) => (
                <li key={entry.id} className="flex gap-2 items-baseline min-w-0 break-inside-avoid py-px"
                    title={guestAbout(entry.id, t) ?? undefined}>
                    <span className="w-6 text-right font-mono text-boxwood/70 shrink-0">{entry.place ?? '—'}</span>
                    <span className="truncate">{fieldName(entry, t)}</span>
                    <span className="ml-auto font-mono text-boxwood/80 shrink-0">
                        {entry.score !== null ? scoreText(entry.score) : entry.place === null ? t('timeMachine.outFirstRound') : ''}
                    </span>
                </li>
            ))}
        </ol>
    );
}

/** "How it really was" block: a story and the real table; expanded when the player's tournament is finished, and compares the place. */
export function RealResult({eventKey, finished, myPlace}: { eventKey: string; finished: boolean; myPlace: number | null }) {
    const {t} = useI18n();
    const [event, setEvent] = useState<HistoricEvent | null>(null);
    useEffect(() => {
        let alive = true;
        getTimeMachine().then((events) => alive && setEvent(events.find((e) => e.key === eventKey) ?? null)).catch(() => undefined);
        return () => {
            alive = false;
        };
    }, [eventKey]);
    if (!event) return null;
    const real = `timeMachine.events.${eventKey}.real` as MessageKey;
    return (
        <details className={sectionClass} open={finished} data-testid="real-result">
            <summary className="font-bold text-amber-200 cursor-pointer">{t('timeMachine.realTitle')}</summary>
            <div className="flex flex-col gap-2 mt-2">
                <p className="text-sm">{t(real)}</p>
                {finished && myPlace !== null && (
                    <p className="text-sm text-amber-300" data-testid="real-compare">{t('timeMachine.yourPlace', {place: myPlace})}</p>
                )}
                <RealTable field={event.field}/>
            </div>
        </details>
    );
}

/** Historic tournament card: story, format, strongest participants, full line-up and an enter or "Continue" button. */
function EventCard({event, control, busy, onStart}: {
    event: HistoricEvent; control: string; busy: boolean; onStart: (event: HistoricEvent) => void;
}) {
    const {t, tp} = useI18n();
    const text = (part: string) => t(`timeMachine.events.${event.key}.${part}` as MessageKey);
    const strongest = [...event.field].sort((a, b) => b.rating - a.rating).slice(0, 5);
    return (
        <article className={`${sectionClass} flex flex-col gap-3`} data-testid={`event-${event.key}`}>
            <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="text-3xl font-bold font-mono text-amber-400">{event.year}</span>
                <h2 className="text-xl font-bold text-amber-200">{text('title')}</h2>
                <span className="text-sm text-boxwood/75">{text('place')}</span>
                {event.best_place !== null && (
                    <span className="ml-auto text-sm text-emerald-300" data-testid={`best-${event.key}`}>
                        {t('timeMachine.bestPlace', {place: event.best_place})}
                    </span>
                )}
            </header>
            <p className="text-sm leading-relaxed max-w-3xl">{text('story')}</p>
            <ul className="text-sm text-boxwood/85 flex flex-wrap gap-x-5 gap-y-1">
                <li>{t(`timeMachine.formats.${event.format}`)}{event.cycles > 1 ? ` · ${tp('timeMachine.cycles', event.cycles)}` : ''}</li>
                <li>{tp('timeMachine.masters', event.field.length)}</li>
                <li data-testid={`games-${event.key}`}>
                    {event.player_games !== null ? tp('timeMachine.yourGames', event.player_games) : t('timeMachine.knockoutGames')}
                </li>
            </ul>
            <p className="text-sm">
                <span className="text-boxwood/70">{t('timeMachine.strongest')}</span>{' '}
                {strongest.map((entry) => fieldShortName(entry, t)).join(', ')}
            </p>
            <details>
                <summary className="text-sm text-amber-300 cursor-pointer">{t('timeMachine.fullField')}</summary>
                <div className="mt-2 flex flex-col gap-2">
                    <p className="text-sm text-boxwood/80">{text('real')}</p>
                    <RealTable field={event.field}/>
                </div>
            </details>
            <div className="flex flex-wrap items-center gap-3">
                {event.active_id !== null ? (
                    <Link to={`/tournaments/${event.active_id}`} data-testid={`continue-${event.key}`}
                          className="px-4 py-2 rounded-md bg-amber-700 text-white font-bold hover:bg-amber-600">
                        {t('timeMachine.continue')}
                    </Link>
                ) : (
                    <button type="button" disabled={busy} onClick={() => onStart(event)} data-testid={`start-${event.key}`}
                            className="px-4 py-2 rounded-md bg-amber-700 text-white font-bold hover:bg-amber-600 disabled:opacity-50 cursor-pointer">
                        {t('timeMachine.enter', {control})}
                    </button>
                )}
                {event.played > 0 && <span className="text-xs text-boxwood/65">{tp('timeMachine.played', event.played)}</span>}
            </div>
        </article>
    );
}

/** Tournament timeline with a time control and period choice; entering creates a tournament on the server and opens its page. */
export function TimeMachinePage() {
    const {t} = useI18n();
    const navigate = useNavigate();
    const [events, setEvents] = useState<HistoricEvent[] | null>(null);
    const [control, setControl] = useState(DEFAULT_CONTROL);
    // Timeline period: null - all tournaments.
    const [period, setPeriod] = useState<number | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<UiMessage | null>(null);

    useEffect(() => {
        let alive = true;
        getTimeMachine().then((list) => alive && setEvents(list))
            .catch((err) => alive && setError(errorMessage(err, 'timeMachine.loadFailed')));
        return () => {
            alive = false;
        };
    }, []);

    // Bullet is not suitable for a twenty-game tournament; "custom control" is not configured here.
    const controls = ALL_TIME_CONTROLS.filter((c) => !c.isManual && c.base >= 3);
    const chosen = controls.find((c) => c.id === control) ?? controls[0];
    const start = (event: { key: string }) => {
        // The timeline is open to a guest too, but the tournament participant is a player: games and place are written to their profile.
        if (!getToken()) {
            setError(uiMessage('timeMachine.loginToEnter'));
            return;
        }
        setBusy(true);
        setError(null);
        startHistoricEvent(event.key, chosen.base * 60_000, chosen.inc * 1000)
            .then((tournament) => navigate(`/tournaments/${tournament.id}`))
            .catch((err) => setError(errorMessage(err, 'timeMachine.startFailed')))
            .finally(() => setBusy(false));
    };
    // Historic tournaments do not block each other (owner decision, 17.11): ongoing ones - with their own "Continue" button.
    const active = events?.filter((e) => e.active_id !== null) ?? [];
    const shown = events?.filter((e) => period === null || periodOf(e.year) === period) ?? null;
    const lastYear = events?.length ? Math.max(...events.map((e) => e.year)) : PERIOD_STARTS[PERIOD_STARTS.length - 1];
    const chip = (on: boolean) => `px-3 py-1.5 rounded-md text-sm font-semibold cursor-pointer transition ${
        on ? 'bg-amber-700 text-white' : 'bg-black/30 text-boxwood-light hover:bg-black/50'}`;

    return (
        <div className="w-full max-w-5xl mx-auto p-3 flex flex-col gap-4 text-boxwood-light" data-testid="time-machine">
            <header className="flex flex-col gap-2">
                <h1 className="text-2xl font-bold text-amber-200 flex items-center gap-2">
                    <Hourglass className="text-amber-400"/> {t('timeMachine.title')}
                </h1>
                <p className="text-sm text-boxwood/85 max-w-3xl">{t('timeMachine.intro')}</p>
                {/* Catalogue of masters of the past (task 28.5): a single game with any participant. */}
                <p className="text-sm">
                    <Link to="/masters" data-testid="masters-link" className="underline text-amber-300">{t('masters.title')}</Link>
                    <span className="text-boxwood/75"> — {t('masters.teaser')}</span>
                </p>
            </header>
            {error && <p role="alert" className="text-sm text-rose-300">{renderUiMessage(error, t)}</p>}
            <LegendsWeek busy={busy} onStart={(key) => start({key})}/>
            <LegendsSeason/>
            <div className={`${sectionClass} flex flex-wrap items-center gap-3`}>
                <label htmlFor="tm-control" className="text-sm">{t('timeMachine.control')}</label>
                <select id="tm-control" value={chosen.id} data-testid="tm-control"
                        onChange={(e) => setControl(e.target.value)} className="bg-black/40 rounded px-2 py-1 text-sm">
                    {controls.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                </select>
                <span className="text-xs text-boxwood/65">{t('timeMachine.controlHint')}</span>
            </div>
            {active.length > 0 && (
                <p className="text-sm text-amber-300" data-testid="tm-active">
                    {t('timeMachine.inProgress', {titles: active.map((e) => eventTitle(e.key, t)).join(', ')})}
                </p>
            )}
            {events === null && !error && <p className="text-sm text-boxwood/70">{t('timeMachine.loading')}</p>}
            {events !== null && events.length > 0 && (
                <div role="group" aria-label={t('timeMachine.period')} className="flex flex-wrap items-center gap-2" data-testid="tm-periods">
                    <button type="button" aria-pressed={period === null} onClick={() => setPeriod(null)} data-testid="period-all"
                            className={chip(period === null)}>
                        {t('timeMachine.allPeriods')} · {events.length}
                    </button>
                    {PERIOD_STARTS.map((start, index) => {
                        const count = events.filter((e) => periodOf(e.year) === index).length;
                        if (count === 0) return null;
                        return (
                            <button key={start} type="button" aria-pressed={period === index} onClick={() => setPeriod(index)}
                                    data-testid={`period-${index}`} className={chip(period === index)}>
                                {periodLabel(index, lastYear)} · {count}
                            </button>
                        );
                    })}
                </div>
            )}
            {shown?.map((event) => (
                <EventCard key={event.key} event={event} control={chosen.label} busy={busy}
                           onStart={start}/>
            ))}
        </div>
    );
}
