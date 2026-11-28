// --- FILE: frontend/src/components/gameImport/DailyImport.tsx ---
// "Import every day" (task 24.1): under the site form of ImportPage the player turns on the daily import from the chosen
// site with the username typed in the form. The server imports on a schedule (src/services/game_import_schedule.py,
// once a day); here the player sees the username followed and how the last run went (when, how many games, or why it
// failed - a serverErrors.* code). Data: services/gameImport.ts (/api/v1/imports/subscriptions).

import {useEffect, useState} from 'react';
import {format, parseISO} from 'date-fns';
import {renderUiMessage, useI18n} from '../../i18n';
import type {MessageKey, UiMessage} from '../../i18n';
import {errorMessage} from '../../services/apiErrors';
import {importApi} from '../../services/gameImport';
import type {ImportSource, ImportSubscriptionView} from '../../services/gameImport';

/** Props: the site of the open tab, the username typed in the form and the storage limit (for the "storage full" text). */
interface Props {
    source: ImportSource;
    nick: string;
    maxStored: number;
}

/** The daily import switch for one site and the state of its last run. */
export function DailyImport({source, nick, maxStored}: Props) {
    const {t, tp, dateLocale} = useI18n();
    const [subscriptions, setSubscriptions] = useState<ImportSubscriptionView[] | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<UiMessage | null>(null);

    useEffect(() => {
        let alive = true;
        importApi.subscriptions().then((body) => alive && setSubscriptions(body.subscriptions ?? [])).catch(() => undefined);
        return () => {
            alive = false;
        };
    }, []);

    if (subscriptions === null) return null;
    const current = subscriptions.find((s) => s.source === source) ?? null;
    const valid = /^[A-Za-z0-9_-]{2,30}$/.test(nick.trim());
    const site = t(`gameImport.source.${source}`);

    const turnOn = async () => {
        setBusy(true);
        setError(null);
        try {
            const saved = await importApi.subscribe(source, nick.trim());
            setSubscriptions((list) => [...(list ?? []).filter((s) => s.source !== source), saved]);
        } catch (err) {
            setError(errorMessage(err, 'common.networkError'));
        } finally {
            setBusy(false);
        }
    };
    const turnOff = async () => {
        setBusy(true);
        setError(null);
        try {
            await importApi.unsubscribe(source);
            setSubscriptions((list) => (list ?? []).filter((s) => s.source !== source));
        } catch (err) {
            setError(errorMessage(err, 'common.networkError'));
        } finally {
            setBusy(false);
        }
    };

    const lastRun = current?.last_run_at
        ? (current.last_error
            ? t('gameImport.daily.failed', {
                date: format(parseISO(current.last_run_at), 'd MMM, HH:mm', {locale: dateLocale}),
                reason: t(`serverErrors.${current.last_error}` as MessageKey, {max: maxStored, retry_after: ''}),
            })
            : t('gameImport.daily.lastRun', {
                date: format(parseISO(current.last_run_at), 'd MMM, HH:mm', {locale: dateLocale}),
                games: tp('gameImport.daily.games', current.last_added),
            }))
        : t('gameImport.daily.waiting');

    return (
        <div className="flex flex-col gap-1 text-sm border-t border-amber-900/40 pt-2" data-testid="daily-import">
            {current ? (
                <div className="flex flex-wrap items-center gap-2">
                    <span className="text-emerald-300" data-testid="daily-on">{t('gameImport.daily.on', {site, username: current.username})}</span>
                    {valid && nick.trim() !== current.username && (
                        <button type="button" disabled={busy} onClick={() => void turnOn()} data-testid="daily-change"
                                className="px-2 py-1 rounded border border-amber-700 cursor-pointer disabled:opacity-40">
                            {t('gameImport.daily.change', {username: nick.trim()})}
                        </button>
                    )}
                    <button type="button" disabled={busy} onClick={() => void turnOff()} data-testid="daily-off"
                            className="px-2 py-1 rounded border border-amber-900/60 cursor-pointer disabled:opacity-40">
                        {t('gameImport.daily.turnOff')}
                    </button>
                </div>
            ) : (
                <button type="button" disabled={busy || !valid} onClick={() => void turnOn()} data-testid="daily-turn-on"
                        className="self-start px-3 py-1 rounded border border-amber-700 hover:border-amber-400 cursor-pointer disabled:opacity-40">
                    {t('gameImport.daily.turnOn', {site})}
                </button>
            )}
            <p className="text-xs text-boxwood/70" data-testid="daily-status">{current ? lastRun : t('gameImport.daily.note')}</p>
            {error && <p className="text-xs text-red-300" role="alert">{renderUiMessage(error, t)}</p>}
        </div>
    );
}
