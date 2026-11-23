// --- FILE: frontend/src/components/chessboard/annotations.tsx ---
// Player marks on the board (task B.1): with the right button, drag an arrow or click a square; the colour is set by a modifier
// (none is green, Shift red, Alt blue, Ctrl or Shift+Alt yellow); repeating the same mark removes it,
// a left click on the board clears everything. For calculating variations in a live game and in puzzles; it does not affect the move.
// Mouse only (a touch screen has no right button); marks live in the component's memory: they are not sent to the server
// and are not visible to the opponent.

import {useCallback, useEffect, useRef, useState} from 'react';
import type {PointerEvent as ReactPointerEvent} from 'react';
import {squareCenter} from './CoachArrowsOverlay';

export type AnnotationColor = 'green' | 'red' | 'blue' | 'yellow';

export interface AnnotationArrow {
    from: string;
    to: string;
    color: AnnotationColor;
}

export const ANNOTATION_COLORS: Record<AnnotationColor, string> = {
    green: 'rgba(21, 128, 61, 0.8)',
    red: 'rgba(220, 38, 38, 0.8)',
    blue: 'rgba(37, 99, 235, 0.8)',
    yellow: 'rgba(234, 179, 8, 0.85)',
};

const ANNOTATION_KEYS = Object.keys(ANNOTATION_COLORS) as AnnotationColor[];

/** Mark colour by the held keys: Ctrl/Cmd or Shift+Alt is yellow, Shift is red, Alt is blue, otherwise green. */
export function annotationColor(event: { shiftKey: boolean; altKey: boolean; ctrlKey: boolean; metaKey: boolean }): AnnotationColor {
    if (event.ctrlKey || event.metaKey || (event.shiftKey && event.altKey)) return 'yellow';
    if (event.shiftKey) return 'red';
    if (event.altKey) return 'blue';
    return 'green';
}

/** Board square under a screen point (by the data-square attribute). */
function squareAt(x: number, y: number): string | null {
    const elements = typeof document.elementsFromPoint === 'function' ? document.elementsFromPoint(x, y) : [];
    const cell = elements.find((el) => el instanceof HTMLElement && el.dataset.square);
    return cell instanceof HTMLElement ? cell.dataset.square ?? null : null;
}

/** Arrow: repeating the same mark removes it, a different colour recolours it. */
export function toggleArrow(arrows: AnnotationArrow[], next: AnnotationArrow): AnnotationArrow[] {
    const same = arrows.find((a) => a.from === next.from && a.to === next.to);
    const rest = arrows.filter((a) => a !== same);
    return same && same.color === next.color ? rest : [...rest, next];
}

/** Ring on a square: the same colour removes it, a different one recolours it. */
export function toggleSquare(squares: Record<string, AnnotationColor>, square: string, color: AnnotationColor) {
    const next = {...squares};
    if (next[square] === color) delete next[square];
    else next[square] = color;
    return next;
}

/** What useBoardAnnotations returns: the marks themselves and pointer handlers for the board container. */
export interface BoardAnnotations {
    arrows: AnnotationArrow[];
    squares: Record<string, AnnotationColor>;
    /** Handlers for the board container (they work on squares too: the event bubbles up). */
    handlers: {
        onPointerDown: (event: ReactPointerEvent) => void;
        onPointerUp: (event: ReactPointerEvent) => void;
    };
    clear: () => void;
}

/**
 * Board marks. resetKey: marks are cleared when it changes (a move was made, a new puzzle). enabled=false:
 * the right button is left to the caller (for example, it cancels a premove). The square under the pointer is found by the
 * data-square attribute, so the caller's board squares must have it.
 */
export function useBoardAnnotations(resetKey: string, enabled = true): BoardAnnotations {
    const [arrows, setArrows] = useState<AnnotationArrow[]>([]);
    const [squares, setSquares] = useState<Record<string, AnnotationColor>>({});
    // Square where the right button was pressed: releasing on the same one makes a ring, on another one an arrow.
    const start = useRef<string | null>(null);

    const clear = useCallback(() => {
        setArrows((prev) => (prev.length ? [] : prev));
        setSquares((prev) => (Object.keys(prev).length ? {} : prev));
    }, []);

    // Reset only when resetKey changes, not on every render and not on first display.
    const lastKey = useRef(resetKey);
    useEffect(() => {
        if (lastKey.current === resetKey) return;
        lastKey.current = resetKey;
        clear();
    }, [resetKey, clear]);

    const onPointerDown = useCallback((event: ReactPointerEvent) => {
        if (event.pointerType !== 'mouse') return;
        if (event.button === 0) {
            clear();
            return;
        }
        if (event.button !== 2 || !enabled) return;
        start.current = squareAt(event.clientX, event.clientY);
    }, [clear, enabled]);

    const onPointerUp = useCallback((event: ReactPointerEvent) => {
        if (event.pointerType !== 'mouse' || event.button !== 2 || !enabled) return;
        const from = start.current;
        start.current = null;
        const to = squareAt(event.clientX, event.clientY);
        if (!from || !to) return;
        const color = annotationColor(event);
        if (from === to) setSquares((prev) => toggleSquare(prev, to, color));
        else setArrows((prev) => toggleArrow(prev, {from, to, color}));
    }, [enabled]);

    return {arrows, squares, handlers: {onPointerDown, onPointerUp}, clear};
}

interface OverlayProps {
    arrows: AnnotationArrow[];
    squares: Record<string, AnnotationColor>;
    flipped: boolean;
    /** Marker id prefix: a page may have several boards. */
    idPrefix?: string;
}

/** Layer of marks over the board: rings on squares and arrows. It does not intercept clicks; it is not drawn without marks. */
export function AnnotationsOverlay({arrows, squares, flipped, idPrefix = 'notes'}: OverlayProps) {
    const marked = Object.entries(squares);
    if (arrows.length === 0 && marked.length === 0) return null;
    return (
        <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full z-30 pointer-events-none"
             data-testid="board-annotations">
            <defs>
                {ANNOTATION_KEYS.map((color) => (
                    <marker key={color} id={`${idPrefix}-head-${color}`} markerWidth="3.5" markerHeight="3.5"
                            refX="2.3" refY="1.75" orient="auto">
                        <polygon points="0 0, 3.5 1.75, 0 3.5" fill={ANNOTATION_COLORS[color]}/>
                    </marker>
                ))}
            </defs>
            {marked.map(([square, color]) => {
                const center = squareCenter(square, flipped);
                if (!center) return null;
                return (
                    <circle key={`sq-${square}`} data-testid={`note-square-${square}`} data-color={color}
                            cx={center.x} cy={center.y} r="5.6" fill="none"
                            stroke={ANNOTATION_COLORS[color]} strokeWidth="0.9"/>
                );
            })}
            {arrows.map((arrow) => {
                const from = squareCenter(arrow.from, flipped);
                const to = squareCenter(arrow.to, flipped);
                if (!from || !to) return null;
                return (
                    <line key={`${arrow.from}-${arrow.to}`} data-testid={`note-arrow-${arrow.from}-${arrow.to}`}
                          data-color={arrow.color}
                          x1={from.x} y1={from.y} x2={to.x} y2={to.y}
                          stroke={ANNOTATION_COLORS[arrow.color]} strokeWidth="2.1" strokeLinecap="round"
                          markerEnd={`url(#${idPrefix}-head-${arrow.color})`}/>
                );
            })}
        </svg>
    );
}
