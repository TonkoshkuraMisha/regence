// --- FILE: frontend/src/components/chessboard/boardUtils.ts ---
// Constants and pure functions of the board (extracted from Chessboard.tsx): board size by window, material
// advantage, a copy of the chess.js game, a game's starting position, FEN validation, laying moves out in pairs. No server needed:
// the chess rules are the chess.js library, the texts are the message catalog (board.* keys).

import {Chess} from 'chess.js';
import {t} from '../../i18n';

/** Files left to right and ranks top to bottom, as White sees them. */
export const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
export const RANKS = ['8', '7', '6', '5', '4', '3', '2', '1'];

/** Board side limits in pixels (the size slider and the resize corner). */
export const MIN_BOARD_SIZE = 280;
export const MAX_BOARD_SIZE = 860;

export type PromotionPiece = 'q' | 'n' | 'r' | 'b';

// The piece name is read from the catalog at display time (a getter): a language change updates the label without a reload.
function promotionOption(type: PromotionPiece): { type: PromotionPiece; readonly label: string } {
    return {
        type,
        get label() {
            return t(`board.pieces.${type}`);
        },
    };
}

/** Pieces to choose on pawn promotion, in display order (PromotionDialog). */
export const PROMOTION_OPTIONS: Array<{ type: PromotionPiece; readonly label: string }> = [
    promotionOption('q'),
    promotionOption('n'),
    promotionOption('r'),
    promotionOption('b'),
];

/**
 * The largest board side that fits the window: by height, the window minus 220 px for the rest of the markup,
 * by width, minus 850 px for the side columns on a screen from 1280 px, otherwise the full width minus 24 px. Not less than
 * MIN_BOARD_SIZE and not more than MAX_BOARD_SIZE.
 */
export function getMaxViewportBoardSize(): number {
    if (typeof window === 'undefined') return 560;
    const availableHeight = window.innerHeight - 220;
    const availableWidth = window.innerWidth >= 1280
        ? window.innerWidth - 850
        : window.innerWidth - 24;
    const limit = Math.min(availableHeight, availableWidth, MAX_BOARD_SIZE);
    return Math.max(MIN_BOARD_SIZE, Math.min(limit, window.innerWidth - 24));
}

/**
 * Board side for the current window: the one saved by the player (a string from localStorage regence_board_size), but no larger than
 * fits; without a saved one, the largest that fits. Called on opening and on every window change,
 * so the board both shrinks and grows again when the window is enlarged (before, it only shrank).
 */
export function fittedBoardSize(saved: string | null, maxFit: number = getMaxViewportBoardSize()): number {
    const parsed = saved === null ? NaN : Number(saved);
    return !Number.isNaN(parsed) && parsed >= MIN_BOARD_SIZE ? Math.min(parsed, maxFit) : maxFit;
}

/** Default board size: the largest that fits the window (double-click on the resize corner). */
export function getDefaultBoardSize(): number {
    if (typeof window !== 'undefined') {
        return getMaxViewportBoardSize();
    }
    return 540;
}

/** Nominal piece values in pawns: only for the advantage line by the player's name, it does not affect the game. */
export const PIECE_VALUES: Record<string, number> = {p: 1, n: 3, b: 3, r: 5, q: 9, k: 0};

/**
 * Material advantage and "captured" pieces by the board position (boardState is the board() result from chess.js).
 * Captured pieces are computed as the difference from the full starting set, not from the capture history: a promoted pawn
 * looks captured, and in a game from a non-standard position the list is meaningless (Chessboard then does not show it).
 * whiteCapturedSymbols are the black pieces captured by White, and vice versa.
 */
export function calculateMaterialBalance(boardState: any[][]) {
    const startCounts: Record<string, number> = {p: 8, n: 2, b: 2, r: 2, q: 1};
    const currentWhite: Record<string, number> = {p: 0, n: 0, b: 0, r: 0, q: 0};
    const currentBlack: Record<string, number> = {p: 0, n: 0, b: 0, r: 0, q: 0};

    let whiteScore = 0;
    let blackScore = 0;

    for (const row of boardState) {
        for (const cell of row) {
            if (!cell) continue;
            const val = PIECE_VALUES[cell.type] || 0;
            if (cell.color === 'w') {
                whiteScore += val;
                if (currentWhite[cell.type] !== undefined) currentWhite[cell.type]++;
            } else {
                blackScore += val;
                if (currentBlack[cell.type] !== undefined) currentBlack[cell.type]++;
            }
        }
    }

    const whiteCapturedSymbols: string[] = [];
    const blackCapturedSymbols: string[] = [];
    const order = ['q', 'r', 'b', 'n', 'p'];
    const glyphs: Record<string, string> = {q: '♛', r: '♜', b: '♝', n: '♞', p: '♟'};

    for (const t of order) {
        const missingBlack = Math.max(0, startCounts[t] - currentBlack[t]);
        for (let i = 0; i < missingBlack; i++) whiteCapturedSymbols.push(glyphs[t]);

        const missingWhite = Math.max(0, startCounts[t] - currentWhite[t]);
        for (let i = 0; i < missingWhite; i++) blackCapturedSymbols.push(glyphs[t]);
    }

    return {
        whiteAdvantage: Math.max(0, whiteScore - blackScore),
        blackAdvantage: Math.max(0, blackScore - whiteScore),
        whiteCapturedSymbols,
        blackCapturedSymbols
    };
}

/**
 * Independent copy of the game. Copied via PGN to keep the move history (and the FEN header of a game with
 * a custom position); for a position without moves and headers the PGN is empty, then only the FEN is copied.
 */
export function cloneChessInstance(source: Chess): Chess {
    const copy = new Chess();
    const currentPgn = source.pgn();
    if (currentPgn) {
        copy.loadPgn(currentPgn);
    } else {
        copy.load(source.fen());
    }
    return copy;
}

export const STANDARD_START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

/** Starting position of the game if it is not the ordinary setup (from the FEN header in the PGN), otherwise null. */
export function customStartFen(source: Chess): string | null {
    const fen = source.header().FEN;
    return fen && fen !== STANDARD_START_FEN ? fen : null;
}

/**
 * Validates a FEN by the same rules as the board (chess.js); returns an error text in the player's language or null.
 * A position in which the game is already over (mate, stalemate, draw) is also rejected: there is nothing to play from it.
 */
export function validateFen(fen: string): string | null {
    try {
        const probe = new Chess(fen.trim());
        if (probe.isGameOver()) return t('board.fenGameOver');
        return null;
    } catch {
        return t('board.fenInvalid');
    }
}

/** Move list row: move number, White's move and Black's move with their indices in the ply history. */
export interface HalfMovePair {
    moveNumber: number;
    /** undefined and whiteIdx === -1 mean the game started with Black's move, the first pair has no White move. */
    whiteSan?: string;
    whiteIdx: number;
    blackSan?: string;
    blackIdx?: number;
}

/**
 * Lays plies out in "white / black" pairs. A game from a custom position may
 * start with Black's move and not at move one: the number and side are taken from its FEN.
 */
export function pairHalfMoves(history: Array<{ san: string }>, startFen?: string | null): HalfMovePair[] {
    const fenParts = (startFen ?? '').trim().split(/\s+/);
    const blackStarts = fenParts[1] === 'b';
    const firstMoveNumber = Number(fenParts[5]) > 0 ? Number(fenParts[5]) : 1;

    const pairs: HalfMovePair[] = [];
    history.forEach((move, idx) => {
        const ply = idx + (blackStarts ? 1 : 0);
        const moveNumber = firstMoveNumber + Math.floor(ply / 2);
        if (ply % 2 === 0) {
            pairs.push({moveNumber, whiteSan: move.san, whiteIdx: idx});
        } else if (pairs.length === 0) {
            pairs.push({moveNumber, whiteIdx: -1, blackSan: move.san, blackIdx: idx});
        } else {
            pairs[pairs.length - 1].blackSan = move.san;
            pairs[pairs.length - 1].blackIdx = idx;
        }
    });
    return pairs;
}

/** Index of the ply currently on the board: for the live position (viewIndex === -1) it is the last move of the history. */
export function prevIndexHelper(viewIndex: number, historyLength: number): number {
    return viewIndex === -1 ? historyLength - 1 : viewIndex;
}
