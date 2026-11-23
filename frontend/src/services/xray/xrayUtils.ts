// --- FILE: frontend/src/services/xray/xrayUtils.ts ---
// Board "x-ray" (task 12.1): pure position calculations, no engine - square control (with batteries), pieces under
// attack, overloaded defenders, pins and skewers, captures (exchange or win), defenses, checks and mates,
// isolated and passed pawns, safe and dangerous squares for the selected piece. All for any side:
// "show for the opponent" - the same calculations for the other color.
// Everything is computed in the browser from FEN: the server and engine are not involved, so the "x-ray" does not fall under the
// fair-play rule as an engine hint. Legal moves come from chess.js, the rest is board geometry in this file.
// Display on the board - components/xray/XrayOverlay.tsx.

import {Chess} from 'chess.js';
import type {Move} from 'chess.js';

/** Piece color and type - in chess.js notation. */
export type Color = 'w' | 'b';
export type PieceType = 'p' | 'n' | 'b' | 'r' | 'q' | 'k';

/** Piece on the board: type, color and square ("e4"). */
export interface BoardPiece {
    type: PieceType;
    color: Color;
    square: string;
}

/** Piece value in pawns for exchange calculation; the king is 100 so that it is never considered a "cheap" piece. */
export const PIECE_VALUE: Record<PieceType, number> = {p: 1, n: 3, b: 3, r: 5, q: 9, k: 100};

const FILES = 'abcdefgh';
const ORTHOGONAL: [number, number][] = [[1, 0], [-1, 0], [0, 1], [0, -1]];
const DIAGONAL: [number, number][] = [[1, 1], [1, -1], [-1, 1], [-1, -1]];
const KNIGHT: [number, number][] = [[1, 2], [2, 1], [2, -1], [1, -2], [-1, -2], [-2, -1], [-2, 1], [-1, 2]];
const KING: [number, number][] = [...ORTHOGONAL, ...DIAGONAL];

/** Square name from zero-based file and rank numbers: (0, 0) is "a1". */
export function squareName(file: number, rank: number): string {
    return `${FILES[file]}${rank + 1}`;
}

function coords(square: string): [number, number] {
    return [FILES.indexOf(square[0]), Number(square[1]) - 1];
}

function onBoard(file: number, rank: number): boolean {
    return file >= 0 && file < 8 && rank >= 0 && rank < 8;
}

/** Opponent's color. */
export function opposite(color: Color): Color {
    return color === 'w' ? 'b' : 'w';
}

/** Pieces of the position by square - from the first part of FEN (placement), without chess.js. */
export function piecesOf(fen: string): Map<string, BoardPiece> {
    const pieces = new Map<string, BoardPiece>();
    const placement = fen.split(' ')[0];
    let rank = 7;
    let file = 0;
    for (const ch of placement) {
        if (ch === '/') {
            rank -= 1;
            file = 0;
        } else if (/\d/.test(ch)) {
            file += Number(ch);
        } else {
            const color: Color = ch === ch.toUpperCase() ? 'w' : 'b';
            const square = squareName(file, rank);
            pieces.set(square, {type: ch.toLowerCase() as PieceType, color, square});
            file += 1;
        }
    }
    return pieces;
}

/** Whether a sliding piece of type type moves along the direction: queen - any, bishop - diagonal, rook - straight. */
function slides(type: PieceType, direction: [number, number]): boolean {
    const diagonal = direction[0] !== 0 && direction[1] !== 0;
    if (type === 'q') return true;
    return diagonal ? type === 'b' : type === 'r';
}

/** Attack on a square: who attacks and from which square. */
export interface Attack {
    from: string;
    piece: BoardPiece;
    /** Attack through one's own sliding piece on the same line (battery). */
    xray: boolean;
}

/**
 * All attacks on squares: for each square - who attacks it (with batteries). Attacks are counted, not moves: a pawn attacks
 * diagonally even an empty square, a square under one's own piece is also "attacked" (that is defense), pins are not considered here.
 */
export function attackMap(pieces: Map<string, BoardPiece>): Map<string, Attack[]> {
    const map = new Map<string, Attack[]>();
    const add = (square: string, attack: Attack) => {
        const list = map.get(square);
        if (list) list.push(attack);
        else map.set(square, [attack]);
    };
    for (const piece of pieces.values()) {
        const [f, r] = coords(piece.square);
        if (piece.type === 'p') {
            const dr = piece.color === 'w' ? 1 : -1;
            for (const df of [-1, 1]) {
                if (onBoard(f + df, r + dr)) add(squareName(f + df, r + dr), {from: piece.square, piece, xray: false});
            }
        } else if (piece.type === 'n' || piece.type === 'k') {
            for (const [df, dr] of piece.type === 'n' ? KNIGHT : KING) {
                if (onBoard(f + df, r + dr)) add(squareName(f + df, r + dr), {from: piece.square, piece, xray: false});
            }
        } else {
            const directions = piece.type === 'r' ? ORTHOGONAL : piece.type === 'b' ? DIAGONAL : KING;
            for (const direction of directions) {
                let xray = false;
                let file = f + direction[0];
                let rank = r + direction[1];
                while (onBoard(file, rank)) {
                    const square = squareName(file, rank);
                    add(square, {from: piece.square, piece, xray});
                    const blocker = pieces.get(square);
                    if (blocker) {
                        // Battery: one's own sliding piece on the same line is "transparent" - the attack goes further.
                        if (blocker.color === piece.color && blocker.type !== 'k' && slides(blocker.type, direction)) {
                            xray = true;
                        } else {
                            break;
                        }
                    }
                    file += direction[0];
                    rank += direction[1];
                }
            }
        }
    }
    return map;
}

/** How many white and black pieces attack the square. */
export interface SquareControl {
    white: number;
    black: number;
}

/** Control of the 64 squares: how many pieces of each side attack the square (with batteries). */
export function controlMap(pieces: Map<string, BoardPiece>, attacks = attackMap(pieces)): Map<string, SquareControl> {
    const control = new Map<string, SquareControl>();
    for (let file = 0; file < 8; file++) {
        for (let rank = 0; rank < 8; rank++) {
            const square = squareName(file, rank);
            const list = attacks.get(square) ?? [];
            control.set(square, {
                white: list.filter((a) => a.piece.color === 'w').length,
                black: list.filter((a) => a.piece.color === 'b').length,
            });
        }
    }
    return control;
}

/** Attacks by side color on square square. */
function attackersBy(attacks: Map<string, Attack[]>, square: string, color: Color): Attack[] {
    return (attacks.get(square) ?? []).filter((a) => a.piece.color === color);
}

/**
 * Absolute pins of both sides: pinned piece -> squares it can still attack (the pin line
 * between the king and the pinning piece, including the latter itself).
 */
export function absolutePins(pieces: Map<string, BoardPiece>): Map<string, Set<string>> {
    const pins = new Map<string, Set<string>>();
    for (const king of pieces.values()) {
        if (king.type !== 'k') continue;
        const [kf, kr] = coords(king.square);
        for (const direction of KING) {
            const line: string[] = [];
            let own: BoardPiece | null = null;
            let file = kf + direction[0];
            let rank = kr + direction[1];
            while (onBoard(file, rank)) {
                const square = squareName(file, rank);
                line.push(square);
                const other = pieces.get(square);
                if (other) {
                    if (other.color === king.color) {
                        if (own) break;
                        own = other;
                    } else {
                        if (own && other.type !== 'k' && other.type !== 'p' && other.type !== 'n'
                            && slides(other.type, direction)) {
                            pins.set(own.square, new Set(line));
                        }
                        break;
                    }
                }
                file += direction[0];
                rank += direction[1];
            }
        }
    }
    return pins;
}

/**
 * Attacks that the pieces can actually deliver: a piece pinned to the king attacks only along the pin line.
 * For "who defends whom" and "can it be captured with a gain"; square control (controlMap) stays full - a pinned
 * piece still does not let the opponent's king onto its squares.
 */
export function effectiveAttacks(pieces: Map<string, BoardPiece>, attacks = attackMap(pieces)): Map<string, Attack[]> {
    const pins = absolutePins(pieces);
    if (pins.size === 0) return attacks;
    const result = new Map<string, Attack[]>();
    for (const [square, list] of attacks) {
        result.set(square, list.filter((a) => {
            const line = pins.get(a.from);
            return !line || line.has(square);
        }));
    }
    return result;
}

/** Order of participation in an exchange: first direct attacks by ascending value, then batteries (behind one's own piece). */
function exchangeOrder(list: Attack[]): number[] {
    return [...list].sort((a, b) => Number(a.xray) - Number(b.xray) || PIECE_VALUE[a.piece.type] - PIECE_VALUE[b.piece.type])
        .map((a) => PIECE_VALUE[a.piece.type]);
}

/**
 * Static exchange evaluation (SEE) on a square: how much the side gains that takes a piece of value victim first with a
 * piece of value first; then the sides capture in turn with the cheapest pieces and may stop at any moment.
 */
export function exchangeGain(victim: number, first: number, takers: number[], defenders: number[]): number {
    const gains = [victim];
    let onSquare = first;
    const lists = [defenders.slice(), takers.slice()];
    for (let side = 0; lists[side].length > 0; side = 1 - side) {
        gains.push(onSquare - gains[gains.length - 1]);
        onSquare = lists[side].shift() as number;
    }
    for (let i = gains.length - 1; i > 0; i--) gains[i - 1] = -Math.max(-gains[i - 1], gains[i]);
    return gains[0] + 0; // avoids -0
}

/**
 * Piece under attack: an exchange on its square, started by the cheapest attacker, wins material (SEE) -
 * accounts for the number of attackers and defenders and for pins (attacks - from effectiveAttacks). The king does not count.
 */
export function isEnPrise(piece: BoardPiece, attacks: Map<string, Attack[]>): boolean {
    if (piece.type === 'k') return false;
    const attackers = exchangeOrder(attackersBy(attacks, piece.square, opposite(piece.color)));
    if (attackers.length === 0) return false;
    const defenders = exchangeOrder(attackersBy(attacks, piece.square, piece.color));
    return exchangeGain(PIECE_VALUE[piece.type], attackers[0], attackers.slice(1), defenders) > 0;
}

/** Pieces of side color that can be captured with a gain. */
export function hangingPieces(pieces: Map<string, BoardPiece>, color: Color, attacks = effectiveAttacks(pieces)): string[] {
    return [...pieces.values()].filter((p) => p.color === color && isEnPrise(p, attacks)).map((p) => p.square);
}

/** Overloaded defender: its square and the squares of the pieces that only it defends. */
export interface Overload {
    defender: string;
    duties: string[];
}

/** Overloaded defenders of side color: the sole defense of two or more attacked pieces. */
export function overloadedDefenders(
    pieces: Map<string, BoardPiece>, color: Color, attacks = effectiveAttacks(pieces),
): Overload[] {
    const duties = new Map<string, string[]>();
    for (const piece of pieces.values()) {
        if (piece.color !== color || piece.type === 'k') continue;
        if (attackersBy(attacks, piece.square, opposite(color)).length === 0) continue;
        const defenders = attackersBy(attacks, piece.square, color).filter((a) => !a.xray);
        if (defenders.length !== 1) continue;
        const list = duties.get(defenders[0].from) ?? [];
        list.push(piece.square);
        duties.set(defenders[0].from, list);
    }
    return [...duties.entries()].filter(([, list]) => list.length >= 2).map(([defender, list]) => ({defender, duties: list}));
}

/** Pin or skewer: two opponent pieces on one line with a sliding piece. */
export interface LineTactic {
    kind: 'pin' | 'skewer';
    /** Attacking sliding piece. */
    attacker: string;
    /** Piece in front on the line. */
    front: string;
    /** Piece behind it. */
    behind: string;
    /**
     * The king is involved. For a pin - the king is behind: the front piece cannot move. For a skewer - the king
     * is in front: that is a check after which the piece behind the king is lost.
     */
    absolute: boolean;
}

/**
 * Pins and skewers by pieces of side color against opponent pieces. Pin - the rear piece is more valuable than the front;
 * skewer - the front is more valuable than the rear and it is either profitable to capture (it costs more than the attacker) or it is unprotected.
 * A pawn behind does not count: nobody opens a line for its sake.
 */
export function lineTactics(
    pieces: Map<string, BoardPiece>, color: Color, attacks = effectiveAttacks(pieces),
): LineTactic[] {
    const result: LineTactic[] = [];
    for (const piece of pieces.values()) {
        if (piece.color !== color || !['b', 'r', 'q'].includes(piece.type)) continue;
        const [f, r] = coords(piece.square);
        const directions = piece.type === 'r' ? ORTHOGONAL : piece.type === 'b' ? DIAGONAL : KING;
        for (const direction of directions) {
            const found: BoardPiece[] = [];
            let file = f + direction[0];
            let rank = r + direction[1];
            while (onBoard(file, rank) && found.length < 2) {
                const other = pieces.get(squareName(file, rank));
                if (other) found.push(other);
                file += direction[0];
                rank += direction[1];
            }
            if (found.length < 2) continue;
            const [front, behind] = found;
            if (front.color === color || behind.color === color) continue;
            const frontValue = PIECE_VALUE[front.type];
            const behindValue = PIECE_VALUE[behind.type];
            if (behindValue > frontValue && behind.type !== 'p') {
                result.push({kind: 'pin', attacker: piece.square, front: front.square, behind: behind.square,
                    absolute: behind.type === 'k'});
            } else if (frontValue > behindValue && behind.type !== 'p' && (frontValue > PIECE_VALUE[piece.type]
                // An unprotected front piece can be captured even by a more valuable one: the queen attacks through the rook onto the bishop.
                || attackersBy(attacks, front.square, front.color).length === 0)) {
                result.push({kind: 'skewer', attacker: piece.square, front: front.square, behind: behind.square,
                    absolute: front.type === 'k'});
            }
        }
    }
    return result;
}

/**
 * Position where side color moves: "what would the opponent do if it were their move?". null - such a position is impossible.
 * If the side to move changes, the en passant right is reset: it belonged to the other side.
 */
export function gameFor(
    fen: string, color: Color, pieces = piecesOf(fen), attacks?: Map<string, Attack[]>,
): Chess | null {
    const parts = fen.split(' ');
    if (parts[1] === color) return new Chess(fen);
    parts[1] = color;
    parts[3] = '-';
    // If color moved and the opponent's king is already in check - such a position cannot exist.
    const enemyKing = [...pieces.values()].find((p) => p.type === 'k' && p.color === opposite(color));
    if (enemyKing && attackersBy(attacks ?? attackMap(pieces), enemyKing.square, color).length > 0) return null;
    try {
        return new Chess(parts.join(' '));
    } catch {
        return null;
    }
}

/** Arrow on the board: from square to square. */
export interface MoveArrow {
    from: string;
    to: string;
}

/** Capture arrow. */
export interface CaptureArrow extends MoveArrow {
    /** winning - wins material (thick arrow), exchange - an exchange (thin). */
    kind: 'winning' | 'exchange';
}

/** All moves of side color (detailed); an impossible position - empty. */
export function verboseMoves(fen: string, color: Color, pieces = piecesOf(fen), attacks?: Map<string, Attack[]>): Move[] {
    return gameFor(fen, color, pieces, attacks)?.moves({verbose: true}) ?? [];
}

/** All legal moves of side color as arrows, without duplicates. */
export function legalMoves(fen: string, color: Color, moves = verboseMoves(fen, color)): MoveArrow[] {
    const seen = new Set<string>();
    const arrows: MoveArrow[] = [];
    for (const move of moves) {
        const key = `${move.from}${move.to}`;
        if (seen.has(key)) continue; // promotions to different pieces - one arrow
        seen.add(key);
        arrows.push({from: move.from, to: move.to});
    }
    return arrows;
}

/**
 * Captures by side color: winning - an exchange on the square started by this capture brings material (SEE, with pins),
 * otherwise an exchange.
 */
export function captures(
    fen: string, color: Color, pieces = piecesOf(fen), attacks = effectiveAttacks(pieces),
    moves = verboseMoves(fen, color, pieces, attacks),
): CaptureArrow[] {
    const seen = new Set<string>();
    const arrows: CaptureArrow[] = [];
    for (const move of moves) {
        if (!move.captured || seen.has(`${move.from}${move.to}`)) continue;
        seen.add(`${move.from}${move.to}`);
        const target = pieces.get(move.to);
        // En passant: the opponent's pawn is not on the target square - the exchange on this square is not counted (an "exchange" arrow).
        const winning = target !== undefined && exchangeGain(
            PIECE_VALUE[target.type], PIECE_VALUE[move.piece as PieceType],
            exchangeOrder(attackersBy(attacks, move.to, color).filter((a) => a.from !== move.from)),
            exchangeOrder(attackersBy(attacks, move.to, target.color)),
        ) > 0;
        arrows.push({from: move.from, to: move.to, kind: winning ? 'winning' : 'exchange'});
    }
    return arrows;
}

/** Defenses by side color: which own piece covers which (the king is not "defended"; defense through a battery does not count). */
export function defenses(pieces: Map<string, BoardPiece>, color: Color, attacks = effectiveAttacks(pieces)): MoveArrow[] {
    const arrows: MoveArrow[] = [];
    for (const piece of pieces.values()) {
        if (piece.color !== color || piece.type === 'k') continue;
        for (const defender of attackersBy(attacks, piece.square, color)) {
            if (!defender.xray) arrows.push({from: defender.from, to: piece.square});
        }
    }
    return arrows;
}

/** Check-giving move arrow; mate - this move delivers mate. */
export interface CheckArrow extends MoveArrow {
    mate: boolean;
}

/** Checks and mates that side color can give (by the "+" and "#" marks in the chess.js move notation). */
export function checks(fen: string, color: Color, moves = verboseMoves(fen, color)): CheckArrow[] {
    const byKey = new Map<string, CheckArrow>();
    for (const move of moves) {
        if (!move.san.includes('+') && !move.san.includes('#')) continue;
        const key = `${move.from}${move.to}`;
        const mate = move.san.includes('#');
        const existing = byKey.get(key);
        if (existing) existing.mate ||= mate;
        else byKey.set(key, {from: move.from, to: move.to, mate});
    }
    return [...byKey.values()];
}

/** Squares of isolated and passed pawns of one side. */
export interface PawnFlags {
    isolated: string[];
    passed: string[];
}

/**
 * Isolated and passed pawns of side color. Isolated - no own pawns on adjacent files;
 * passed - no opponent pawns ahead on its own and adjacent files.
 */
export function pawnFlags(pieces: Map<string, BoardPiece>, color: Color): PawnFlags {
    const own = [...pieces.values()].filter((p) => p.type === 'p' && p.color === color);
    const enemy = [...pieces.values()].filter((p) => p.type === 'p' && p.color !== color);
    const forward = color === 'w' ? 1 : -1;
    const isolated: string[] = [];
    const passed: string[] = [];
    for (const pawn of own) {
        const [f, r] = coords(pawn.square);
        if (!own.some((o) => Math.abs(coords(o.square)[0] - f) === 1)) isolated.push(pawn.square);
        const blocked = enemy.some((e) => {
            const [ef, er] = coords(e.square);
            return Math.abs(ef - f) <= 1 && (er - r) * forward > 0;
        });
        if (!blocked) passed.push(pawn.square);
    }
    return {isolated, passed};
}

/** Square where the selected piece can go, and whether it is safe there. */
export interface SquareSafety {
    square: string;
    safe: boolean;
}

/**
 * Where the piece from square from can go and where it will be under attack. Each move is made on a copy of the position,
 * and in the new position it is checked whether the piece can be captured with a gain (isEnPrise); a pawn promotes to a queen.
 */
export function destinationSafety(fen: string, from: string): SquareSafety[] {
    const pieces = piecesOf(fen);
    const piece = pieces.get(from);
    if (!piece) return [];
    const game = gameFor(fen, piece.color);
    if (!game) return [];
    const result: SquareSafety[] = [];
    const seen = new Set<string>();
    for (const move of game.moves({square: from as never, verbose: true})) {
        if (seen.has(move.to)) continue;
        seen.add(move.to);
        const after = new Chess(game.fen());
        after.move({from: move.from, to: move.to, promotion: move.promotion ?? 'q'});
        const afterPieces = piecesOf(after.fen());
        const moved = afterPieces.get(move.to);
        result.push({square: move.to, safe: !moved || !isEnPrise(moved, effectiveAttacks(afterPieces))});
    }
    return result;
}

/** Result of xrayFor: one square set per x-ray display mode (toggles - components/xray/XrayPanel.tsx). */
export interface XrayReport {
    control: Map<string, SquareControl>;
    hanging: string[];
    overloaded: Overload[];
    lines: LineTactic[];
    captures: CaptureArrow[];
    defenses: MoveArrow[];
    checks: CheckArrow[];
    moves: MoveArrow[];
    pawns: PawnFlags;
}

/**
 * Full "x-ray" for side color: what it can do (captures, checks, moves, pins), what it defends, which of its pieces
 * are under attack and overloaded, its pawn weaknesses and strengths. Square control - for both sides.
 */
export function xrayFor(fen: string, color: Color): XrayReport {
    // The position is parsed once: pieces, attack map and chess.js moves are shared by all modes.
    const pieces = piecesOf(fen);
    const attacks = attackMap(pieces);
    // Defenses and exchanges - without attacks by pinned pieces; square control - full.
    const effective = effectiveAttacks(pieces, attacks);
    const moves = verboseMoves(fen, color, pieces, attacks);
    return {
        control: controlMap(pieces, attacks),
        hanging: hangingPieces(pieces, color, effective),
        overloaded: overloadedDefenders(pieces, color, effective),
        lines: lineTactics(pieces, color, effective),
        captures: captures(fen, color, pieces, effective, moves),
        defenses: defenses(pieces, color, effective),
        checks: checks(fen, color, moves),
        moves: legalMoves(fen, color, moves),
        pawns: pawnFlags(pieces, color),
    };
}
