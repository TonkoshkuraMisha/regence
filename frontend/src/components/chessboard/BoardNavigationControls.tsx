// --- FILE: frontend/src/components/chessboard/BoardNavigationControls.tsx ---
// Game rewind buttons on the main board: to the start, one move back, one move forward, to the live position. Markup only:
// which position to show (viewIndex) is decided by Chessboard; the same actions are on the arrow keys.

import {ChevronFirst, ChevronLeft, ChevronRight, ChevronLast} from 'lucide-react';
import {useI18n} from '../../i18n';

export interface BoardNavigationControlsProps {
    historyLength: number;
    /** -1 is the live position, -2 is the very start of the game (before the first move). */
    viewIndex: number;
    onFirst: () => void;
    onBack: () => void;
    onForward: () => void;
    onLast: () => void;
}

/**
 * Move-log rewind buttons: they duplicate the arrow keys (left and right step a move, up goes to the start,
 * down goes to the live position). "Back" is disabled at the start of the game, "forward" on the live position.
 */
export function BoardNavigationControls({
    historyLength, viewIndex, onFirst, onBack, onForward, onLast,
}: BoardNavigationControlsProps) {
    const {t} = useI18n();
    return (
        <div
            className="bg-acacia-dark p-2 rounded-md border border-amber-900/40 flex items-center justify-between shrink-0">
            <span className="text-xs font-semibold text-boxwood/80 pl-1">{t('board.navigation')}</span>
            <div className="flex gap-1.5">
                <button
                    type="button"
                    disabled={historyLength === 0 || viewIndex === -2}
                    onClick={onFirst}
                    className="p-1.5 bg-acacia rounded hover:bg-boxwood hover:text-acacia-dark disabled:opacity-30 transition cursor-pointer"
                    title={t('board.toStart')}
                >
                    <ChevronFirst size={16}/>
                </button>
                <button
                    type="button"
                    disabled={historyLength === 0 || viewIndex === -2}
                    onClick={onBack}
                    className="p-1.5 bg-acacia rounded hover:bg-boxwood hover:text-acacia-dark disabled:opacity-30 transition cursor-pointer"
                    title={t('board.back')}
                >
                    <ChevronLeft size={16}/>
                </button>
                <button
                    type="button"
                    disabled={historyLength === 0 || viewIndex === -1}
                    onClick={onForward}
                    className="p-1.5 bg-acacia rounded hover:bg-boxwood hover:text-acacia-dark disabled:opacity-30 transition cursor-pointer"
                    title={t('board.forward')}
                >
                    <ChevronRight size={16}/>
                </button>
                <button
                    type="button"
                    disabled={historyLength === 0 || viewIndex === -1}
                    onClick={onLast}
                    className="p-1.5 bg-acacia rounded hover:bg-boxwood hover:text-acacia-dark disabled:opacity-30 transition cursor-pointer"
                    title={t('board.toEnd')}
                >
                    <ChevronLast size={16}/>
                </button>
            </div>
        </div>
    );
}
