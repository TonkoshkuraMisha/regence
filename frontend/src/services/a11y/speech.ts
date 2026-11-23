// --- FILE: frontend/src/services/a11y/speech.ts ---
// Accessibility (task 26.3): moves, squares and the position in words — for screen readers and for those who play without
// looking at the board. The module is pure: words come from the translation catalog (a11y.* keys), hence in three languages; data is
// the verbose chess.js move (history({verbose: true})) and the chess.js board (board()). Pieces hidden in blindfold play are not
// passed in here: what is hidden is decided by the caller (Chessboard, visibleSquares).

/** Translation: key and parameters → string (useI18n().t). */
export type Translate = (key: string, params?: Record<string, string | number>) => string;

export type PieceType = 'p' | 'n' | 'b' | 'r' | 'q' | 'k';
export type Side = 'w' | 'b';

/** Piece on a square (as in chess.js board()). */
export interface BoardPiece {
    type: PieceType;
    color: Side;
}

/** Verbose chess.js move: the fields needed here. */
export interface VerboseMove {
    color: Side;
    piece: PieceType;
    from: string;
    to: string;
    san: string;
    captured?: PieceType;
    promotion?: PieceType;
    /** chess.js flags: k — kingside castling, q — queenside, e — en passant capture. */
    flags: string;
}

// Order of pieces in the position description: from king to pawns.
const ORDER: PieceType[] = ['k', 'q', 'r', 'b', 'n', 'p'];
const FILES = 'abcdefgh';

/** Square for a screen reader: «e4, white knight», «e4, empty»; hidden — do not name the piece (blindfold play). */
export function squareLabel(square: string, piece: BoardPiece | null, t: Translate, hidden = false): string {
    if (hidden) return square;
    return piece ? t('a11y.square', {square, piece: t(`a11y.piece.${piece.color}${piece.type}`)})
        : t('a11y.emptySquare', {square});
}

/** Move in words: «White: knight takes f3, check», «Black: kingside castling», «White: pawn e8, promotion to queen, mate». */
export function moveWords(move: VerboseMove, t: Translate): string {
    const parts: string[] = [];
    if (move.flags.includes('k')) parts.push(t('a11y.castleShort'));
    else if (move.flags.includes('q')) parts.push(t('a11y.castleLong'));
    else {
        const noun = t(`a11y.noun.${move.piece}`);
        parts.push(move.captured ? t('a11y.captures', {piece: noun, from: move.from, to: move.to})
            : t('a11y.moves', {piece: noun, from: move.from, to: move.to}));
        if (move.flags.includes('e')) parts.push(t('a11y.enPassant'));
        if (move.promotion) parts.push(t(`a11y.promotion.${move.promotion}`));
    }
    if (move.san.endsWith('#')) parts.push(t('a11y.mate'));
    else if (move.san.endsWith('+')) parts.push(t('a11y.check'));
    return t('a11y.move', {side: t(move.color === 'w' ? 'a11y.white' : 'a11y.black'), words: parts.join(', ')});
}

/**
 * Position in words: by side, pieces from king to pawns, each with its squares: «White: king on g1; queen on
 * d1; pawn on a2, b2. Black: …». board — 8 ranks from the 8th to the 1st (chess.js board()); null — empty square.
 */
export function positionWords(board: (BoardPiece | null)[][], t: Translate): string {
    const squares: Record<string, string[]> = {};
    board.forEach((row, rowIndex) => row.forEach((piece, fileIndex) => {
        if (!piece) return;
        (squares[`${piece.color}${piece.type}`] ??= []).push(`${FILES[fileIndex]}${8 - rowIndex}`);
    }));
    const side = (color: Side) => {
        const groups = ORDER.filter((type) => squares[`${color}${type}`])
            .map((type) => t('a11y.group', {piece: t(`a11y.noun.${type}`), squares: squares[`${color}${type}`].sort().join(', ')}));
        return t('a11y.side', {side: t(color === 'w' ? 'a11y.white' : 'a11y.black'), pieces: groups.length ? groups.join('; ') : t('a11y.nothing')});
    };
    return `${side('w')} ${side('b')}`;
}

/**
 * Square the focus moves to on an arrow key: arrows are screen-relative, so with a flipped board the directions
 * change. Past the board edge the focus stays in place.
 */
export function stepSquare(square: string, key: string, flipped: boolean): string {
    const step: Record<string, [number, number]> = {ArrowUp: [0, 1], ArrowDown: [0, -1], ArrowLeft: [-1, 0], ArrowRight: [1, 0]};
    const delta = step[key];
    if (!delta) return square;
    const sign = flipped ? -1 : 1;
    const file = FILES.indexOf(square[0]) + delta[0] * sign;
    const rank = Number(square[1]) + delta[1] * sign;
    return file < 0 || file > 7 || rank < 1 || rank > 8 ? square : `${FILES[file]}${rank}`;
}
