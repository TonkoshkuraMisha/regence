// --- FILE: frontend/src/components/WeekSummaryCard.tsx ---
// «Моя неделя»: итоги последних 7 суток игрока — партии (победы, ничьи, поражения, изменение рейтинга), задачи, дни
// активности — и один совет. Данные и совет-код отдаёт сервер (GET /workout/week, src/services/weekly_summary.py);
// текст совета собирается здесь по коду weekly.advice.<код>. Показывается под планом разминки на /workout; при ошибке
// сети блока просто нет.

import {useEffect, useState} from 'react';
import {useI18n} from '../i18n';
import type {MessageKey} from '../i18n';
import {fetchWeekSummary} from '../services/workout';
import type {WeekSummary} from '../services/workout';

export function WeekSummaryCard() {
    const {t} = useI18n();
    const [week, setWeek] = useState<WeekSummary | null>(null);

    useEffect(() => {
        let cancelled = false;
        fetchWeekSummary().then((r) => { if (!cancelled) setWeek(r); }).catch(() => undefined);
        return () => { cancelled = true; };
    }, []);

    if (!week) return null;
    const {games, puzzles} = week;
    const sign = games.rating_delta > 0 ? '+' : '';
    return (
        <section className="mt-6 bg-black/30 rounded p-4 flex flex-col gap-2" data-testid="week-summary">
            <h2 className="text-sm uppercase tracking-widest text-amber-500/80 font-bold">{t('weekly.title')}</h2>
            <ul className="text-sm flex flex-col gap-1">
                <li data-testid="week-games">{t('weekly.games', {total: games.total, wins: games.wins, draws: games.draws, losses: games.losses})}
                    {games.total > 0 && <span className="ml-2 font-mono">{sign}{games.rating_delta}</span>}</li>
                <li data-testid="week-puzzles">{t('weekly.puzzles', {solved: puzzles.solved, attempts: puzzles.attempts})}</li>
                <li data-testid="week-days">{t('weekly.days', {days: week.days_active, streak: week.streak})}</li>
            </ul>
            <p className="text-amber-200" data-testid="week-advice">{t(`weekly.advice.${week.advice}` as MessageKey)}</p>
        </section>
    );
}
