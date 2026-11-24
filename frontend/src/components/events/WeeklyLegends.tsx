// --- FILE: frontend/src/components/events/WeeklyLegends.tsx ---
// The weekly tournament against legends (task 26.1): the page /events/weekly and the lobby banner. The page shows the
// week's legends (a portrait, the strength and the player's result), the time control, the time left, the standings and
// last week's winner; "Play" opens a fair game on the server (weeklyLegendsApi.start) and hands it to the main board
// through location.state.weeklyGame (Chessboard.tsx). Data — services/weeklyLegends.ts; rules — src/services/weekly_legends.py.

import {useEffect, useState} from 'react';
import {Link, useNavigate} from 'react-router-dom';
import {Crown, Swords, Trophy} from 'lucide-react';
import {renderUiMessage, useI18n} from '../../i18n';
import type {UiMessage} from '../../i18n';
import {errorMessage} from '../../services/apiErrors';
import {getToken} from '../../services/authToken';
import {controlLabel} from '../../services/arenas';
import {weeklyLegendsApi} from '../../services/weeklyLegends';
import type {WeeklyEvent, WeeklyLegend, WeeklyStanding} from '../../services/weeklyLegends';
import {HISTORICAL_BOTS} from '../../config/champions';
import type {HistoricalBotId} from '../../config/champions';
import {PlayerAvatar} from '../PlayerAvatar';

const HOUR_MS = 3_600_000;
const DAY_MS = 24 * HOUR_MS;

/** Time left until the end of the week, in days and hours. */
function timeLeft(endsAt: string, now = Date.now()): { days: number; hours: number } {
    const ms = Math.max(0, new Date(endsAt).getTime() - now);
    return {days: Math.floor(ms / DAY_MS), hours: Math.floor((ms % DAY_MS) / HOUR_MS)};
}

/** The name of a legend in the player's language (the bots catalogue). */
function useLegendName() {
    const {t} = useI18n();
    return (botId: string) => t(`bots.profiles.${botId}.shortName` as Parameters<typeof t>[0]);
}

/** Lobby banner: the week's tournament against legends and the time left. */
export function WeeklyLegendsBanner() {
    const {t} = useI18n();
    const [event, setEvent] = useState<WeeklyEvent | null>(null);
    useEffect(() => {
        weeklyLegendsApi.event().then(setEvent).catch(() => undefined);
    }, []);
    if (!event) return null;
    const left = timeLeft(event.ends_at);
    return (
        <Link to="/events/weekly" data-testid="weekly-banner"
              className="flex items-center justify-between gap-2 px-2 py-1.5 mb-2 rounded bg-amber-900/40 border border-amber-700/60 text-xs hover:border-amber-400">
            <span className="flex items-center gap-1 font-bold text-amber-200"><Crown size={13}/> {t('weeklyLegends.title')}</span>
            <span className="text-boxwood/80">{t('weeklyLegends.timeLeft', left)}</span>
        </Link>
    );
}

function LegendCard({legend, canPlay, busy, onPlay}: {
    legend: WeeklyLegend; canPlay: boolean; busy: boolean; onPlay: (botId: string) => void;
}) {
    const {t} = useI18n();
    const name = useLegendName();
    const profile = HISTORICAL_BOTS[legend.bot_id as HistoricalBotId];
    const played = legend.points !== null;
    return (
        <li className="flex items-center gap-3 p-2 rounded bg-black/30 border border-amber-900/40" data-testid={`legend-${legend.bot_id}`}>
            {profile && <img src={profile.avatar} alt="" className="w-12 h-12 rounded object-cover sepia-[.3]"/>}
            <div className="flex-1 min-w-0">
                <div className="font-bold text-amber-200 truncate">{name(legend.bot_id)}</div>
                {legend.rating !== null && <div className="text-xs text-boxwood/70">{t('weeklyLegends.strength', {rating: legend.rating})}</div>}
            </div>
            {played ? (
                <span className="text-sm font-mono text-amber-300" data-testid={`legend-result-${legend.bot_id}`}
                      title={legend.forfeit ? t(`weeklyLegends.forfeit.${legend.forfeit}` as Parameters<typeof t>[0]) : undefined}>
                    {t('weeklyLegends.points', {points: legend.points ?? 0})}
                </span>
            ) : canPlay ? (
                <button type="button" disabled={busy} onClick={() => onPlay(legend.bot_id)} data-testid={`legend-play-${legend.bot_id}`}
                        className="px-3 py-1.5 rounded bg-amber-700 text-white text-sm font-bold flex items-center gap-1 disabled:opacity-50">
                    <Swords size={14}/> {t('weeklyLegends.play')}
                </button>
            ) : null}
        </li>
    );
}

function StandingRow({row, mine}: { row: WeeklyStanding; mine: boolean }) {
    const {t} = useI18n();
    return (
        <tr className={mine ? 'text-amber-200 font-bold' : 'text-boxwood-light'}>
            <td className="py-1 pr-2 text-right font-mono">{row.place}</td>
            <td className="py-1 pr-2">
                <Link to={`/profile/${encodeURIComponent(row.username)}`} className="flex items-center gap-1.5 hover:underline">
                    <PlayerAvatar username={row.username} avatar={row.avatar} className="w-5 h-5 rounded"/> {row.username}
                </Link>
            </td>
            <td className="py-1 pr-2 text-right font-mono">{t('weeklyLegends.points', {points: row.points})}</td>
            <td className="py-1 text-right text-xs text-boxwood/70">{t('weeklyLegends.wins', {wins: row.wins, games: row.games})}</td>
        </tr>
    );
}

/** The page /events/weekly. */
export function WeeklyLegendsPage() {
    const {t} = useI18n();
    const navigate = useNavigate();
    const name = useLegendName();
    const [event, setEvent] = useState<WeeklyEvent | null>(null);
    const [error, setError] = useState<UiMessage | null>(null);
    const [busy, setBusy] = useState(false);
    const signedIn = Boolean(getToken());

    useEffect(() => {
        weeklyLegendsApi.event().then(setEvent).catch((err) => setError(errorMessage(err, 'weeklyLegends.loadFailed')));
    }, []);

    const play = async (botId: string) => {
        setBusy(true);
        setError(null);
        try {
            navigate('/', {state: {weeklyGame: await weeklyLegendsApi.start(botId)}});
        } catch (err) {
            setError(errorMessage(err, 'weeklyLegends.startFailed'));
            setBusy(false);
        }
    };

    const left = event ? timeLeft(event.ends_at) : null;
    return (
        <div className="w-full max-w-4xl flex flex-col gap-4 font-serif" data-testid="weekly-page">
            <header className="bg-acacia-dark border border-amber-900/40 p-5 rounded shadow-heavy">
                <h1 className="text-2xl font-bold text-amber-200 flex items-center gap-2"><Crown size={22}/> {t('weeklyLegends.title')}</h1>
                <p className="text-sm text-boxwood/80 mt-2 max-w-2xl">{t('weeklyLegends.intro')}</p>
                {event && left && (
                    <p className="text-sm text-amber-300 mt-2" data-testid="weekly-meta">
                        {t('weeklyLegends.meta', {control: controlLabel(event), ...left})}
                    </p>
                )}
                {!signedIn && <p className="text-sm text-boxwood/70 mt-2">{t('weeklyLegends.loginToPlay')}</p>}
            </header>
            {error && <p className="text-sm text-red-300" role="alert">{renderUiMessage(error, t)}</p>}
            {event && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <section className="bg-acacia-dark border border-amber-900/40 p-4 rounded shadow-heavy">
                        <h2 className="text-lg font-bold text-amber-200 mb-3">{t('weeklyLegends.legends')}</h2>
                        {event.open_game && (
                            <p className="text-xs text-amber-300 mb-2" data-testid="weekly-open-game">
                                {t('weeklyLegends.openGame', {name: name(event.open_game)})}
                            </p>
                        )}
                        <ul className="flex flex-col gap-2">
                            {event.legends.map((legend) => (
                                <LegendCard key={legend.bot_id} legend={legend} canPlay={signedIn} busy={busy}
                                            onPlay={(botId) => void play(botId)}/>
                            ))}
                        </ul>
                        <p className="text-xs text-boxwood/65 mt-3">{t('weeklyLegends.rules')}</p>
                    </section>
                    <section className="bg-acacia-dark border border-amber-900/40 p-4 rounded shadow-heavy">
                        <h2 className="text-lg font-bold text-amber-200 mb-3 flex items-center gap-2">
                            <Trophy size={18}/> {t('weeklyLegends.standings', {players: event.standings.players})}
                        </h2>
                        {event.standings.top.length === 0 ? (
                            <p className="text-sm text-boxwood/70">{t('weeklyLegends.noPlayers')}</p>
                        ) : (
                            <table className="w-full text-sm" data-testid="weekly-standings">
                                <tbody>
                                    {event.standings.top.map((row) => (
                                        <StandingRow key={row.username} row={row} mine={row.username === event.standings.me?.username}/>
                                    ))}
                                    {event.standings.me && event.standings.me.place > event.standings.top.length && (
                                        <StandingRow row={event.standings.me} mine/>
                                    )}
                                </tbody>
                            </table>
                        )}
                        {event.last_winner && (
                            <p className="text-xs text-boxwood/70 mt-3" data-testid="weekly-last-winner">
                                {t('weeklyLegends.lastWinner', {name: event.last_winner.username, points: event.last_winner.points})}
                            </p>
                        )}
                    </section>
                </div>
            )}
        </div>
    );
}
