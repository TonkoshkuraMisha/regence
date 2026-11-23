// --- FILE: frontend/src/components/puzzles/PuzzleBoard.tsx ---
// Puzzle board (task 13.3): a move by dragging a piece (mouse, finger, pen) or by two clicks, a piece and then a square;
// piece choice on promotion (puzzles sometimes have an underpromotion), last-move highlight and hints.
// Pieces and colours come from the player's settings. With onSquare a click selects a square, not a move (defence exercises, task 13.6).
//
// Dragging: the piece "sticks" to the pointer, the move goes to the square under it on release. Released on the same square
// (or just clicked), the piece stays selected and the move can be finished by clicking a square. The selection is tied to the position:
// after the opponent's reply or a new puzzle the old selection does not apply.
// Appearance is config/boardAppearance.ts (the player's localStorage), sounds are services/soundEngine. Moves are checked by
// chess.js, and whether a move is correct is decided by the parent (onMove gives UCI). A shared board for PuzzlesPage, trainers and lessons
// (learn/*, trainers/*, repertoire/*, chess960/*, study/*, guess/*, tools/*).
// PuzzleBoard draws pieces, highlights, arrows and hints and accepts a move (dragging, clicks, promotion choice).

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import type {PointerEvent as ReactPointerEvent} from 'react';
import {Chess} from 'chess.js';
import {useI18n} from '../../i18n';
import {resolveMoveSound, soundEngine} from '../../services/soundEngine';
import {AnnotationsOverlay, useBoardAnnotations} from '../chessboard/annotations';
import {useBoardKeyboard} from '../chessboard/hooks/useBoardKeyboard';
import {squareLabel} from '../../services/a11y/speech';
import type {Translate} from '../../services/a11y/speech';
import {
    BOARD_THEMES, lastMoveColor, getHarmoniousPieceStyle, getPieceSvgUrl, getSavedBoardThemeKey, getSavedPieceSetKey,
} from '../../config/boardAppearance';
import {BoardTextureLayer} from '../chessboard/BoardTextureLayer';

/** File letters left to right (to convert a square to coordinates). */
const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
/** Pieces offered on promotion, in display order. */
const PROMOTIONS = ['q', 'r', 'b', 'n'] as const;
/** Pointer travel after which a press counts as a drag, not a click. */
const DRAG_THRESHOLD_PX = 4;

interface Props {
    fen: string;
    orientation: 'white' | 'black';
    /** Whether moving is allowed (the solver's side and their turn). */
    interactive: boolean;
    lastMove?: { from: string; to: string } | null;
    /** Hint: the piece's square and, after the second hint, the move's square. */
    hint?: { from: string; to: string | null } | null;
    /** Mark of the move result on a square. */
    mark?: { square: string; ok: boolean } | null;
    onMove: (uci: string) => void;
    /** Square selection instead of a move (defence exercises 13.6: "show the threat"). */
    onSquare?: (square: string) => void;
    /** Arrows over the board (school lessons, task 14.1). */
    arrows?: BoardArrow[];
    /** Highlighted squares. */
    highlights?: string[];
    /** Dark highlight (a session with a trainer, task 17.3). */
    darkHighlights?: string[];
    /** "Ghost" piece: semi-transparent, shows where the piece can stand. */
    ghost?: { square: string; piece: string } | null;
    /** ABC stars (task 14.5): squares that must be passed through; on a square with a piece, a star in the corner. */
    stars?: string[];
    /** Move and wrong-solution sounds, as on the main board (on by default; the toggle is shared). */
    sound?: boolean;
}

/** Arrow over the board: from and to are squares, color is green by default. */
export interface BoardArrow {
    from: string;
    to: string;
    color?: 'green' | 'red' | 'blue' | 'yellow';
}

/** Arrow colour by name (rgba with transparency so as not to hide pieces). */
const ARROW_COLORS: Record<NonNullable<BoardArrow['color']>, string> = {
    green: 'rgba(22, 163, 74, 0.85)',
    red: 'rgba(220, 38, 38, 0.85)',
    blue: 'rgba(37, 99, 235, 0.85)',
    yellow: 'rgba(234, 179, 8, 0.9)',
};

/** Dragging: the start square, the press point and the current point; moved says whether DRAG_THRESHOLD_PX was passed. */
interface Drag {
    from: string;
    startX: number;
    startY: number;
    x: number;
    y: number;
    moved: boolean;
}

/** Centre of a square in 0..8 coordinates taking board orientation into account. */
function squareCenter(square: string, orientation: 'white' | 'black'): [number, number] {
    const file = FILES.indexOf(square[0]);
    const rank = Number(square[1]) - 1;
    return orientation === 'white' ? [file + 0.5, 7 - rank + 0.5] : [7 - file + 0.5, rank + 0.5];
}

/** Triangle of the arrowhead at the destination square. */
function arrowHead(x1: number, y1: number, x2: number, y2: number): string {
    const length = Math.hypot(x2 - x1, y2 - y1) || 1;
    const ux = (x2 - x1) / length;
    const uy = (y2 - y1) / length;
    const tipX = x2 - ux * 0.15;
    const tipY = y2 - uy * 0.15;
    const baseX = tipX - ux * 0.4;
    const baseY = tipY - uy * 0.4;
    return `${tipX},${tipY} ${baseX - uy * 0.22},${baseY + ux * 0.22} ${baseX + uy * 0.22},${baseY - ux * 0.22}`;
}

/** Board square under a screen point (by the data-square attribute). */
function squareAt(x: number, y: number): string | null {
    const elements = typeof document.elementsFromPoint === 'function' ? document.elementsFromPoint(x, y) : [];
    const cell = elements.find((el) => el instanceof HTMLElement && el.dataset.square);
    return cell instanceof HTMLElement ? cell.dataset.square ?? null : null;
}

export function PuzzleBoard({
    fen, orientation, interactive, lastMove, hint, mark, onMove, onSquare, arrows = [], highlights = [], darkHighlights = [], ghost = null, stars = [],
    sound = true,
}: Props) {
    const {t} = useI18n();
    const [selection, setSelection] = useState<{ square: string; fen: string } | null>(null);
    const [promotion, setPromotion] = useState<{ from: string; to: string } | null>(null);
    const [drag, setDrag] = useState<Drag | null>(null);
    // The position editor (16.4) also shows an unfinished setup (without kings), which chess.js takes without validation.
    const game = useMemo(() => {
        try {
            return new Chess(fen);
        } catch {
            return new Chess(fen, {skipValidation: true});
        }
    }, [fen]);
    const selected = selection && selection.fen === fen && interactive && !onSquare ? selection.square : null;
    const themeKey = getSavedBoardThemeKey();
    const pieceSet = getSavedPieceSetKey();
    const theme = BOARD_THEMES[themeKey] || BOARD_THEMES.walnut;
    const ranks = orientation === 'white' ? ['8', '7', '6', '5', '4', '3', '2', '1'] : ['1', '2', '3', '4', '5', '6', '7', '8'];
    const files = orientation === 'white' ? FILES : [...FILES].reverse();
    const targets = useMemo(() => new Set(
        selected ? game.moves({square: selected as never, verbose: true}).map((m) => m.to as string) : [],
    ), [game, selected]);

    // Move sound: the position changed by the move lastMove from the previous position (one's own move, the opponent's reply, a lesson move).
    // A new puzzle or a jump to another step is not a move: no sound.
    const previousFen = useRef(fen);
    useEffect(() => {
        const before = previousFen.current;
        previousFen.current = fen;
        if (!sound || before === fen || !lastMove) return;
        const placement = fen.split(' ')[0];
        try {
            const played = new Chess(before).moves({square: lastMove.from as never, verbose: true})
                .find((m) => m.to === lastMove.to && m.after.split(' ')[0] === placement);
            if (played) soundEngine.play(resolveMoveSound(played.san));
        } catch {
            // The previous position cannot be parsed: simply no sound.
        }
    }, [fen, lastMove, sound]);
    const wrongMark = mark && !mark.ok ? mark.square : null;
    useEffect(() => {
        if (sound && wrongMark) soundEngine.play('illegal');
    }, [wrongMark, sound]);

    const select = (square: string | null) => setSelection(square ? {square, fen} : null);

    const ownPiece = (square: string) => {
        const piece = game.get(square as never);
        return Boolean(piece && piece.color === game.turn());
    };

    /** Move from -> to if it is legal; promotion goes through a piece choice. Returns whether a move was made. */
    const attempt = useCallback((from: string, to: string): boolean => {
        const candidates = game.moves({square: from as never, verbose: true}).filter((m) => m.to === to);
        if (candidates.length === 0) return false;
        setSelection(null);
        if (candidates.some((m) => m.promotion)) {
            setPromotion({from, to});
            return true;
        }
        onMove(`${from}${to}`);
        return true;
    }, [game, onMove]);

    const click = (square: string) => {
        if (!interactive || promotion) return;
        if (onSquare) {
            onSquare(square);
            return;
        }
        if (selected && selected !== square && attempt(selected, square)) return;
        select(ownPiece(square) ? square : null);
    };

    // Accessibility (task 26.3): on a board where moves are made, squares are buttons with a label ("e4, white knight"), arrows and
    // Enter/Space (like a click): a hook shared with the main board.
    const boardKeys = useBoardKeyboard(`${files[0]}${ranks[0]}`, orientation === 'black', click);

    const pointerDown = (square: string, event: ReactPointerEvent) => {
        if (!interactive || promotion || onSquare) return;
        if (event.pointerType === 'mouse' && event.button !== 0) return;
        if (!ownPiece(square)) return;  // someone else's piece or an empty square is a click (a capture, cancelling the selection)
        event.preventDefault();         // no text selection and no browser image "ghost"
        select(square);
        setDrag({from: square, startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY, moved: false});
    };

    useEffect(() => {
        if (!drag) return;
        const move = (event: PointerEvent) => {
            setDrag((current) => current && {
                ...current, x: event.clientX, y: event.clientY,
                moved: current.moved || Math.hypot(event.clientX - current.startX, event.clientY - current.startY) > DRAG_THRESHOLD_PX,
            });
        };
        const up = (event: PointerEvent) => {
            const from = drag.from;
            const target = squareAt(event.clientX, event.clientY);
            setDrag(null);
            // Released on another square: a move; on the same one or off the board, the piece stays selected (a click).
            if (target && target !== from) attempt(from, target);
        };
        const cancel = () => setDrag(null);
        window.addEventListener('pointermove', move);
        window.addEventListener('pointerup', up);
        window.addEventListener('pointercancel', cancel);
        return () => {
            window.removeEventListener('pointermove', move);
            window.removeEventListener('pointerup', up);
            window.removeEventListener('pointercancel', cancel);
        };
    }, [drag?.from, attempt]); // eslint-disable-line react-hooks/exhaustive-deps

    // The position changed in the middle of a drag (the opponent's reply, a new puzzle): the drag is cancelled.
    useEffect(() => setDrag(null), [fen, interactive]);

    const dragged = drag?.moved ? game.get(drag.from as never) : null;
    // The solver's right-button marks (task B.1): calculating variations in a puzzle; a new position clears them.
    const notes = useBoardAnnotations(fen);

    return (
        <div className="relative w-full aspect-square select-none touch-none" data-testid="puzzle-board"
             onPointerDown={notes.handlers.onPointerDown} onPointerUp={notes.handlers.onPointerUp}
             onContextMenu={(event) => event.preventDefault()}>
            <div className="grid grid-cols-8 grid-rows-8 w-full h-full border border-black/60 rounded-[2px] overflow-hidden"
                 role="group" aria-label={t('a11y.board')}>
                {ranks.map((rank) => files.map((file) => {
                    const square = `${file}${rank}`;
                    const piece = game.get(square as never);
                    const dark = (FILES.indexOf(file) + Number(rank)) % 2 === 1;
                    const isLast = lastMove && (lastMove.from === square || lastMove.to === square);
                    const isHint = hint && (hint.from === square || hint.to === square);
                    const lifted = Boolean(drag?.moved && drag.from === square);
                    const grabbable = interactive && !onSquare && !promotion && piece && piece.color === game.turn();
                    return (
                        <div key={square} data-square={square} onClick={() => click(square)}
                             {...(interactive ? boardKeys.squareProps(square) : {})}
                             aria-pressed={interactive ? selected === square : undefined}
                             aria-label={squareLabel(square, piece || null, t as Translate)}
                             onPointerDown={(event) => pointerDown(square, event)}
                             style={{backgroundColor: dark ? theme.dark : theme.light}}
                             className={`board-square relative flex items-center justify-center ${interactive ? 'cursor-pointer' : ''} ${grabbable ? 'cursor-grab' : ''}`}>
                            <BoardTextureLayer theme={theme} where="square" isDark={dark}/>
                            {isLast && <div className="absolute inset-0 pointer-events-none" style={{backgroundColor: lastMoveColor(theme)}}/>}
                            {darkHighlights.includes(square) && (
                                <div data-testid={`board-dark-${square}`} className="absolute inset-0 bg-stone-900/55 pointer-events-none"/>
                            )}
                            {highlights.includes(square) && (
                                <div data-testid={`board-highlight-${square}`}
                                     className="absolute inset-0 bg-sky-400/40 pointer-events-none"/>
                            )}
                            {stars.includes(square) && (
                                <span data-testid={`board-star-${square}`} aria-hidden="true"
                                      className={`absolute pointer-events-none text-yellow-400 drop-shadow-[0_1px_1px_rgba(0,0,0,0.8)] leading-none ${piece ? 'top-0.5 right-1 text-sm' : 'text-3xl'}`}>★</span>
                            )}
                            {ghost?.square === square && !piece && (
                                <img src={getPieceSvgUrl(pieceSet, ghost.piece[0] as 'w' | 'b', ghost.piece[1].toLowerCase())}
                                     alt="" aria-hidden="true" data-testid={`board-ghost-${square}`} draggable={false}
                                     className="absolute inset-0 w-full h-full object-contain opacity-40 pointer-events-none"/>
                            )}
                            {selected === square && <div className="absolute inset-0 bg-amber-400/50 pointer-events-none"/>}
                            {isHint && (
                                <div data-testid={`puzzle-hint-${square}`}
                                     className="absolute inset-0 ring-4 ring-inset ring-sky-400/90 pointer-events-none"/>
                            )}
                            {targets.has(square) && (
                                <div data-testid={`puzzle-target-${square}`}
                                     className="absolute w-1/4 h-1/4 rounded-full bg-black/25 pointer-events-none z-10"/>
                            )}
                            {piece && (
                                <img src={getPieceSvgUrl(pieceSet, piece.color, piece.type)} alt={`${piece.color}${piece.type}`}
                                     draggable={false}
                                     className={`w-full h-full object-contain pointer-events-none relative ${lifted ? 'opacity-30' : ''}`}
                                     style={getHarmoniousPieceStyle(pieceSet, themeKey, piece.color)}/>
                            )}
                            {mark?.square === square && (
                                <span data-testid={mark.ok ? 'puzzle-mark-ok' : 'puzzle-mark-wrong'}
                                      className={`absolute top-0.5 right-0.5 w-5 h-5 rounded-full text-[12px] leading-5 text-center font-bold text-white z-20 ${mark.ok ? 'bg-emerald-600' : 'bg-rose-600'}`}>
                                    {mark.ok ? '✓' : '✗'}
                                </span>
                            )}
                        </div>
                    );
                }))}
            </div>
            {arrows.length > 0 && (
                <svg viewBox="0 0 8 8" className="absolute inset-0 w-full h-full pointer-events-none z-20"
                     data-testid="board-arrows" aria-hidden="true">
                    {arrows.map((arrow, i) => {
                        const [x1, y1] = squareCenter(arrow.from, orientation);
                        const [x2, y2] = squareCenter(arrow.to, orientation);
                        const length = Math.hypot(x2 - x1, y2 - y1) || 1;
                        // The arrow ends a little before the square centre so that the arrowhead does not cover the piece.
                        const ex = x2 - ((x2 - x1) / length) * 0.3;
                        const ey = y2 - ((y2 - y1) / length) * 0.3;
                        const color = ARROW_COLORS[arrow.color ?? 'green'];
                        return (
                            <g key={`${arrow.from}${arrow.to}${i}`} data-testid={`board-arrow-${arrow.from}${arrow.to}`}>
                                <line x1={x1} y1={y1} x2={ex} y2={ey} stroke={color} strokeWidth={0.16} strokeLinecap="round"/>
                                <polygon points={arrowHead(x1, y1, x2, y2)} fill={color}/>
                            </g>
                        );
                    })}
                </svg>
            )}
            {drag && dragged && (
                <img src={getPieceSvgUrl(pieceSet, dragged.color, dragged.type)} alt="" aria-hidden="true" draggable={false}
                     data-testid="puzzle-drag-piece"
                     className="fixed w-[12%] max-w-[90px] aspect-square object-contain pointer-events-none z-50 -translate-x-1/2 -translate-y-1/2"
                     style={{left: drag.x, top: drag.y, ...getHarmoniousPieceStyle(pieceSet, themeKey, dragged.color)}}/>
            )}
            <AnnotationsOverlay arrows={notes.arrows} squares={notes.squares} flipped={orientation === 'black'}
                                idPrefix="puzzle-notes"/>
            {promotion && (
                <div className="absolute inset-0 bg-black/60 flex items-center justify-center z-30" role="dialog"
                     aria-label={t('puzzles.promotion')}>
                    <div className="flex gap-2 bg-acacia-dark p-3 rounded-md border border-amber-600">
                        {PROMOTIONS.map((type) => (
                            <button key={type} type="button" data-testid={`puzzle-promote-${type}`}
                                    onClick={() => {
                                        onMove(`${promotion.from}${promotion.to}${type}`);
                                        setPromotion(null);
                                    }}
                                    className="w-14 h-14 bg-boxwood/80 rounded hover:bg-boxwood cursor-pointer">
                                <img src={getPieceSvgUrl(pieceSet, game.turn(), type)} alt={type} className="w-full h-full"/>
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
