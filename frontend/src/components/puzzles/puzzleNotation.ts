// --- FILE: frontend/src/components/puzzles/puzzleNotation.ts ---
// Puzzle move notation with figurine notation (♘f3 instead of Nf3): understandable in any language, as with the coach.
// Pure functions over chess.js, no network: moves arrive from the server in UCI, here they are converted to SAN from the given position.
// Used by PuzzlesPage, DefenseTrainer, GeneratedDrills, SolutionReplay, and also learn/MateCourse and chessboard/CoachCards.

import {Chess} from 'chess.js';

/** UCI ("e7e8q") to a chess.js move object; promotion is the fifth character, otherwise undefined. */
export function toMove(uci: string) {
    return {from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci.length > 4 ? uci[4] : undefined};
}

/** Piece symbols by colour (a pawn has no letter), to replace the first SAN letter and the promotion letter. */
const FIGURINES: Record<'w' | 'b', Record<string, string>> = {
    w: {K: '♔', Q: '♕', R: '♖', B: '♗', N: '♘'},
    b: {K: '♚', Q: '♛', R: '♜', B: '♝', N: '♞'},
};

/** SAN -> figurine notation: "Nf3" -> "♘f3", "e8=Q" -> "e8=♕". */
export function figurine(san: string, color: 'w' | 'b'): string {
    return san.replace(/^[KQRBN]/, (letter) => FIGURINES[color][letter])
        .replace(/=([QRBN])/, (_, letter: string) => `=${FIGURINES[color][letter]}`);
}

/** Solution in the familiar notation: "24. ♘f6+ ♚f8 25. ♖xf7#", moves from position fen. */
export function solutionSan(fen: string, line: string[]): string {
    const game = new Chess(fen);
    const parts: string[] = [];
    for (const uci of line) {
        const number = game.moveNumber();
        const white = game.turn() === 'w';
        const move = game.move(toMove(uci));
        const san = figurine(move.san, move.color);
        if (white) parts.push(`${number}. ${san}`);
        else parts.push(parts.length === 0 ? `${number}… ${san}` : san);
    }
    return parts.join(' ');
}

/** Moves without numbers: "♘f3", "♛xb2", each from the position after the previous ones. */
export function sanMoves(fen: string, line: string[]): string[] {
    const game = new Chess(fen);
    return line.map((uci) => {
        const move = game.move(toMove(uci));
        return figurine(move.san, move.color);
    });
}
