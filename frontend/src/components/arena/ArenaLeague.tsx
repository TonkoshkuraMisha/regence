// --- FILE: frontend/src/components/arena/ArenaLeague.tsx ---
// Monthly arena league (task 33.5) on the /arenas page: players by the sum of the month's arena points in one time control category.
// The table is computed by the server (GET /api/v1/arenas/league, src/services/arena_league.py): arenas only, no Swiss events,
// the category tabs are those in which the schedule creates arenas. The league does not affect the rating. A signed-in player sees their own
// row under the table even if they are below the top places.

import {useEffect, useState} from 'react';
import {Medal} from 'lucide-react';
import {useI18n} from '../../i18n';
import {arenasApi} from '../../services/arenas';
import type {ArenaLeague as LeagueData, LeagueCategory, LeagueRow} from '../../services/arenas';
import {EmptyState, SegmentedControl, Section} from '../ui';

// Time control category the league opens with (if the server gave no other tabs).
const DEFAULT_CATEGORY: LeagueCategory = 'blitz';

/** Monthly arena league block: category tabs (if there is more than one), the table and one's own row under it. Rendered in ArenasPage. */
export function ArenaLeague() {
    const {t} = useI18n();
    const [category, setCategory] = useState<LeagueCategory>(DEFAULT_CATEGORY);
    const [data, setData] = useState<LeagueData | null>(null);

    useEffect(() => {
        let alive = true;
        arenasApi.league(category).then((next) => alive && setData(next)).catch(() => undefined);
        return () => {
            alive = false;
        };
    }, [category]);

    const table = data?.table ?? [];
    const categories = data?.categories ?? [];
    const me = data?.me ?? null;
    const meShown = me !== null && table.some((row) => row.username === me.username);

    const line = (row: LeagueRow, own: boolean) => (
        <tr key={`${row.place}-${row.username}`} className={own ? 'text-amber-200 font-bold' : ''}
            data-testid={own ? 'league-me' : `league-row-${row.place}`}>
            <td className="pr-2">{row.place}</td>
            <td className="pr-2 break-all">{row.username}</td>
            <td className="pr-2 text-right">{row.score}</td>
            <td className="pr-2 text-right">{row.best}</td>
            <td className="text-right">{row.arenas}</td>
        </tr>
    );

    return (
        <Section title={t('arenas.league.title')} aside={data ? t('arenas.league.season', {season: data.season}) : undefined}
                 testId="arena-league">
            <p className="text-sm text-boxwood/75">{t('arenas.league.intro')}</p>
            {categories.length > 1 && (
                <SegmentedControl<LeagueCategory> label={t('arenas.league.title')} value={category} onChange={setCategory}
                                  testIdPrefix="league-category"
                                  options={categories.map((id) => ({id, label: t(`ratingCategory.${id}`)}))}/>
            )}
            {table.length === 0 ? (
                <EmptyState icon={<Medal size={28}/>} title={t('arenas.league.empty')} description={t('arenas.league.emptyText')}/>
            ) : (
                <table className="w-full text-sm" data-testid="league-table">
                    <thead>
                        <tr className="text-left text-boxwood/70">
                            <th>#</th><th>{t('arenas.league.player')}</th>
                            <th className="text-right">{t('arenas.score')}</th>
                            <th className="text-right">{t('arenas.league.best')}</th>
                            <th className="text-right">{t('arenas.league.arenas')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table.map((row) => line(row, row.username === me?.username))}
                        {me && !meShown && line(me, true)}
                    </tbody>
                </table>
            )}
        </Section>
    );
}
