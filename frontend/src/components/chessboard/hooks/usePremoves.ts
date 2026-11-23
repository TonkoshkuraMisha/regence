// --- FILE: frontend/src/components/chessboard/hooks/usePremoves.ts ---
// Premoves: a queue of moves set during the opponent's turn (no more than MAX_PREMOVES). The board shows the position "as
// if the premoves were played"; the first premove is executed as soon as the opponent has moved, and if it became illegal,
// the queue is cleared. The queue lives only in the browser: the server knows nothing about premoves until the next one is
// sent as an ordinary move (make_move with the is_premove flag). Works in games against a human and a bot.

import {useCallback, useEffect, useMemo, useState} from 'react';
import {Chess} from 'chess.js';
import type {PromotionPiece} from '../boardUtils';
import type {SoundEventType} from '../../../services/soundEngine';

export interface Premove {
    from: string;
    to: string;
    promotion?: PromotionPiece;
}

export interface UsePremovesOptions {
    game: Chess;
    myColor: 'white' | 'black';
    gameOverResult: string | null;
    /** -1 is the live position; any other value is history viewing, premoves are not executed. */
    viewIndex: number;
    /** Premoves make sense only in PvP and bot games, not in free analysis. */
    isOpponentControlled: boolean;
    /** Ordinary board move (Chessboard.executeMove); returns false if the move is impossible. */
    executeMove: (from: string, to: string, explicitPromotion?: PromotionPiece, isPremoveMove?: boolean) => boolean;
    playAudio: (type: SoundEventType) => void;
    /** Clears the square selection and aborts the current drag so that a premove starts "clean". */
    clearSelection: () => void;
    /** Opens the piece choice dialog for a promotion premove (with isPremove: true, the choice comes back here). */
    openPromotionDialog: (p: { from: string; to: string; color: 'w' | 'b'; isPremove: true }) => void;
}

/** How many premoves can be set in a row. */
export const MAX_PREMOVES = 8;

/**
 * Position "as if the premoves were already played": pieces are simply rearranged (without rules checking, which happens on execution),
 * castling moves the rook too, a promotion places the chosen piece. It is used to pick pieces for the next premoves
 * and to draw the board while the queue is non-empty.
 */
export function applyPremoves(game: Chess, premoves: Premove[]): Chess {
    const view = new Chess(game.fen());
    for (const move of premoves) {
        const piece = view.get(move.from as never);
        if (!piece) continue;
        view.remove(move.from as never);
        view.put(move.promotion ? {type: move.promotion, color: piece.color} : piece, move.to as never);
        const fileShift = move.to.charCodeAt(0) - move.from.charCodeAt(0);
        if (piece.type === 'k' && Math.abs(fileShift) === 2) {
            const rank = move.from[1];
            const [rookFrom, rookTo] = fileShift > 0 ? [`h${rank}`, `f${rank}`] : [`a${rank}`, `d${rank}`];
            const rook = view.get(rookFrom as never);
            if (rook && rook.type === 'r' && rook.color === piece.color) {
                view.remove(rookFrom as never);
                view.put(rook, rookTo as never);
            }
        }
    }
    return view;
}

export interface UsePremovesResult {
    /** First premove of the queue (it will be executed next). */
    premove: Premove | null;
    /** The whole premove queue. */
    premoves: Premove[];
    /** Position after the queue's premoves (see applyPremoves). */
    premoveView: Chess;
    /** null clears the whole queue; a premove replaces the queue with itself alone. */
    setPremove: (value: Premove | null) => void;
    /** Puts a move into a premove (or opens the promotion dialog); called on the opponent's turn. */
    scheduleOrPromotePremove: (from: string, to: string, explicitPromotion?: PromotionPiece) => void;
}

/**
 * Premove: while the opponent is to move, the player can specify their next moves in advance (up to MAX_PREMOVES). As soon as
 * the position confirms that it is the player's turn, the first premove is executed automatically through
 * executeMove with isPremoveMove=true: the client reports zero think time and the is_premove flag. The clock is
 * still run by the server by its own time; the flag is needed by anti-cheat (such a move is not counted in the move rhythm, and
 * the server trusts the flag only if it itself sees an almost instant move).
 */
export function usePremoves({
    game, myColor, gameOverResult, viewIndex, isOpponentControlled, executeMove, playAudio,
    clearSelection, openPromotionDialog,
}: UsePremovesOptions): UsePremovesResult {
    const [premoves, setPremoves] = useState<Premove[]>([]);
    const premoveView = useMemo(() => (premoves.length ? applyPremoves(game, premoves) : game), [game, premoves]);
    const setPremove = useCallback((value: Premove | null) => setPremoves(value ? [value] : []), []);

    const scheduleOrPromotePremove = useCallback((from: string, to: string, explicitPromotion?: PromotionPiece) => {
        if (from === to) return;
        // The piece comes from the square where it will be after the already placed premoves (a chain: Nf3, then Ng5).
        const piece = premoveView.get(from as never);
        const myColorChar = myColor === 'white' ? 'w' : 'b';
        if (!piece || piece.color !== myColorChar) {
            clearSelection();
            return;
        }

        const targetRank = to[1];
        const isPawnPromotion =
            piece.type === 'p' &&
            ((piece.color === 'w' && targetRank === '8') || (piece.color === 'b' && targetRank === '1'));

        if (isPawnPromotion && !explicitPromotion) {
            openPromotionDialog({from, to, color: myColorChar, isPremove: true});
            clearSelection();
            return;
        }

        const next = {from, to, promotion: isPawnPromotion ? (explicitPromotion || 'q') : undefined};
        // Beyond MAX_PREMOVES a premove does not enter the queue (the sound still plays).
        setPremoves((queue) => (queue.length >= MAX_PREMOVES ? queue : [...queue, next]));
        playAudio('premove');
        clearSelection();
    }, [premoveView, myColor, playAudio, clearSelection, openPromotionDialog]);

    // Execution: fires on every new position; waits until the turn passes to the player and the board shows the live position.
    useEffect(() => {
        if (premoves.length === 0 || gameOverResult || viewIndex !== -1 || !isOpponentControlled) return;

        const currentTurnColor = game.turn() === 'w' ? 'white' : 'black';
        if (currentTurnColor !== myColor) return;

        // The first premove is executed; if it became impossible (the opponent replied differently), the whole queue is cleared:
        // the rest were built on it.
        const [first, ...rest] = premoves;
        const played = executeMove(first.from, first.to, first.promotion || 'q', true);
        setPremoves(played ? rest : []);
    }, [game, premoves, isOpponentControlled, myColor, gameOverResult, viewIndex, executeMove]);

    return {premove: premoves[0] ?? null, premoves, premoveView, setPremove, scheduleOrPromotePremove};
}
