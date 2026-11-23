// --- FILE: frontend/src/components/beta/BetaAdmin.tsx ---
// Beta programme for a moderator (task 24.4), on the /moderation page (social/ModerationPage.tsx; the panels are visible only to
// a moderator): invitations (create a code with a limit and an expiry, copy a link, revoke; one sees how many people
// came through each) and a queue of "Report a problem" messages with statuses. Data is services/beta.ts
// (/api/v1/beta/invites and /feedback, src/api/beta.py); the server checks the rights.

import {useCallback, useEffect, useState} from 'react';
import {Bug, Ticket} from 'lucide-react';
import {renderUiMessage, useI18n} from '../../i18n';
import type {UiMessage} from '../../i18n';
import {errorMessage} from '../../services/apiErrors';
import {betaApi, FEEDBACK_STATUSES, inviteLink} from '../../services/beta';
import type {FeedbackItem, FeedbackStatus, Invite} from '../../services/beta';

// Styles of the input field and the panels' buttons (extracted so as not to repeat long class strings).
const inputClass = 'bg-black/40 border border-amber-900/60 rounded px-2 py-1 text-sm text-amber-100 focus:outline-none focus:border-amber-600';
const buttonClass = 'px-2 py-1 rounded bg-black/40 border border-amber-800/60 hover:border-amber-500 text-sm';

/** Positive integer from a form field; an empty or invalid value gives undefined (the field is not sent, no limit). */
function positiveInt(raw: string): number | undefined {
    const value = Number.parseInt(raw, 10);
    return Number.isFinite(value) && value > 0 ? value : undefined;
}

/** Invitations: the registration mode (closed by invitation or open), a new code form and a list of codes. */
export function InvitesPanel() {
    const {t, dateLocale} = useI18n();
    const [invites, setInvites] = useState<Invite[]>([]);
    const [inviteOnly, setInviteOnly] = useState(false);
    const [note, setNote] = useState('');
    const [maxUses, setMaxUses] = useState('');
    const [days, setDays] = useState('');
    const [copied, setCopied] = useState<number | null>(null);
    const [error, setError] = useState<UiMessage | null>(null);

    const fail = (err: unknown) => setError(errorMessage(err, 'common.networkError'));
    const load = useCallback(() => {
        betaApi.invites().then((data) => {
            setInvites(Array.isArray(data.invites) ? data.invites : []);
            setInviteOnly(data.invite_only === true);
        }).catch((err) => setError(errorMessage(err, 'common.networkError')));
    }, []);
    useEffect(load, [load]);

    const create = (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        betaApi.createInvite({
            ...(note.trim() ? {note: note.trim()} : {}),
            ...(positiveInt(maxUses) ? {max_uses: positiveInt(maxUses)} : {}),
            ...(positiveInt(days) ? {expires_in_days: positiveInt(days)} : {}),
        }).then(() => {
            setNote('');
            load();
        }).catch(fail);
    };

    const copy = (invite: Invite) => {
        void navigator.clipboard?.writeText(inviteLink(invite.code)).then(() => setCopied(invite.id)).catch(() => undefined);
    };

    return (
        <section className="flex flex-col gap-2" data-testid="beta-invites">
            <h2 className="font-bold text-amber-200 flex items-center gap-2"><Ticket size={18}/> {t('beta.invites.title')}</h2>
            <p className="text-sm text-boxwood/75" data-testid="beta-invite-mode">
                {t(inviteOnly ? 'beta.invites.modeClosed' : 'beta.invites.modeOpen')}
            </p>
            <form className="flex flex-wrap gap-2 items-end" onSubmit={create} data-testid="beta-invite-form">
                <label className="flex flex-col gap-0.5 text-xs text-boxwood/75 grow min-w-40">
                    {t('beta.invites.note')}
                    <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={100} className={inputClass}
                           data-testid="beta-invite-note"/>
                </label>
                <label className="flex flex-col gap-0.5 text-xs text-boxwood/75 w-32">
                    {t('beta.invites.maxUses')}
                    <input value={maxUses} onChange={(e) => setMaxUses(e.target.value)} type="number" min={1} inputMode="numeric"
                           placeholder={t('beta.invites.unlimited')} className={inputClass} data-testid="beta-invite-max"/>
                </label>
                <label className="flex flex-col gap-0.5 text-xs text-boxwood/75 w-32">
                    {t('beta.invites.expiresDays')}
                    <input value={days} onChange={(e) => setDays(e.target.value)} type="number" min={1} max={365} inputMode="numeric"
                           placeholder={t('beta.invites.noExpiry')} className={inputClass} data-testid="beta-invite-days"/>
                </label>
                <button type="submit" className="px-3 py-1.5 rounded bg-amber-700 text-white font-bold text-sm">{t('beta.invites.create')}</button>
            </form>
            {error && <p role="alert" className="text-sm text-rose-300">{renderUiMessage(error, t)}</p>}
            {invites.length === 0 && <p className="text-sm text-boxwood/70">{t('beta.invites.empty')}</p>}
            {invites.map((invite) => (
                <article key={invite.id} data-testid={`beta-invite-${invite.id}`}
                         className={`bg-black/30 rounded p-3 flex flex-wrap gap-x-3 gap-y-1 items-baseline text-sm ${invite.state === 'active' ? '' : 'opacity-60'}`}>
                    <span className="font-mono font-bold text-amber-200 select-text">{invite.code}</span>
                    <span className={invite.state === 'active' ? 'text-emerald-300' : 'text-rose-300'}>{t(`beta.invites.states.${invite.state}`)}</span>
                    <span data-testid={`beta-invite-uses-${invite.id}`}>
                        {invite.max_uses === null ? t('beta.invites.uses', {n: invite.uses})
                            : t('beta.invites.usesOf', {n: invite.uses, max: invite.max_uses})}
                    </span>
                    {invite.expires_at && (
                        <span className="text-boxwood/70">
                            {t('beta.invites.expires', {date: new Date(invite.expires_at).toLocaleDateString(dateLocale.code)})}
                        </span>
                    )}
                    {invite.note && <span className="text-boxwood/85">{invite.note}</span>}
                    {invite.state === 'active' && (
                        <span className="flex gap-1.5 ml-auto">
                            <button type="button" className={buttonClass} onClick={() => copy(invite)} data-testid={`beta-invite-copy-${invite.id}`}>
                                {t(copied === invite.id ? 'beta.invites.copied' : 'beta.invites.copyLink')}
                            </button>
                            <button type="button" className={buttonClass} data-testid={`beta-invite-revoke-${invite.id}`}
                                    onClick={() => void betaApi.revokeInvite(invite.id).then(load).catch(fail)}>
                                {t('beta.invites.revoke')}
                            </button>
                        </span>
                    )}
                </article>
            ))}
        </section>
    );
}

/** Queue of player messages: tabs by status with counters, the message context and a status change. */
export function FeedbackPanel() {
    const {t, dateLocale} = useI18n();
    // null means unprocessed (new and taken into work).
    const [filter, setFilter] = useState<FeedbackStatus | null>(null);
    const [items, setItems] = useState<FeedbackItem[]>([]);
    const [counts, setCounts] = useState<Partial<Record<FeedbackStatus, number>>>({});
    const [error, setError] = useState<UiMessage | null>(null);

    const load = useCallback(() => {
        betaApi.feedback(filter ?? undefined).then((data) => {
            setItems(Array.isArray(data.items) ? data.items : []);
            setCounts(data.counts ?? {});
        }).catch((err) => setError(errorMessage(err, 'common.networkError')));
    }, [filter]);
    useEffect(load, [load]);

    const open = (counts.new ?? 0) + (counts.in_progress ?? 0);
    const tabClass = (active: boolean) => `${buttonClass} ${active ? 'border-amber-400 text-amber-200' : ''}`;
    return (
        <section className="flex flex-col gap-2" data-testid="beta-feedback">
            <h2 className="font-bold text-amber-200 flex items-center gap-2"><Bug size={18}/> {t('beta.feedback.title')}</h2>
            <div className="flex flex-wrap gap-1.5">
                <button type="button" className={tabClass(filter === null)} onClick={() => setFilter(null)} data-testid="beta-feedback-tab-open">
                    {t('beta.feedback.open', {n: open})}
                </button>
                {FEEDBACK_STATUSES.map((status) => (
                    <button key={status} type="button" className={tabClass(filter === status)} onClick={() => setFilter(status)}
                            data-testid={`beta-feedback-tab-${status}`}>
                        {t('beta.feedback.statusCount', {status: t(`beta.feedback.statuses.${status}`), n: counts[status] ?? 0})}
                    </button>
                ))}
            </div>
            {error && <p role="alert" className="text-sm text-rose-300">{renderUiMessage(error, t)}</p>}
            {items.length === 0 && <p className="text-sm text-boxwood/70">{t('beta.feedback.empty')}</p>}
            {items.map((item) => (
                <article key={item.id} className="bg-black/30 rounded p-3 flex flex-col gap-1.5 text-sm" data-testid={`beta-feedback-${item.id}`}>
                    <div className="flex flex-wrap gap-x-2 gap-y-0.5 items-baseline">
                        <span className="font-bold">{t(`beta.feedback.statuses.${item.status}`)}</span>
                        <span className="text-boxwood/80">{item.author ?? t('beta.feedback.guest')}</span>
                        {item.created_at && <span className="text-xs text-boxwood/60">{new Date(item.created_at).toLocaleString(dateLocale.code)}</span>}
                    </div>
                    <p className="whitespace-pre-wrap break-words select-text">{item.message}</p>
                    <span className="font-mono text-xs text-amber-200/80 break-all" data-testid={`beta-feedback-context-${item.id}`}>
                        {[item.page, item.app_version && `v${item.app_version}`, item.language, item.screen].filter(Boolean).join(' · ')}
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                        {FEEDBACK_STATUSES.filter((status) => status !== item.status).map((status) => (
                            <button key={status} type="button" className={buttonClass} data-testid={`beta-feedback-${item.id}-${status}`}
                                    onClick={() => void betaApi.setFeedbackStatus(item.id, status).then(load)
                                        .catch((err) => setError(errorMessage(err, 'common.networkError')))}>
                                {t(`beta.feedback.statuses.${status}`)}
                            </button>
                        ))}
                    </div>
                </article>
            ))}
        </section>
    );
}
