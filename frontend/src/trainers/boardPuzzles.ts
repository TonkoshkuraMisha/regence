// --- FILE: frontend/src/trainers/boardPuzzles.ts ---
// Board puzzles (task 19.4): placements ("Eight queens", rooks, bishops, knights, domination) and the "Knight's tour".
// Squares - [column, row] pairs from 0; board N x N. Checks are pure functions (tests: all 92 solutions, domination, tour).

export type Piece = 'Q' | 'R' | 'B' | 'N';
export type Cell = [number, number];

export interface PlacementPuzzle {
    id: string;
    piece: Piece;
    count: number;
    size: number;
    /** independent - pieces do not attack each other; dominate - every square is occupied or attacked. */
    goal: 'independent' | 'dominate';
}

/** Order - trainer level (1 - easiest). */
export const PLACEMENT_PUZZLES: PlacementPuzzle[] = [
    {id: 'queens4', piece: 'Q', count: 4, size: 4, goal: 'independent'},
    {id: 'queens5', piece: 'Q', count: 5, size: 5, goal: 'independent'},
    {id: 'queens6', piece: 'Q', count: 6, size: 6, goal: 'independent'},
    {id: 'rooks8', piece: 'R', count: 8, size: 8, goal: 'independent'},
    {id: 'queens7', piece: 'Q', count: 7, size: 7, goal: 'independent'},
    {id: 'queens8', piece: 'Q', count: 8, size: 8, goal: 'independent'},
    {id: 'bishops14', piece: 'B', count: 14, size: 8, goal: 'independent'},
    {id: 'knights32', piece: 'N', count: 32, size: 8, goal: 'independent'},
    {id: 'knights12', piece: 'N', count: 12, size: 8, goal: 'dominate'},
    {id: 'queens5dom', piece: 'Q', count: 5, size: 8, goal: 'dominate'},
];

export function placementPuzzle(level: number): PlacementPuzzle {
    return PLACEMENT_PUZZLES[Math.min(PLACEMENT_PUZZLES.length, Math.max(1, level)) - 1];
}

const KNIGHT: Cell[] = [[1, 2], [2, 1], [2, -1], [1, -2], [-1, -2], [-2, -1], [-2, 1], [-1, 2]];
const LINES: Record<'Q' | 'R' | 'B', Cell[]> = {
    R: [[1, 0], [-1, 0], [0, 1], [0, -1]],
    B: [[1, 1], [1, -1], [-1, 1], [-1, -1]],
    Q: [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]],
};

export const key = ([x, y]: Cell) => `${x},${y}`;
const inside = ([x, y]: Cell, size: number) => x >= 0 && y >= 0 && x < size && y < size;

/** Squares attacked by the piece from square `from`; lines stop at occupied squares (those are attacked too). */
export function attacks(piece: Piece, from: Cell, size: number, occupied: Set<string> = new Set()): Cell[] {
    if (piece === 'N') return KNIGHT.map(([dx, dy]) => [from[0] + dx, from[1] + dy] as Cell).filter((c) => inside(c, size));
    const result: Cell[] = [];
    for (const [dx, dy] of LINES[piece]) {
        let cell: Cell = [from[0] + dx, from[1] + dy];
        while (inside(cell, size)) {
            result.push(cell);
            if (occupied.has(key(cell))) break;
            cell = [cell[0] + dx, cell[1] + dy];
        }
    }
    return result;
}

/** Pairs of pieces attacking each other (for highlighting). */
export function conflicts(piece: Piece, cells: Cell[], size: number): Set<string> {
    const occupied = new Set(cells.map(key));
    const bad = new Set<string>();
    for (const cell of cells) {
        for (const target of attacks(piece, cell, size, occupied)) {
            if (occupied.has(key(target))) {
                bad.add(key(cell));
                bad.add(key(target));
            }
        }
    }
    return bad;
}

/** Squares that are neither occupied nor attacked (for domination). */
export function uncovered(piece: Piece, cells: Cell[], size: number): Cell[] {
    const occupied = new Set(cells.map(key));
    const covered = new Set(occupied);
    for (const cell of cells) for (const target of attacks(piece, cell, size, occupied)) covered.add(key(target));
    const result: Cell[] = [];
    for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) if (!covered.has(key([x, y]))) result.push([x, y]);
    return result;
}

export function isSolved(puzzle: PlacementPuzzle, cells: Cell[]): boolean {
    if (cells.length !== puzzle.count) return false;
    if (puzzle.goal === 'independent') return conflicts(puzzle.piece, cells, puzzle.size).size === 0;
    return uncovered(puzzle.piece, cells, puzzle.size).length === 0;
}

/** Solution key - to count distinct solutions found. */
export function solutionKey(cells: Cell[]): string {
    return cells.map(key).sort().join(';');
}

/** All solutions of the N queens problem (for 8x8 - 92). */
export function allQueenSolutions(size: number): Cell[][] {
    const solutions: Cell[][] = [];
    const cols: number[] = [];
    const place = (row: number) => {
        if (row === size) {
            solutions.push(cols.map((x, y) => [x, y] as Cell));
            return;
        }
        for (let x = 0; x < size; x++) {
            if (cols.every((cx, cy) => cx !== x && Math.abs(cx - x) !== row - cy)) {
                cols.push(x);
                place(row + 1);
                cols.pop();
            }
        }
    };
    place(0);
    return solutions;
}

// ---- Knight's tour ----

export const TOUR_SIZES = [5, 6, 8];

export function tourSize(level: number): number {
    return TOUR_SIZES[Math.min(TOUR_SIZES.length, Math.max(1, level)) - 1];
}

export function knightMoves(from: Cell, size: number, visited: Set<string>): Cell[] {
    return attacks('N', from, size).filter((c) => !visited.has(key(c)));
}

export function isKnightMove(a: Cell, b: Cell): boolean {
    const dx = Math.abs(a[0] - b[0]);
    const dy = Math.abs(a[1] - b[1]);
    return (dx === 1 && dy === 2) || (dx === 2 && dy === 1);
}

/** Warnsdorff's rule hint: the move to the square with the fewest onward moves (on a tie - the first). */
export function warnsdorffHint(path: Cell[], size: number): Cell | null {
    const visited = new Set(path.map(key));
    const options = knightMoves(path[path.length - 1], size, visited);
    if (options.length === 0) return null;
    let best = options[0];
    let bestDegree = Infinity;
    for (const option of options) {
        const degree = knightMoves(option, size, new Set([...visited, key(option)])).length;
        if (degree < bestDegree) {
            bestDegree = degree;
            best = option;
        }
    }
    return best;
}

/** A tour is valid: every square once, every step is a knight move. */
export function isTour(path: Cell[], size: number): boolean {
    if (path.length !== size * size || new Set(path.map(key)).size !== path.length) return false;
    return path.every((cell, i) => inside(cell, size) && (i === 0 || isKnightMove(path[i - 1], cell)));
}

export function isClosedTour(path: Cell[], size: number): boolean {
    return isTour(path, size) && isKnightMove(path[path.length - 1], path[0]);
}

export const CLOSED_TOUR_SCORE = 200;
export const OPEN_TOUR_SCORE = 100;
