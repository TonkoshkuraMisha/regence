// --- FILE: frontend/src/content/classics/index.ts ---
// Master games with explanations (task 14.7): the JSON files of this folder are produced by scripts/build_classics.py - moves, engine
// evaluations, coach comments (catalog keys coach.*), "what would you play?" stops. The intro and summary texts are
// authored, in en and uk. Files load on demand: they do not enter the main bundle. Games come from the champions' archive
// or, with --library / --pgn, from the game library or a PGN file (field source).
// A game opens with stops by default; classicLink(id, {demo: true}) opens it as a demonstration - moves with comments, no questions.

import type {Language} from '../../i18n';
import type {CoachComment} from '../../services/coach';

export interface ClassicStop {
    /** Ply of the game (0 - White's first move): the position before it. */
    ply: number;
    move: string;
    best_cp: number;
    gap_cp: number;
    lines: [string, number][];
}

export interface ClassicGame {
    id: string;
    white: string;
    black: string;
    event: string | null;
    year: string | null;
    result: string;
    moves: string[];
    /** Evaluation after each ply, from White's point of view, in centipawns. */
    evals: number[];
    /** Coach comment on a ply (key - ply number). */
    comments: Record<string, CoachComment>;
    stops: ClassicStop[];
    /** Where a chosen game came from (build_classics.py --library / --pgn): the library moves_hash or the PGN file name. */
    source?: { library?: string; pgn?: string };
    intro: Record<Language, string>;
    summary: Record<Language, string>;
}

const modules = import.meta.glob<ClassicGame>('./*.json', {import: 'default'});

export const CLASSIC_IDS: string[] = Object.keys(modules).map((path) => path.slice(2, -5)).sort();

export async function loadClassic(id: string): Promise<ClassicGame | null> {
    const load = modules[`./${id}.json`];
    return load ? load() : null;
}

export async function loadAllClassics(): Promise<ClassicGame[]> {
    const games = await Promise.all(CLASSIC_IDS.map((id) => loadClassic(id)));
    return games
        .filter((game): game is ClassicGame => game !== null)
        .sort((a, b) => Number(a.year ?? 0) - Number(b.year ?? 0) || a.id.localeCompare(b.id));
}

/** Points for an answer at a stop - the same rules as in "Guess the master's move" (src/services/guess.py). */
export function scoreStop(stop: ClassicStop, uci: string): { score: number; loss: number } {
    if (uci === stop.move) return {score: 100, loss: 0};
    const known = new Map(stop.lines.map(([move, cp]) => [move, cp]));
    const loss = Math.max(0, known.has(uci) ? stop.best_cp - known.get(uci)! : stop.gap_cp + 50);
    if (loss <= 30) return {score: 80, loss};
    return {score: Math.max(0, 80 - Math.floor((loss - 30) / 5)), loss};
}

/**
 * Short title of a game by its id "white-black-year" (the file name): "Tolush – Keres, 1947". Used where the game file is
 * not loaded yet (a Big course step label); the course test checks it against the players and year of every game the course links.
 */
export function classicIdTitle(id: string): string {
    const parts = id.split('-');
    const year = /^\d{4}$/.test(parts[parts.length - 1]) ? parts.pop() : undefined;
    const names = parts.map((name) => name.charAt(0).toUpperCase() + name.slice(1)).join(' – ');
    return year ? `${names}, ${year}` : names;
}

/** Query parameter of the game page that switches the stops off: ?stops=off - a demonstration (Big course step "demo"). */
const STOPS_PARAM = 'stops';
const STOPS_OFF = 'off';

/** Link to a game page; demo - without "what would you play?" stops (the toggle on the page still turns them on). */
export function classicLink(id: string, options: { demo?: boolean } = {}): string {
    const path = `/learn/classics/${id}`;
    return options.demo ? `${path}?${STOPS_PARAM}=${STOPS_OFF}` : path;
}

/** Whether the game page starts with stops: yes, unless the link is a demonstration (classicLink with demo). */
export function startsWithStops(params: URLSearchParams): boolean {
    return params.get(STOPS_PARAM) !== STOPS_OFF;
}

export function progressId(id: string): string {
    return `classics-${id}`.slice(0, 64);
}
