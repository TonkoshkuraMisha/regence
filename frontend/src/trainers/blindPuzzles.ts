// --- FILE: frontend/src/trainers/blindPuzzles.ts ---
// Blind puzzles and visualization (task 19.6). Source - "what would you play?" stops in classic games (14.7): each
// has a known best move and evaluations of alternatives. The position N plies before the stop is shown, then the board
// is hidden, N moves are announced in notation, and the player makes a move on an empty board (evaluated as in classic stops).
// "Where is the piece?": after the same N moves, point to the square of the named piece.

import {Chess} from 'chess.js';
import type {ClassicGame, ClassicStop} from '../content/classics';
import {rng} from './vision';

export interface BlindTask {
    game: ClassicGame;
    stop: ClassicStop;
    startFen: string;
    /** Announced moves in SAN, with numbers ("12. Nf3", "12... e5"). */
    moves: string[];
    finalFen: string;
    /** Side that moves in the final position. */
    side: 'white' | 'black';
}

/** N - level (1-10 plies blind). */
export function blindPlies(level: number): number {
    return Math.min(10, Math.max(1, level));
}

function play(game: ClassicGame, plies: number): Chess {
    const board = new Chess();
    for (const uci of game.moves.slice(0, plies)) board.move({from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4]});
    return board;
}

export function blindTask(games: ClassicGame[], level: number, seed: number, round: number): BlindTask | null {
    const n = blindPlies(level);
    const stops = games.flatMap((game) => game.stops.filter((stop) => stop.ply >= n).map((stop) => ({game, stop})));
    if (stops.length === 0) return null;
    const {game, stop} = stops[Math.floor(rng(seed * 31 + round * 977 + n)() * stops.length)];
    const board = play(game, stop.ply - n);
    const startFen = board.fen();
    const moves: string[] = [];
    for (const uci of game.moves.slice(stop.ply - n, stop.ply)) {
        const number = board.moveNumber();
        const white = board.turn() === 'w';
        const made = board.move({from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4]});
        moves.push(`${number}${white ? '.' : '…'} ${made.san}`);
    }
    return {game, stop, startFen, moves, finalFen: board.fen(), side: board.turn() === 'w' ? 'white' : 'black'};
}

export interface WhereQuestion {
    color: 'w' | 'b';
    type: 'k' | 'q' | 'r' | 'b' | 'n' | 'p';
    square: string;
}

/** "Where is the piece?": a piece that is the only one of its kind and color on the board - preferably among those that moved blind. */
export function whereQuestion(task: BlindTask, seed: number): WhereQuestion {
    const board = new Chess(task.finalFen);
    const placed: WhereQuestion[] = [];
    board.board().forEach((row) => row.forEach((cell) => {
        if (cell) placed.push({color: cell.color, type: cell.type, square: cell.square});
    }));
    const unique = placed.filter((p) => placed.filter((o) => o.color === p.color && o.type === p.type).length === 1);
    const replay = new Chess(task.startFen);
    const moved = new Set<string>();
    for (const san of task.moves) moved.add(replay.move(san.split(' ').pop()!).to);
    const preferred = unique.filter((p) => moved.has(p.square) && p.type !== 'k');
    const pool = preferred.length ? preferred : unique;   // kings are always unique - a question will be found
    return pool[Math.floor(rng(seed + 7)() * pool.length)];
}
