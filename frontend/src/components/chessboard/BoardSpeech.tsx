// --- FILE: frontend/src/components/chessboard/BoardSpeech.tsx ---
// Board accessibility (task 26.3): the last move is announced in words in a live region (aria-live), so a screen reader
// speaks every move, the player's and the opponent's; the "Position in words" button shows the setup as text. The words are in
// services/a11y/speech.ts. In blindfold play (blind) the position description is unavailable: it would reveal hidden pieces, while moves
// are announced, as they are spoken aloud in blindfold play anyway.

import {useState} from 'react';
import {Volume2} from 'lucide-react';
import {useI18n} from '../../i18n';
import {moveWords, positionWords} from '../../services/a11y/speech';
import type {BoardPiece, Translate, VerboseMove} from '../../services/a11y/speech';

interface Props {
    /** Last move of the game (chess.js verbose); null means no moves yet. */
    lastMove: VerboseMove | null;
    /** Displayed position (chess.js board()). */
    board: (BoardPiece | null)[][];
    /** Blindfold play is on: do not show the position in words. */
    blind: boolean;
}

export function BoardSpeech({lastMove, board, blind}: Props) {
    const {t} = useI18n();
    const tr = t as Translate;
    const [open, setOpen] = useState(false);
    return (
        <div className="w-full flex flex-col items-start gap-1 text-xs">
            <p className="sr-only" aria-live="polite" data-testid="move-announcer">{lastMove ? moveWords(lastMove, tr) : ''}</p>
            <button type="button" onClick={() => setOpen((v) => !v)} disabled={blind} aria-expanded={open && !blind}
                    data-testid="describe-position"
                    className="flex items-center gap-1 text-amber-300/80 hover:text-amber-200 disabled:opacity-40 cursor-pointer disabled:cursor-default">
                <Volume2 size={13} aria-hidden/> {t(open && !blind ? 'a11y.describeHide' : 'a11y.describe')}
            </button>
            {open && !blind && (
                <p className="text-boxwood-light/90 leading-snug" data-testid="position-words">{positionWords(board, tr)}</p>
            )}
        </div>
    );
}
