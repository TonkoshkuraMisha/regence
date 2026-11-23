// --- FILE: frontend/src/services/pgnExport.ts ---
// PGN export (task 16.4): a line from "Tools" and a game with analysis comments from the game viewer. Comments
// go in curly braces after the move, the evaluation in the standard form [%eval ...], move glyphs (!, ?!, ?, ??) after the SAN.
// The file is assembled entirely in the browser, the server is not involved. The comment text (with [%eval ...]) is prepared
// by the caller: here it is only cleaned of curly braces and inserted after the move.

import {Chess} from 'chess.js';

/** Initial position of standard chess: for it the SetUp and FEN tags are not written to the PGN. */
export const STANDARD_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

/** Move for writing to the PGN. */
export interface PgnMove {
    san: string;
    /** Move glyph: !, ?!, ?, ?? (empty — no glyph). */
    symbol?: string;
    comment?: string | null;
}

/** Data for buildPgn. */
export interface PgnInput {
    /** PGN tags; empty values are skipped, missing ones of the seven mandatory are filled with "?". */
    headers?: Record<string, string | null | undefined>;
    /** Starting position; if it is not the initial one, the SetUp and FEN tags are added to the PGN. */
    startFen?: string | null;
    moves: PgnMove[];
    /** "1-0", "0-1", "1/2-1/2" or "*"; anything else is written as "*". */
    result?: string | null;
}

/** Curly braces inside a comment would close it early — they are removed; spaces and line breaks are collapsed. */
function escapeComment(text: string): string {
    return text.replace(/[{}]/g, '').replace(/\s+/g, ' ').trim();
}

/**
 * PGN text: tags, then moves with numbers (lines no longer than 80 characters) and the result. The "N..." number before Black's
 * move is put at the start of the record and after a comment — as the PGN standard requires.
 */
export function buildPgn({headers = {}, startFen, moves, result}: PgnInput): string {
    const custom = startFen && startFen !== STANDARD_FEN ? startFen : null;
    const final = result && /^(1-0|0-1|1\/2-1\/2|\*)$/.test(result) ? result : '*';
    const tags: Record<string, string> = {
        Event: '?', Site: '?', Date: '????.??.??', Round: '?', White: '?', Black: '?',
        ...Object.fromEntries(Object.entries(headers).filter(([, v]) => v)) as Record<string, string>,
        Result: final,
    };
    if (custom) {
        tags.SetUp = '1';
        tags.FEN = custom;
    }
    const lines = Object.entries(tags).map(([key, value]) => `[${key} "${value.replace(/"/g, "'")}"]`);
    const blackFirst = custom ? custom.split(' ')[1] === 'b' : false;
    const firstNumber = custom ? Number(custom.split(' ')[5] ?? 1) || 1 : 1;
    const tokens: string[] = [];
    moves.forEach((move, i) => {
        const ply = i + (blackFirst ? 1 : 0);
        const number = firstNumber + Math.floor(ply / 2);
        if (ply % 2 === 0) tokens.push(`${number}.`);
        else if (i === 0 || moves[i - 1]?.comment) tokens.push(`${number}...`);
        tokens.push(`${move.san}${move.symbol ?? ''}`);
        if (move.comment && escapeComment(move.comment)) tokens.push(`{${escapeComment(move.comment)}}`);
    });
    tokens.push(final);
    // Movetext lines are no longer than 80 characters.
    const body: string[] = [];
    let line = '';
    for (const token of tokens) {
        if (line && line.length + token.length + 1 > 80) {
            body.push(line);
            line = token;
        } else {
            line = line ? `${line} ${token}` : token;
        }
    }
    if (line) body.push(line);
    return `${lines.join('\n')}\n\n${body.join('\n')}\n`;
}

/** SAN of the line's moves from position startFen; an illegal move — a chess.js exception. */
export function sansOf(startFen: string, uciMoves: string[]): string[] {
    const game = new Chess(startFen);
    return uciMoves.map((uci) => game.move({from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4]}).san);
}

/** Hand the text to the browser as a downloadable PGN file (a temporary Blob link). */
export function downloadText(filename: string, text: string): void {
    const url = URL.createObjectURL(new Blob([text], {type: 'application/x-chess-pgn'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
}
