// --- FILE: frontend/src/components/chessboard/hooks/useBoardKeyboard.ts ---
// Board from the keyboard (task 26.3): squares are buttons, one square enters the Tab order (keySquare: the last one that
// had focus, otherwise the top-left on screen), arrows move focus across the screen (for a flipped board too, by screen,
// stepSquare from services/a11y/speech.ts), Enter or Space does the same as a click on a square. The square label ("e4, white
// knight") is set by the board itself, squareLabel. Shared by the main board (Chessboard.tsx) and the puzzle and trainer board
// (puzzles/PuzzleBoard.tsx). No network or data.

import {useRef, useState} from 'react';
import type {KeyboardEvent as ReactKeyboardEvent} from 'react';
import {stepSquare} from '../../../services/a11y/speech';

/**
 * Board keyboard: firstSquare is the square Tab starts from if the board has not had focus yet; flipped means the board
 * is flipped; activate is the Enter/Space action (like a click). Returns the square properties for the markup.
 */
export function useBoardKeyboard(firstSquare: string, flipped: boolean, activate: (square: string) => void) {
    const [focused, setFocused] = useState<string | null>(null);
    const refs = useRef<Record<string, HTMLElement | null>>({});
    const keySquare = focused ?? firstSquare;

    const onKeyDown = (event: ReactKeyboardEvent<HTMLElement>, square: string) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            event.stopPropagation();
            activate(square);
            return;
        }
        if (!event.key.startsWith('Arrow')) return;
        event.preventDefault();
        event.stopPropagation();
        const next = stepSquare(square, event.key, flipped);
        setFocused(next);
        refs.current[next]?.focus();
    };

    /** Properties of a button square: a ref for focus, role, position in the Tab order, and key and focus handlers. */
    const squareProps = (square: string) => ({
        ref: (element: HTMLElement | null) => {
            refs.current[square] = element;
        },
        role: 'button' as const,
        tabIndex: square === keySquare ? 0 : -1,
        onKeyDown: (event: ReactKeyboardEvent<HTMLElement>) => onKeyDown(event, square),
        onFocus: () => setFocused(square),
    });

    return {keySquare, squareProps};
}
