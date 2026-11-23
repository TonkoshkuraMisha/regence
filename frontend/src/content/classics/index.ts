// --- FILE: frontend/src/content/classics/index.ts ---
// Master games with explanations (task 14.7): the JSON files of this folder are produced by scripts/build_classics.py - moves, engine
// evaluations, coach comments (catalog keys coach.*), "what would you play?" stops. The intro and summary texts are
// authored, in several languages. Files load on demand: they do not enter the main bundle.

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

export function progressId(id: string): string {
    return `classics-${id}`.slice(0, 64);
}
