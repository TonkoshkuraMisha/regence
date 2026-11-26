// --- FILE: frontend/src/components/social/SocialHeader.tsx ---
// Header (task 17.1): player search and the notification centre (bell). The bell polls the server every
// POLL_MS and immediately on the "notification" socket event (the socket is open on the main board). Unread direct messages
// (task 30.1) count toward the bell number; the first list row leads to "Messages".
// Data: socialApi.search, notifications and markRead (services/social.ts, /api/v1/social) and messagesApi.unread
// (services/messages.ts); also refreshed on the direct_message socket event and the regence:dm-changed window event.
// Rendered in App.tsx.

import {useCallback, useEffect, useRef, useState} from 'react';
import {Link, useNavigate} from 'react-router-dom';
import {Bell, MessageSquare, Search} from 'lucide-react';
import {useI18n} from '../../i18n';
import {controlLabel} from '../../services/arenas';
import {gameSocket} from '../../services/gameSocket';
import {messagesApi} from '../../services/messages';
import {notificationLink, socialApi} from '../../services/social';
import {eventTitle} from '../../services/timeMachine';
import {useKidMode} from '../../services/kidMode';
import type {AppNotification, Inbox, PlayerCard} from '../../services/social';
import {PLAYER_SEARCH_MAX} from '../../config/textLimits';

// Notification polling period (ms) in case no socket event arrives.
export const POLL_MS = 30_000;

/** Base-time minutes from the notification payload; no number - "?". */
function minutes(ms: unknown): string {
    return typeof ms === 'number' ? String(Math.round(ms / 60000)) : '?';
}

/** Notification text by kind; strings come from the social.notify.* catalogue, an unknown kind is a report reply. */
export function notificationText(n: AppNotification, t: ReturnType<typeof useI18n>['t']): string {
    const p = n.payload;
    if (n.kind === 'challenge') {
        return t('social.notify.challenge', {from: String(p.from), base: minutes(p.base_time_ms),
            inc: typeof p.increment_ms === 'number' ? Math.round(p.increment_ms / 1000) : 0});
    }
    if (n.kind === 'rematch') return t('social.notify.rematch', {from: String(p.from)});
    if (n.kind === 'tournament_round') return t('social.notify.tournamentRound', {round: Number(p.round)});
    if (n.kind === 'workout_reminder') return t('social.notify.workoutReminder', {streak: Number(p.streak)});
    if (n.kind === 'post_comment') return t('social.notify.postComment', {from: String(p.from)});
    if (n.kind === 'arena_reminder') {
        return t('social.notify.arenaReminder', {
            control: controlLabel({base_time_ms: Number(p.base_time_ms), increment_ms: Number(p.increment_ms)}),
        });
    }
    if (n.kind === 'arena_podium') return t('social.notify.arenaPodium', {place: Number(p.place)});
    if (n.kind === 'legends_week') return t('social.notify.legendsWeek', {title: eventTitle(String(p.event_key), t)});
    return t('social.notify.reportAnswer');
}

/** Player search by name prefix (from two characters, 250 ms debounce) with navigation to the profile. */
export function PlayerSearch() {
    const {t} = useI18n();
    const [open, setOpen] = useState(false);
    const [query, setQuery] = useState('');
    const [players, setPlayers] = useState<PlayerCard[]>([]);

    useEffect(() => {
        const q = query.trim();
        if (q.length < 2) {
            setPlayers([]);
            return;
        }
        const timer = window.setTimeout(() => {
            socialApi.search(q).then((r) => setPlayers(r.players)).catch(() => setPlayers([]));
        }, 250);
        return () => window.clearTimeout(timer);
    }, [query]);

    return (
        <div className="relative">
            <button type="button" onClick={() => setOpen((v) => !v)} aria-label={t('social.search')} title={t('social.search')}
                    data-testid="player-search-toggle"
                    className="p-2 hover:bg-black/30 rounded-md transition text-boxwood/85 hover:text-amber-300">
                <Search size={19}/>
            </button>
            {open && (
                <div className="absolute right-0 top-11 w-64 bg-[#1A120B] border border-amber-900/60 rounded-md shadow-xl p-2 z-50">
                    <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('social.searchPlaceholder')}
                           data-testid="player-search-input" maxLength={PLAYER_SEARCH_MAX}
                           className="w-full bg-black/40 rounded px-2 py-1 text-sm"/>
                    <ul className="mt-1 flex flex-col">
                        {players.map((p) => (
                            <li key={p.username}>
                                <Link to={`/profile/${encodeURIComponent(p.username)}`} onClick={() => setOpen(false)}
                                      className="flex items-center justify-between gap-2 px-2 py-1 rounded hover:bg-black/40 text-sm">
                                    <span className="flex items-center gap-1.5">
                                        <span className={`w-2 h-2 rounded-full ${p.online ? 'bg-emerald-400' : 'bg-stone-600'}`}
                                              aria-label={t(p.online ? 'social.online' : 'social.offline')}/>
                                        {p.username}
                                    </span>
                                    <span className="font-mono text-xs text-boxwood/70">{p.blitz_rating}</span>
                                </Link>
                            </li>
                        ))}
                        {query.trim().length >= 2 && players.length === 0 && (
                            <li className="px-2 py-1 text-xs text-boxwood/60">{t('social.nobody')}</li>
                        )}
                    </ul>
                </div>
            )}
        </div>
    );
}

/** Bell: unread count (notifications plus direct messages, shown up to "9+"); opening the list marks notifications as read. */
export function NotificationBell() {
    const {t} = useI18n();
    const navigate = useNavigate();
    const [inbox, setInbox] = useState<Inbox>({unread: 0, items: []});
    const [dmUnread, setDmUnread] = useState(0);
    const [open, setOpen] = useState(false);
    const alive = useRef(true);
    // Kid mode (task 23.1): messages are closed, so neither the unread count nor the link is shown.
    const kidMode = useKidMode();

    const refresh = useCallback(() => {
        socialApi.notifications().then((r) => alive.current && setInbox(r)).catch(() => undefined);
        if (kidMode) setDmUnread(0);
        else messagesApi.unread().then((r) => alive.current && setDmUnread(r.unread)).catch(() => undefined);
    }, [kidMode]);

    useEffect(() => {
        alive.current = true;
        refresh();
        const timer = window.setInterval(refresh, POLL_MS);
        const onNotification = () => refresh();
        gameSocket.on('notification', onNotification);
        gameSocket.on('direct_message', onNotification);
        window.addEventListener('regence:dm-changed', onNotification);
        return () => {
            alive.current = false;
            window.clearInterval(timer);
            gameSocket.off('notification', onNotification);
            gameSocket.off('direct_message', onNotification);
            window.removeEventListener('regence:dm-changed', onNotification);
        };
    }, [refresh]);

    const toggle = () => {
        const next = !open;
        setOpen(next);
        if (next && inbox.unread > 0) {
            socialApi.markRead().then((r) => alive.current && setInbox(r)).catch(() => undefined);
        }
    };

    return (
        <div className="relative">
            <button type="button" onClick={toggle} aria-label={t('social.notifications')} title={t('social.notifications')}
                    data-testid="notification-bell"
                    className="relative p-2 hover:bg-black/30 rounded-md transition text-boxwood/85 hover:text-amber-300">
                <Bell size={19}/>
                {inbox.unread + dmUnread > 0 && (
                    <span data-testid="notification-badge"
                          className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full bg-rose-600 text-white text-[10px] leading-4 text-center">
                        {inbox.unread + dmUnread > 9 ? '9+' : inbox.unread + dmUnread}
                    </span>
                )}
            </button>
            {open && (
                <div className="absolute right-0 top-11 w-72 max-h-96 overflow-y-auto bg-[#1A120B] border border-amber-900/60 rounded-md shadow-xl p-2 z-50"
                     data-testid="notification-list">
                    {!kidMode && <Link to="/messages" onClick={() => setOpen(false)} data-testid="notification-messages"
                          className="flex items-center justify-between gap-2 px-2 py-1.5 mb-1 rounded hover:bg-black/40 text-sm border-b border-amber-900/40">
                        <span className="flex items-center gap-1.5"><MessageSquare size={14}/> {t('dm.title')}</span>
                        {dmUnread > 0 && <span className="text-xs text-rose-300">{t('dm.newCount', {count: dmUnread})}</span>}
                    </Link>}
                    {inbox.items.length === 0 && <p className="text-sm text-boxwood/70 px-2 py-1">{t('social.noNotifications')}</p>}
                    {inbox.items.map((n) => (
                        <button key={n.id} type="button" onClick={() => {
                            setOpen(false);
                            navigate(notificationLink(n));
                        }} className={`w-full text-left px-2 py-1.5 rounded hover:bg-black/40 text-sm ${n.read ? 'text-boxwood/70' : 'text-amber-100'}`}>
                            {notificationText(n, t)}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}
