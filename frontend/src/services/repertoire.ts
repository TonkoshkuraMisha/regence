// --- FILE: frontend/src/services/repertoire.ts ---
// Opening repertoire (task 20.1): /api/v1/repertoires — own lines for White or Black, six starter sets,
// adding lines (UCI from the initial position or PGN text), comments and deleting a move with the branches behind it.
// The server sends position-graph edges with SAN and the position key after the move — the client walks them without computing keys.
// Routes — src/api/repertoire.py; graph — src/services/repertoire.py, SM-2 scheduled review and play
// against the repertoire — repertoire_drill.py, deviations in a played game — repertoire_deviations.py. Everything except
// the starter set list requires sign-in; the opponent reply (opponent) is closed during a game with a human.

import {apiRequest} from './http';

export type RepertoireColor = 'white' | 'black';
/** Server starter set codes (src/services/repertoire_starters.py); names and intro texts are in the catalog. */
export const STARTER_IDS = ['italian', 'london', 'open_games', 'queens_gambit', 'caro_kann', 'nimzo_indian'] as const;
export type StarterId = typeof STARTER_IDS[number];

/** Starter set: ready-made lines (each is UCI moves from the initial position), side and level. */
export interface Starter {
    id: StarterId;
    color: RepertoireColor;
    level: 'beginner' | 'intermediate' | 'advanced';
    /** Set style (27.10); an old server may lack it. */
    style?: 'attacking' | 'positional';
    lines: string[][];
}

/** Repertoire in the list: moves — the number of moves (edges) in it. */
export interface RepertoireSummary {
    id: number;
    name: string;
    color: RepertoireColor;
    /** Which starter set it was copied from; null — built from scratch. */
    starter: StarterId | null;
    moves: number;
}

/** Graph edge: move uci from position position leads to position child. Position keys are computed by the server (EPD). */
export interface RepertoireEdge {
    position: string;
    uci: string;
    san: string;
    child: string;
    /** The player's own comment on the move; an empty string — no comment. */
    comment: string;
    /** A move of the repertoire's side (not the opponent's reply). */
    mine: boolean;
}

/** Whole repertoire: all graph edges and the key of the initial position (root) the traversal starts from. */
export interface Repertoire {
    id: number;
    name: string;
    color: RepertoireColor;
    starter: StarterId | null;
    root: string;
    moves: RepertoireEdge[];
}

/** Request to /api/v1/repertoires through the shared http.ts wrapper (token, JSON, errors). */
const call = <T>(path: string, init: RequestInit = {}) => apiRequest<T>(`/repertoires${path}`, init);

const json = (method: string, body: object): RequestInit => ({method, body: JSON.stringify(body)});

// --- Deviations in games (task 20.3) ---

/** The first place where the played game left one of the player's repertoires (by positions, accounting for transpositions). */
export interface Deviation {
    repertoire_id: number;
    name: string;
    starter: StarterId | null;
    /**
     * you_left — the player played a move outside the repertoire; opponent_new — the opponent played a move not in the repertoire;
     * end — the game reached the end of the prepared line; followed — the whole game followed the repertoire.
     */
    kind: 'you_left' | 'opponent_new' | 'end' | 'followed';
    /** Ply of the game (from 1); for followed — the game length. */
    ply: number;
    /** The move played in the game (SAN and UCI) and the moves the repertoire expected (SAN). */
    played: string | null;
    played_uci: string | null;
    expected: string[];
    /** Moves up to the deviation position. */
    line: string[];
    position: string;
}

/** "3." for a White move, "1…" for a Black move — the move number from the ply. */
export function moveLabel(ply: number): string {
    return `${Math.ceil(ply / 2)}${ply % 2 ? '.' : '…'}`;
}

// --- Review (task 20.2) ---

/** Review card state: not shown yet, learning, learned. */
export type CardStatus = 'new' | 'learning' | 'learned';

/** Repertoire card counters. The daily quota of new cards is set by the server (NEW_PER_DAY in repertoire_drill.py). */
export interface DrillStats {
    total: number;
    new: number;
    learning: number;
    learned: number;
    /** Overdue for review now. */
    due: number;
    /** How many new cards can still be taken today. */
    new_left: number;
}

/** Correct card answer — one of the repertoire's own moves in this position. */
export interface DrillAnswerOption {
    uci: string;
    san: string;
    comment: string;
}

/** "Find your move" card: a repertoire position where the player is to move; all of the player's moves from it are correct (answers). */
export interface DrillCard {
    position: string;
    /** Moves from the initial position to the card. */
    line: string[];
    fen: string;
    answers: DrillAnswerOption[];
    status: CardStatus;
}

/** Card answer result: the new state and the next review date per the SM-2 schedule (computed by the server). */
export interface DrillAnswer {
    correct: boolean;
    answers: DrillAnswerOption[];
    status: CardStatus;
    due_at: string | null;
    stats: DrillStats;
}

export const repertoireApi = {
    starters: () => call<{ starters: Starter[] }>('/starters'),
    list: () => call<{ repertoires: RepertoireSummary[] }>(''),
    /** New repertoire: empty (name, color) or a copy of a starter set (starter — the side is taken from it). */
    create: (body: { name?: string; color?: RepertoireColor; starter?: StarterId }) => call<Repertoire>('', json('POST', body)),
    get: (id: number) => call<Repertoire>(`/${id}`),
    rename: (id: number, name: string) => call<{ id: number; name: string }>(`/${id}`, json('PATCH', {name})),
    remove: (id: number) => call<{ deleted: boolean }>(`/${id}`, {method: 'DELETE'}),
    /** Add a line (UCI from the initial position) or lines from PGN; added — how many moves turned out to be new. */
    addLine: (id: number, moves: string[]) => call<Repertoire & { added: number }>(`/${id}/lines`, json('POST', {moves})),
    importPgn: (id: number, pgn: string) => call<Repertoire & { added: number }>(`/${id}/pgn`, json('POST', {pgn})),
    comment: (id: number, position: string, uci: string, comment: string) =>
        call<{ comment: string }>(`/${id}/comment`, json('PUT', {position, uci, comment})),
    /** Remove a move and the branches behind it — except positions reachable by another move order. */
    removeMove: (id: number, position: string, uci: string) =>
        call<Repertoire & { removed: number }>(`/${id}/remove`, json('POST', {position, uci})),
    /** Session cards: review — scheduled and new within the daily quota, learn — new lines. */
    drill: (id: number, mode: 'review' | 'learn') => call<{ stats: DrillStats; cards: DrillCard[] }>(`/${id}/drill?mode=${mode}`),
    /** retry — repeating a card after a mistake in the same session: it does not change the schedule. */
    answer: (id: number, position: string, uci: string, retry: boolean) =>
        call<DrillAnswer>(`/${id}/drill/answer`, json('POST', {position, uci, retry})),
    /** Put a position card into today's review (the "Practice" button after a game, task 20.3). */
    focus: (id: number, position: string) => call<{ ok: boolean }>(`/${id}/drill/focus`, json('POST', {position})),
    /** Deviations of the player's own finished game from the repertoires of its color. */
    deviations: (gameId: number | string) => call<{ color: RepertoireColor; results: Deviation[] }>(`/game/${gameId}/deviations`),
    /**
     * "Play against the repertoire": the opponent's reply after the player's line — from the repertoire's replies, preferring the one popular among
     * people (by the position index). reply = null — no replies, the line is complete.
     */
    opponent: (id: number, moves: string[]) =>
        call<{ reply: string | null; san: string | null }>(`/${id}/opponent`, json('POST', {moves})),
};

/** Edges from a position: own moves first. */
export function edgesFrom(repertoire: Repertoire, position: string): RepertoireEdge[] {
    return repertoire.moves.filter((m) => m.position === position).sort((a, b) => Number(b.mine) - Number(a.mine));
}

/**
 * Where a line (UCI from the initial position) leaves the repertoire: the key of the last known position and the number of the line's moves
 * already in the repertoire. As long as all moves follow edges, the position is known without chess logic on the client.
 */
export function followLine(repertoire: Repertoire, line: string[]): { position: string; known: number } {
    let position = repertoire.root;
    for (let i = 0; i < line.length; i++) {
        const edge = repertoire.moves.find((m) => m.position === position && m.uci === line[i]);
        if (!edge) return {position, known: i};
        position = edge.child;
    }
    return {position, known: line.length};
}
