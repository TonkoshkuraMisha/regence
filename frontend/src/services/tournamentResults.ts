// --- FILE: frontend/src/services/tournamentResults.ts ---
// Tournament or arena results for the finish screen (TournamentCelebration): pure functions with no network and no markup.
// From the server table (Tournament.standings / players, Arena.standings) they build the full participant list — place, name,
// rating, points — and the player's summary (points, wins/draws/losses, rating). The single source of truth is the server: here is
// only the layout into rows; bots get names from the i18n catalogs (participantName).

import type {I18n} from '../i18n';
import type {ArenaStanding} from './arenas';
import {participantName, type Tournament} from './tournaments';

/** Row of the final table on the finish screen. */
export interface ResultRow {
    key: string | number;
    place: number;
    name: string;
    rating: number | null;
    /** Points already as text ("2,5", "×" for an eliminated player). */
    score: string;
    /** The player's own row: highlighted and scrolled into view. */
    mine: boolean;
    /** Avatar code (PlayerAvatar); empty — the avatar is derived from the name. */
    avatar?: string | null;
    /** Small caption under the name: wins/draws/losses in a tournament, performance in an arena (like the results popups of chess.com and performance on lichess). */
    detail?: string;
}

/** Player summary: the client supplies captions (keys celebration.stats.*), here only the values. */
export interface ResultStats {
    points: string;
    wins: number;
    draws: number;
    losses: number;
    rating: number | null;
}

/** Whole tournament summary above the table (like the lichess results header): how many games, share of draws and White wins. */
export interface TournamentSummary {
    games: number;
    drawPercent: number;
    whitePercent: number;
}

/** Points as a single number for humans: 3 → "3", 2.5 → "2,5" (a comma — as is customary in chess tables). */
export function formatPoints(points: number): string {
    return String(points).replace('.', ',');
}

/** Wins, draws and losses of a participant over the tournament's played games. */
function seatRecord(tournament: Tournament, seat: number): { wins: number; draws: number; losses: number } {
    let wins = 0;
    let draws = 0;
    let losses = 0;
    for (const g of tournament.games) {
        if (g.result === null || (g.white_seat !== seat && g.black_seat !== seat)) continue;
        if (g.result === '1/2-1/2') draws++;
        else if ((g.result === '1-0') === (g.white_seat === seat)) wins++;
        else losses++;
    }
    return {wins, draws, losses};
}

/** Tournament final table: from the server table, and for knockout (no points table) — from the participants' final places. */
export function tournamentRows(tournament: Tournament, tr: I18n['t'], myName?: string): ResultRow[] {
    const player = (seat: number) => tournament.players.find((p) => p.seat === seat);
    const row = (seat: number, place: number, score: string): ResultRow | null => {
        const p = player(seat);
        if (!p) return null;
        const record = seatRecord(tournament, seat);
        return {
            key: seat, place, name: participantName(p, tr, myName), rating: p.rating, score,
            mine: seat === tournament.my_seat,
            detail: record.wins + record.draws + record.losses > 0 ? `${record.wins}/${record.draws}/${record.losses}` : undefined,
        };
    };
    const rows = tournament.standings.length > 0
        ? tournament.standings.map((s) => row(s.seat, s.place, formatPoints(s.points)))
        : tournament.players.map((p) => row(p.seat, p.place ?? p.seat, p.eliminated_round ? '×' : ''));
    return rows.filter((r): r is ResultRow => r !== null).sort((a, b) => a.place - b.place || Number(b.mine) - Number(a.mine));
}

/** Player summary over the tournament's played games; null — the player did not take part in the tournament. */
export function tournamentStats(tournament: Tournament): ResultStats | null {
    const seat = tournament.my_seat;
    if (seat == null) return null;
    const {wins, draws, losses} = seatRecord(tournament, seat);
    const mine = tournament.standings.find((s) => s.seat === seat);
    const points = mine ? mine.points : wins + draws / 2;
    return {
        points: formatPoints(points), wins, draws, losses,
        rating: tournament.players.find((p) => p.seat === seat)?.rating ?? null,
    };
}

/** Tournament summary: played games, share of draws and White wins; null — no games yet. */
export function tournamentSummary(tournament: Tournament): TournamentSummary | null {
    const played = tournament.games.filter((g) => g.result !== null);
    if (played.length === 0) return null;
    const share = (count: number) => Math.round((100 * count) / played.length);
    return {
        games: played.length,
        drawPercent: share(played.filter((g) => g.result === '1/2-1/2').length),
        whitePercent: share(played.filter((g) => g.result === '1-0').length),
    };
}

/** Arena final table: arena points, the player's rating on entry; the player's own row is determined by the player's name. */
export function arenaRows(standings: ArenaStanding[], myName: string | null | undefined): ResultRow[] {
    return standings.filter((s) => s.games > 0).map((s) => ({
        key: s.username, place: s.place, name: s.username, rating: s.rating, score: String(s.score),
        mine: myName != null && s.username === myName,
        detail: s.performance != null ? `${s.performance}` : undefined,
    }));
}

/** Results table as CSV for download (chess.com provides results as a file): place, participant, rating, points; values in quotes. */
export function resultsCsv(rows: ResultRow[]): string {
    const quote = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`;
    const lines = rows.map((r) => [r.place, r.name, r.rating ?? '', r.score].map(quote).join(','));
    return ['place,name,rating,score', ...lines].join('\r\n');
}
