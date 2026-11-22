// --- FILE: frontend/src/components/social/ViolationsSummary.tsx ---
// Сводка по нарушениям за 30 суток для модератора (таск 26.4): поступило и закрыто заявок, очередь и возраст самой
// старой, помеченные нарушители, разбивка по видам и решениям, игроки с наибольшим числом жалоб. Данные —
// GET /moderation/summary (src/services/moderation_report.py); названия видов и решений — из moderation.kinds/actions.

import {useEffect, useState} from 'react';
import {useI18n} from '../../i18n';
import type {MessageKey} from '../../i18n';
import {moderationApi} from '../../services/moderation';
import type {ViolationsSummary as Summary} from '../../services/moderation';

export function ViolationsSummary() {
    const {t} = useI18n();
    const [data, setData] = useState<Summary | null>(null);

    useEffect(() => {
        let cancelled = false;
        moderationApi.summary().then((r) => { if (!cancelled) setData(r); }).catch(() => undefined);
        return () => { cancelled = true; };
    }, []);

    if (!data) return null;
    const counts = (group: 'kinds' | 'actions', values: Record<string, number>) =>
        Object.entries(values).map(([code, n]) => `${t(`moderation.${group}.${code}` as MessageKey)}: ${n}`).join(' · ');
    return (
        <section className="bg-black/30 rounded p-4 flex flex-col gap-1.5 text-sm" data-testid="violations-summary">
            <h2 className="font-bold text-amber-200">{t('moderation.summary.title', {days: data.days})}</h2>
            <p data-testid="summary-totals">{t('moderation.summary.totals', {opened: data.opened, resolved: data.resolved, open: data.open_now})}</p>
            {data.oldest_open_hours !== null && <p>{t('moderation.summary.oldest', {hours: data.oldest_open_hours})}</p>}
            <p>{t('moderation.summary.cheaters', {n: data.cheaters})}</p>
            {Object.keys(data.by_kind).length > 0 && <p data-testid="summary-kinds">{counts('kinds', data.by_kind)}</p>}
            {Object.keys(data.by_action).length > 0 && <p data-testid="summary-actions">{counts('actions', data.by_action)}</p>}
            {data.top_targets.length > 0 && (
                <p data-testid="summary-top">{t('moderation.summary.top')} {data.top_targets.map((x) => `${x.username} (${x.reports})`).join(', ')}</p>
            )}
        </section>
    );
}
