// --- FILE: frontend/src/components/puzzles/usePositionExplorer.tsx ---
// Free review after an answer (owner's feedback 18.11): when a puzzle or a trainer question is solved, the board does not
// freeze with an arrow: the move made stands on it, and the position can be played out for both sides, a move taken back or
// a return made to the puzzle position. Moves are checked by chess.js (legality is the same as on the PuzzleBoard board). The hook keeps
// only the line from the puzzle position; there are no engine evaluations or hints: it is not analysis but "moving the pieces" (fair play
// is not affected: during one's own game against a human the trainers are closed anyway by the section's rules).
// In-memory state only (no network or localStorage). Used by PuzzlesPage, DefenseTrainer, GeneratedDrills,
// GuessPage, learn/MateCourse and trainers/{CalcGames, MiniatureGame, StructureQuiz}.

import {useCallback, useMemo, useState} from 'react';
import {Chess} from 'chess.js';
import {RotateCcw, Undo2} from 'lucide-react';
import {useI18n} from '../../i18n';

/** Review line: the puzzle position and the UCI moves played from it (the starting position does not change). */
interface Line {
    start: string;
    moves: string[];
}

/** Hook interface: what to show on the board and how to change the review line. */
export interface PositionExplorer {
    /** Review is on (after an answer). */
    active: boolean;
    /** Position on the board: the starting one plus the played moves. */
    fen: string | null;
    /** Last move of the line, for highlighting on the board. */
    lastMove: { from: string; to: string } | null;
    /** How many moves have been played from the puzzle position. */
    plies: number;
    /** Turn the review on from position fen, playing the moves moves at once (for example, the player's answer). */
    start: (fen: string, moves?: string[]) => void;
    /** Play a UCI move for the side to move; an illegal one gives false and the board does not change. */
    play: (uci: string) => boolean;
    /** Take one move back. */
    back: () => void;
    /** Return to the puzzle position (the line is cleared, the review stays on). */
    reset: () => void;
    /** Turn the review off (a new puzzle or exercise). */
    stop: () => void;
}

/** Position after the line's moves; illegal moves at the end are dropped. */
function replay(line: Line): { fen: string; last: { from: string; to: string } | null; plies: number } {
    const game = new Chess(line.start);
    let last: { from: string; to: string } | null = null;
    let plies = 0;
    for (const uci of line.moves) {
        try {
            game.move({from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] ?? 'q'});
        } catch {
            break;
        }
        last = {from: uci.slice(0, 2), to: uci.slice(2, 4)};
        plies += 1;
    }
    return {fen: game.fen(), last, plies};
}

/** Free review hook: keeps only the move line, the board position is recomputed by replay() each time. */
export function usePositionExplorer(): PositionExplorer {
    const [line, setLine] = useState<Line | null>(null);
    const view = useMemo(() => (line ? replay(line) : null), [line]);

    const start = useCallback((fen: string, moves: string[] = []) => {
        // A position that chess.js does not accept (for example, a single piece without kings in "How many moves?"): the review is not
        // turned on, the board stays as it was.
        try {
            new Chess(fen);
        } catch {
            setLine(null);
            return;
        }
        const played = replay({start: fen, moves});
        setLine({start: fen, moves: moves.slice(0, played.plies)});
    }, []);
    const play = useCallback((uci: string) => {
        if (!line || !view) return false;
        const game = new Chess(view.fen);
        try {
            game.move({from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] ?? 'q'});
        } catch {
            return false;
        }
        setLine({...line, moves: [...line.moves.slice(0, view.plies), uci]});
        return true;
    }, [line, view]);
    const back = useCallback(() => setLine((l) => (l ? {...l, moves: l.moves.slice(0, -1)} : l)), []);
    const reset = useCallback(() => setLine((l) => (l ? {...l, moves: []} : l)), []);
    const stop = useCallback(() => setLine(null), []);

    return {
        active: line !== null, fen: view?.fen ?? null, lastMove: view?.last ?? null, plies: view?.plies ?? 0,
        start, play, back, reset, stop,
    };
}

/** Review buttons under the board: a move back and to the puzzle position; a hint that the board is free. */
export function ExplorerControls({explorer}: { explorer: PositionExplorer }) {
    const {t} = useI18n();
    if (!explorer.active) return null;
    return (
        <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="explorer-controls">
            <span className="text-boxwood/70">{t('puzzles.explore.hint')}</span>
            <button type="button" onClick={explorer.back} disabled={explorer.plies === 0} data-testid="explorer-back"
                    className="px-2 py-1 rounded bg-black/30 border border-amber-900/50 flex items-center gap-1 disabled:opacity-40">
                <Undo2 size={12}/> {t('puzzles.explore.back')}
            </button>
            <button type="button" onClick={explorer.reset} disabled={explorer.plies === 0} data-testid="explorer-reset"
                    className="px-2 py-1 rounded bg-black/30 border border-amber-900/50 flex items-center gap-1 disabled:opacity-40">
                <RotateCcw size={12}/> {t('puzzles.explore.toStart')}
            </button>
        </div>
    );
}
