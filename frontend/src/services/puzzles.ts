// --- FILE: frontend/src/services/puzzles.ts ---
// Puzzles (tasks 13.2–13.3, defense drills 13.6): API client. The solution never comes from the server — only the position,
// the opponent's first move and replies to correct moves.
// All requests go to /api/v1/puzzles and require sign-in (routes in src/api/puzzles.py). The server owns the rules:
// puzzles, solver rating, timed runs and theme stages — src/services/puzzles.py; "Your mistakes" —
// personal_puzzles.py; defense — defense_drills.py; generator drills — generated_drills.py; mate course —
// mate_course.py. Which solver move is expected next is kept by the server in Redis (one active puzzle per player).

import {apiRequest} from './http';

/** A puzzle to solve: the position before the opponent's first move. It contains no solution. */
export interface PuzzleView {
    id: number;
    fen: string;
    /** The opponent's move (UCI) the puzzle starts with: the client shows it, then the solver moves. */
    first_move: string;
    rating: number;
    /** Theme registry codes (src/services/themes.py); names are in the catalog under themes.<code>.name. */
    themes: string[];
    /** The solver's color. */
    color: 'white' | 'black';
    /** How many moves the solver must make. */
    solution_length: number;
    daily?: boolean;
    /** Timed-run state, if the puzzle was issued within one. */
    run?: TimedRun;
    /** Tactic training: the puzzle's stage (mixed set — null). */
    stage?: number | null;
}

/**
 * Timed run (3 or 5 minutes): the server counts the score, mistakes and time left; the client only shows the timer.
 * over — the run is finished: time ran out or three mistakes were made.
 */
export interface TimedRun {
    run_id: string;
    minutes: number;
    solved: number;
    mistakes: number;
    seconds_left: number;
    over: boolean;
}

/**
 * Theme progress after a solved training puzzle. A stage (1–4) is passed when at least pass of the last window puzzles
 * were solved cleanly — without a mistake or a hint; the server sends both numbers (STAGE_WINDOW and STAGE_PASS).
 */
export interface TrainingProgress {
    theme: string;
    stage: number;
    /** Results of the stage's recent puzzles as a string, one character per puzzle (the server keeps it in theme_progress.recent). */
    recent: string;
    mastered: boolean;
    /** With this puzzle the player advanced to the next stage. */
    advanced: boolean;
    window: number;
    pass: number;
}

/** A theme in the training overview (GET /puzzles/training). */
export interface ThemeOverview {
    code: string;
    section: string;
    stage: number;
    recent: string;
    solved: number;
    mastered: boolean;
    /** How many puzzles of the theme exist in the database at each of the four stages. */
    available: [number, number, number, number];
    /** There are enough puzzles at all stages (theme minimums are set in the theme registry) — the theme can be trained. */
    ready: boolean;
}

/** Tactic training overview: the player's progress across all registry themes. */
export interface TrainingOverview {
    window: number;
    pass: number;
    themes: ThemeOverview[];
}

/** Example for demonstrating a tactic (GET /puzzles/demo): the position and the whole solution; it does not count as an attempt. */
export interface DemoExample {
    fen: string;
    moves: string[];
    color: 'white' | 'black';
}

/** Puzzle goals (task 27.8): the solving outcome, derived by the server from the puzzle's themes. */
export const PUZZLE_GOALS = ['mate', 'draw', 'promotion', 'material'] as const;
export type PuzzleGoal = typeof PUZZLE_GOALS[number];

/**
 * What is being trained: a theme (at the player's stage), a section (mixed set) or just a goal with no theme or section
 * (mixed set by goal). blind — "no theme name": the puzzle's themes are hidden until the solution is finished.
 */
export interface TrainingTarget {
    theme?: string;
    section?: string;
    blind: boolean;
    goal?: PuzzleGoal;
}

/** "Your mistakes" (task 13.5): the position before a mistake in the player's game. */
export interface PersonalView {
    id: number;
    /** A game on the site or a game from another site (task 24.1) — exactly one is filled. */
    game_id: number | null;
    imported_game_id?: number | null;
    ply: number;
    fen: string;
    previous_move: string | null;
    color: 'white' | 'black';
    themes: string[];
    attempts: number;
    solved_streak: number;
    /** Where the mistake came from: the opponent (for a bot, its id) and the game date (task B.3). */
    opponent?: string | null;
    opponent_is_bot?: boolean;
    played_at?: string | null;
}

/** Response to an attempt in "Your mistakes": whether it is correct, the best move (solution) and the move played in the game (played). */
export interface PersonalAnswer {
    correct: boolean;
    solution: string;
    played: string;
    /** The puzzle is mastered (solved correctly twice in a row) and is no longer repeated. */
    done: boolean;
    solved_streak: number;
    /** When the puzzle returns for review: the server sets the intervals of 1, 3, 7 and 21 days. */
    next_due_at: string | null;
}

/** "Your mistakes" summary: due now, total in progress, mastered and when the next review is. */
export interface PersonalSummary {
    due: number;
    active: number;
    mastered: number;
    next_due_at: string | null;
}

/** Puzzle result: the solver's rating before and after (Elo against the puzzle rating) and the streak solved without mistakes or hints. */
export interface PuzzleResult {
    solved: boolean;
    rating_before: number;
    rating_after: number;
    delta: number;
    streak: number;
    themes: string[];
    run: TimedRun | null;
    training?: TrainingProgress | null;
}

/**
 * Response to the solver's move. A correct move gives reply: the opponent's reply move (null if this move solved the puzzle).
 * The first mistake ends the puzzle: done, and solution carries the whole solution. result is present only when done.
 */
export interface MoveResponse {
    correct: boolean;
    done: boolean;
    reply: string | null;
    solution: string[] | null;
    result: PuzzleResult | null;
}

/**
 * Hint: the first shows the piece square (from), the second also the move square (to). Hints reduce the rating gain:
 * one halves it, two bring it to zero.
 */
export interface HintResponse {
    from: string;
    to: string | null;
    hints_used: number;
}

/** Solver profile (GET /puzzles/me): puzzle rating, attempt count, streak, run records and recent attempts. */
export interface PuzzleProfile {
    rating: number;
    games: number;
    streak: number;
    /** Personal run records for 3 and 5 minutes. */
    best: { '3': number; '5': number };
    history: {
        puzzle_id: number;
        puzzle_rating: number;
        solved: boolean;
        hints_used: number;
        rating_after: number;
        created_at: string | null;
    }[];
}

/** Timed-run result: score, mistakes and the personal record for this duration (best already includes this run). */
export interface TimedResult {
    score: number;
    mistakes: number;
    minutes: number;
    best: number;
    new_record: boolean;
}

/** A row of the timed-run leaderboard; me — this is the player's own row. */
export interface LeaderRow {
    place: number;
    username: string;
    score: number;
    me: boolean;
}

export type LeaderScope = 'week' | 'all';

/** Leaderboard: the top and the player's own row (if the player is ranked, including below the top). */
export interface TimedLeaders {
    rows: LeaderRow[];
    me: LeaderRow | null;
}

/** Defense drills (task 13.6): "What does the opponent threaten?" and "Don't blunder". */
export type DefenseKind = 'threat' | 'blunder';

/** Registry themes solved by defense drills rather than by database puzzles. */
export const DEFENSE_DRILL_THEMES: Record<string, DefenseKind> = {
    find_the_threat: 'threat',
    blunder_check: 'blunder',
};

/** A defense drill at the player's stage. The threat and the correct moves are not sent in it — only after the answer. */
export interface DefenseDrillView {
    id: number;
    kind: DefenseKind;
    theme: string;
    fen: string;
    color: 'white' | 'black';
    rating: number;
    stage: number;
    /** "Don't blunder": three moves to choose from (UCI). */
    choices: string[];
}

/** First step of "What does the opponent threaten?": whether the square was guessed; the threat itself (the opponent's move, UCI) is revealed either way. */
export interface DefenseThreatResponse {
    correct: boolean;
    threat: string;
    /** Threat motif codes — for the caption. */
    motifs: string[];
}

/** Defense drill result: correct moves, refutations of the wrong ones and theme progress. */
export interface DefenseAnswer {
    correct: boolean;
    /** Solved cleanly — only such a result counts toward the stage. */
    clean: boolean;
    good: string[];
    threat: string | null;
    /** A losing move → the opponent's reply that refutes it. */
    refutations: Record<string, string>;
    motifs: string[];
    training: TrainingProgress;
}

/** Generator drills (task 13.7): a "kind × piece" matrix, levels 1–3. */
export const DRILL_KINDS = ['capture', 'fork', 'check', 'pin', 'safe', 'escape', 'mate1', 'mate2'] as const;
export type DrillKind = typeof DRILL_KINDS[number];
/** Drill piece: queen, rook, bishop, knight; x — a random piece. */
export const DRILL_PIECES = ['q', 'r', 'b', 'n', 'x'] as const;
export type DrillPiece = typeof DRILL_PIECES[number];

/** Registry theme → drill kind (the button in the theme card of "Tactics"). The same table is THEME_DRILLS on the server. */
export const THEME_DRILLS: Record<string, DrillKind> = {
    hanging_piece: 'capture', fork: 'fork', pin: 'pin', basic_mates: 'mate1',
};

/** Whether a drill exists for the "kind × piece" pair: only the knight pin combination is missing — a knight does not pin. */
export function drillSupported(kind: DrillKind, piece: DrillPiece): boolean {
    return !(kind === 'pin' && piece === 'n');
}

/** Generator drill: the position is built by the server from the seed table (data/drills/seeds.json); the solution is not sent. */
export interface DrillView {
    /** Drill key — the client sends it with the answer (POST /puzzles/drills/answer). */
    key: string;
    kind: DrillKind;
    piece: DrillPiece;
    level: number;
    fen: string;
    color: 'white' | 'black';
    /** The piece to solve with (q/r/b/n); for "escape mate" — any. */
    piece_type: string | null;
    /** Solver moves: mate in 2 — two. */
    moves: number;
    run?: DrillRun;
}

/** One-minute drill run: the server counts the score and time; three mistakes or time up — over. */
export interface DrillRun {
    /** The "kind, piece, level" combination — the personal record is kept per combination. */
    combo: string;
    solved: number;
    mistakes: number;
    seconds_left: number;
    over: boolean;
}

/** Response to drill moves — shaped like the puzzle's MoveResponse; within a run it also carries the run state (run). */
export interface DrillAnswer {
    correct: boolean;
    done: boolean;
    reply: string | null;
    solution: string[] | null;
    run: DrillRun | null;
}

/** Drill run result: score and the personal record of the combination (drill_records table). */
export interface DrillRunResult {
    combo: string;
    score: number;
    mistakes: number;
    best: number;
    new_record: boolean;
}

/** Request to /api/v1/puzzles through the shared http.ts wrapper (token, JSON, errors). */
const request = <T>(path: string, init: RequestInit = {}) => apiRequest<T>(`/puzzles${path}`, init);

/**
 * Mate pattern course (task 14.6): patterns in course order and the number of puzzles found for each;
 * tasks — how many puzzles per pattern the player goes through, exam_size and exam_minutes — size and time of the final test.
 */
export interface MateCourseOverview {
    tasks: number;
    exam_size: number;
    exam_minutes: number;
    constructions: { code: string; available: number }[];
}

/** Plan of the course's final test: puzzles of different patterns (theme and puzzle number within its set). */
export interface MateExamPlan {
    minutes: number;
    tasks: { theme: string; index: number }[];
}

/**
 * Puzzle endpoints. Mate course and run puzzles are solved with the same move / hint / giveUp as ordinary ones: a started
 * puzzle becomes the player's active puzzle on the server, and the previous unfinished one is cancelled.
 */
export const puzzlesApi = {
    mateCourse: () => request<MateCourseOverview>('/course/mates'),
    mateExam: () => request<MateExamPlan>('/course/mates/exam'),
    /** Start a course puzzle: the index-th puzzle of the pattern by difficulty; it does not change the puzzle rating. */
    mateTask: (theme: string, index: number) =>
        request<PuzzleView & { course: string; index: number }>(`/course/mates/${encodeURIComponent(theme)}/${index}`),
    /** A puzzle matching the solver's rating (and by theme), excluding recently solved ones. */
    next: (theme?: string | null) => request<PuzzleView>(`/next${theme ? `?theme=${encodeURIComponent(theme)}` : ''}`),
    /** Puzzle of the day — the same for everyone, by UTC date. */
    daily: () => request<PuzzleView>('/daily'),
    move: (id: number, move: string) => request<MoveResponse>(`/${id}/move`, {
        method: 'POST', body: JSON.stringify({move}),
    }),
    hint: (id: number) => request<HintResponse>(`/${id}/hint`, {method: 'POST'}),
    /** "Show solution": the puzzle counts as unsolved. */
    giveUp: (id: number) => request<{ solution: string[]; result: PuzzleResult }>(`/${id}/give-up`, {method: 'POST'}),
    me: () => request<PuzzleProfile>('/me'),
    timedStart: (minutes: 3 | 5) => request<TimedRun>('/timed/start', {
        method: 'POST', body: JSON.stringify({minutes}),
    }),
    /** Next run puzzle: harder with each one solved; run puzzles do not change the solver's rating. */
    timedNext: () => request<PuzzleView & { run: TimedRun }>('/timed/next'),
    /** Run leaderboard: week (Monday UTC) or all-time records. */
    timedLeaders: (minutes: 3 | 5, scope: LeaderScope) => request<TimedLeaders>(`/timed/leaders?minutes=${minutes}&scope=${scope}`),
    timedFinish: () => request<TimedResult>('/timed/finish', {method: 'POST'}),
    /** Tactic training puzzle (GET /puzzles/train) — see TrainingTarget. */
    train: (target: TrainingTarget) => {
        const params = new URLSearchParams();
        if (target.theme) params.set('theme', target.theme);
        if (target.section) params.set('section', target.section);
        if (target.blind) params.set('blind', 'true');
        if (target.goal) params.set('goal', target.goal);
        return request<PuzzleView>(`/train?${params.toString()}`);
    },
    training: () => request<TrainingOverview>('/training'),
    personalSummary: () => request<PersonalSummary>('/personal'),
    personalNext: () => request<PersonalView>('/personal/next'),
    personalAnswer: (id: number, move: string) => request<PersonalAnswer>(`/personal/${id}/answer`, {
        method: 'POST', body: JSON.stringify({move}),
    }),
    /** Plies of the game that the player's puzzles were made from — for the badge in game review. */
    personalPlies: (gameId: number) => request<{ game_id: number; plies: number[] }>(`/personal/game/${gameId}`),
    drillsNext: (kind: DrillKind, piece: DrillPiece, level: number) =>
        request<DrillView>(`/drills/next?kind=${kind}&piece=${piece}&level=${level}`),
    drillsAnswer: (key: string, moves: string[], run = false) => request<DrillAnswer>('/drills/answer', {
        method: 'POST', body: JSON.stringify({key, moves, run}),
    }),
    drillsRunStart: (kind: DrillKind, piece: DrillPiece, level: number) => request<DrillRun>('/drills/run/start', {
        method: 'POST', body: JSON.stringify({kind, piece, level}),
    }),
    drillsRunNext: () => request<DrillView & { run: DrillRun }>('/drills/run/next'),
    drillsRunFinish: () => request<DrillRunResult>('/drills/run/finish', {method: 'POST'}),
    /** Personal run records by combination and the "theme → drill kind" table from the server. */
    drillsRecords: () => request<{ records: Record<string, number>; themes: Record<string, DrillKind> }>('/drills/records'),
    defenseNext: (kind: DefenseKind) => request<DefenseDrillView>(`/defense/next?kind=${kind}`),
    /** "What does the opponent threaten?", first step: square — the square of the attacking piece or of the attack. */
    defenseThreat: (id: number, square: string) => request<DefenseThreatResponse>(`/defense/${id}/threat`, {
        method: 'POST', body: JSON.stringify({square}),
    }),
    defenseAnswer: (id: number, move: string) => request<DefenseAnswer>(`/defense/${id}/answer`, {
        method: 'POST', body: JSON.stringify({move}),
    }),
    demo: (theme: string) => request<{ theme: string; examples: DemoExample[] }>(
        `/demo?theme=${encodeURIComponent(theme)}`,
    ),
};
