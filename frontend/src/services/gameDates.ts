// --- FILE: frontend/src/services/gameDates.ts ---
// Game date for lists and viewing. Taken from the PGN Date header: for historical games the month and day are often
// unknown, and «1860.??.??» is shown as «1860»; an unknown year («????») — there is no date from the PGN. Then — the server's
// game end time (finished_at, ISO), in the format «d MMM yyyy» in the player's language. No network needed.
// Called by Profile.tsx, ChampionGames.tsx and GameViewer.tsx — each has its own text for the case when there is no date.

import {format, parseISO} from 'date-fns';
import type {Locale} from 'date-fns';

/** Date from the PGN header without unknown parts; null — there is no date or the year is unknown. */
export function pgnDisplayDate(pgnDate: string | null | undefined): string | null {
    if (!pgnDate || pgnDate.includes('????')) return null;
    return pgnDate.replace(/\?/g, '').replace(/\.+$/, '');
}

/** Game date for display: from the PGN, otherwise from finished_at; null — neither exists. */
export function gameDisplayDate(pgnDate: string | null | undefined, finishedAt: string | null | undefined,
                                locale: Locale): string | null {
    return pgnDisplayDate(pgnDate) ?? (finishedAt ? format(parseISO(finishedAt), 'd MMM yyyy', {locale}) : null);
}
