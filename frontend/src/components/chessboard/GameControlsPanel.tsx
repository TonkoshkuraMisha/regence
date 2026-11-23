// --- FILE: frontend/src/components/chessboard/GameControlsPanel.tsx ---
// Game control buttons under the move list. Three modes with different sets of actions: a game against a human (cancel before the
// first moves, resign, draw, berserk in an arena, rematch), a game against a bot (take back, resign, draw, rematch) and a
// free board (reset, take back, position from FEN). After a game against a human or a bot: "Review" (the page
// /game/{id}) and PGN download (GET /profile/games/{id}/pgn). The component itself sends nothing: the actions are
// performed by Chessboard (WebSocket for a game against a human, the useBotGame hook for a bot).

import {useState} from 'react';
import {Flag, Handshake, X, RefreshCw, RotateCcw, Undo2, Eye, Download, Grid3x3, Zap, Pause, Play} from 'lucide-react';
import type {NavigateFunction} from 'react-router-dom';
import {API_BASE_URL} from '../../config/api';
import {useI18n} from '../../i18n';

/** Rematch state after a game against a human (WebSocket events rematch_offered and rematch_declined). */
export type RematchStatus = 'none' | 'offered_by_me' | 'offered_by_opponent' | 'declined';

export interface GameControlsPanelProps {
    /** A game against a human (in progress or just finished), a game against a bot (any) or the free board. */
    mode: 'pvp' | 'bot' | 'sandbox';
    gameId: number | null;
    /** id of the bot game in the archive: appears after saving (/bots/save-game); without it there is no review or PGN. */
    savedBotGameId: number | null;
    historyLength: number;
    gameOverResult: string | null;
    rematchStatus: RematchStatus;
    isBotThinking: boolean;
    whitePlayer: { username: string; rating: string };
    blackPlayer: { username: string; rating: string };
    navigate: NavigateFunction;
    onAbortGame: () => void;
    /** Pause of a bot game (friendly only): a toggle; undefined means no pause (ladder, tournament, game over). */
    onPauseToggle?: () => void;
    paused?: boolean;
    /** Arena game before its first move (33.3): "berserk" is half the time without increment for an extra point. */
    onBerserk?: () => void;
    onResign: () => void;
    onOfferDraw: () => void;
    onAcceptRematch: () => void;
    onDeclineRematch: () => void;
    onOfferRematch: () => void;
    /** Reset of the free board; after a game against a human the same handler is the "To lobby" button. */
    onResetSandbox: () => void;
    /** Take back a move: on the free board and in a bot game (there together with the bot's reply). */
    onUndoSandboxMove: () => void;
    /** A club ladder or tournament game is in progress: taking back is forbidden. */
    undoLocked?: boolean;
    /** The free board holds a position loaded from FEN (reset is available even without moves). */
    hasCustomPosition?: boolean;
    /** Sets a position from FEN on the free board; returns an error text or null. */
    onLoadFen?: (fen: string) => string | null;
    /** Tournament game: no rematch; after the game the tournament banner leads on (next game, standings). */
    hideRematch?: boolean;
}

/**
 * Game control buttons under the move log: three independent modes (PvP/bot/sandbox),
 * because the set of available actions (resign vs cancel, rematch vs return to lobby...) differs in each.
 */
export function GameControlsPanel({
    mode, gameId, savedBotGameId, historyLength, gameOverResult, rematchStatus, isBotThinking,
    whitePlayer, blackPlayer, navigate, onAbortGame, onResign, onOfferDraw, onAcceptRematch,
    onDeclineRematch, onOfferRematch, onResetSandbox, onUndoSandboxMove, undoLocked = false, hasCustomPosition = false, onLoadFen,
    hideRematch = false, onBerserk, onPauseToggle, paused = false,
}: GameControlsPanelProps) {
    const {t} = useI18n();
    const [fenInput, setFenInput] = useState('');
    const [fenError, setFenError] = useState<string | null>(null);

    const submitFen = (e: React.FormEvent) => {
        e.preventDefault();
        if (!onLoadFen || !fenInput.trim()) return;
        const error = onLoadFen(fenInput);
        setFenError(error);
        if (!error) setFenInput('');
    };

    // Going to the review: names, ratings and result are passed in the route state: the game page (GameViewer) takes
    // them first, and the PGN headers when there is no state (direct entry by address). The fallback rating is for a
    // side with no number on the card.
    const navigateToReview = (reviewGameId: number, site?: string, blackRatingFallback = 1200) => navigate(`/game/${reviewGameId}`, {
        state: {
            game: {
                game_id: reviewGameId,
                white_username: whitePlayer.username,
                white_rating: Number(whitePlayer.rating) || 1200,
                black_username: blackPlayer.username,
                black_rating: Number(blackPlayer.rating) || blackRatingFallback,
                result: gameOverResult || '*',
                ...(site ? {site} : {}),
                finished_at: new Date().toISOString()
            }
        }
    });

    // Game against a human: while fewer than two plies have been made, "Cancel" (the game is not counted), after that
    // "Resign"; a draw can be offered from the same moment.
    if (mode === 'pvp') {
        return (
            <div className="shrink-0 flex flex-col gap-1.5">
                {onBerserk && !gameOverResult && (
                    <button
                        type="button"
                        onClick={onBerserk}
                        title={t('controls.berserkHint')}
                        data-testid="berserk-button"
                        className="flex items-center justify-center gap-1.5 px-3 py-2 bg-orange-950/90 text-orange-200 text-xs sm:text-sm font-bold rounded-md hover:bg-orange-900 transition shadow border border-orange-600/60 cursor-pointer"
                    >
                        <Zap size={15}/> {t('controls.berserk')}
                    </button>
                )}
                <div className="grid grid-cols-2 gap-2">
                    {historyLength < 2 ? (
                        <button
                            type="button"
                            onClick={onAbortGame}
                            disabled={!!gameOverResult}
                            className="flex items-center justify-center gap-1.5 px-3 py-2 bg-amber-950/90 text-amber-200 text-xs sm:text-sm font-bold rounded-md hover:bg-amber-900 transition shadow border border-amber-700/60 disabled:opacity-40 cursor-pointer"
                        >
                            <X size={15}/> {t('controls.abort')}
                        </button>
                    ) : (
                        <button
                            type="button"
                            onClick={onResign}
                            disabled={!!gameOverResult}
                            className="flex items-center justify-center gap-1.5 px-3 py-2 bg-red-950/85 text-red-200 text-xs sm:text-sm font-bold rounded-md hover:bg-red-900 transition shadow border border-red-800/50 disabled:opacity-40 cursor-pointer"
                        >
                            <Flag size={15}/> {t('controls.resign')}
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={onOfferDraw}
                        disabled={!!gameOverResult || historyLength < 2}
                        className="flex items-center justify-center gap-1.5 px-3 py-2 bg-acacia-dark text-boxwood-light text-xs sm:text-sm font-bold rounded-md hover:bg-black/50 transition shadow border border-amber-700/30 disabled:opacity-40 cursor-pointer"
                    >
                        <Handshake size={15}/> {t('controls.offerDraw')}
                    </button>
                </div>

                {gameOverResult && (
                    <div className="flex flex-col gap-1.5">
                        {rematchStatus === 'offered_by_opponent' ? (
                            <div
                                className="p-2 rounded-md bg-emerald-950/90 border border-emerald-500/60 flex flex-col gap-1.5 text-xs text-emerald-100 text-center shadow">
                                <span className="font-bold">{t('controls.rematchOffered')}</span>
                                <div className="grid grid-cols-2 gap-2">
                                    <button
                                        type="button"
                                        onClick={onAcceptRematch}
                                        className="py-1.5 px-3 bg-emerald-700 hover:bg-emerald-600 text-white font-bold rounded transition shadow cursor-pointer"
                                    >
                                        {t('controls.acceptRematch')}
                                    </button>
                                    <button
                                        type="button"
                                        onClick={onDeclineRematch}
                                        className="py-1.5 px-3 bg-red-900/80 hover:bg-red-800 text-red-100 font-bold rounded transition cursor-pointer"
                                    >
                                        {t('common.decline')}
                                    </button>
                                </div>
                            </div>
                        ) : (
                            <div className="grid grid-cols-2 gap-2">
                                <button
                                    type="button"
                                    disabled={rematchStatus === 'offered_by_me' || rematchStatus === 'declined'}
                                    onClick={onOfferRematch}
                                    className="flex items-center justify-center gap-1.5 px-3 py-2 font-bold text-xs sm:text-sm rounded-md transition shadow bg-emerald-800 hover:bg-emerald-700 text-emerald-100 border border-emerald-500/50 disabled:opacity-50 cursor-pointer"
                                >
                                    <RefreshCw size={15}
                                               className={rematchStatus === 'offered_by_me' ? 'animate-spin' : ''}/>
                                    {rematchStatus === 'offered_by_me'
                                        ? t('controls.waitingAnswer')
                                        : rematchStatus === 'declined'
                                            ? t('controls.rematchDeclined')
                                            : t('controls.rematch')}
                                </button>
                                <button
                                    type="button"
                                    onClick={onResetSandbox}
                                    className="flex items-center justify-center gap-1.5 px-3 py-2 font-bold text-xs sm:text-sm rounded-md transition shadow bg-boxwood text-acacia-dark border border-amber-700/50 hover:bg-boxwood-light cursor-pointer"
                                >
                                    <RotateCcw size={15}/> {t('controls.toLobby')}
                                </button>
                            </div>
                        )}

                        {/* A cancelled game has no moves or PGN: nothing to review or download. */}
                        {gameOverResult !== '*' && <div className="grid grid-cols-2 gap-2">
                            <button
                                type="button"
                                onClick={() => gameId && navigateToReview(gameId)}
                                className="flex items-center justify-center gap-1.5 px-3 py-1.5 bg-emerald-900/80 hover:bg-emerald-800 text-emerald-100 text-xs font-bold rounded-md transition shadow border border-emerald-600/50 cursor-pointer"
                            >
                                <Eye size={14}/> {t('common.gameReview')}
                            </button>
                            <a
                                href={`${API_BASE_URL}/api/v1/profile/games/${gameId}/pgn`}
                                download
                                className="flex items-center justify-center gap-1.5 px-3 py-1.5 bg-[#1A120B] hover:bg-black text-amber-400 text-xs font-bold rounded-md transition shadow border border-amber-800/60"
                            >
                                <Download size={14}/> {t('common.downloadPgn')}
                            </a>
                        </div>}
                    </div>
                )}
            </div>
        );
    }

    if (mode === 'bot') {
        return (
            <div className="shrink-0 flex flex-col gap-1.5">
                <div className="flex flex-col gap-1.5">
                    {!(hideRematch && gameOverResult) && <div className="grid grid-cols-2 gap-2">
                        <button
                            type="button"
                            disabled={historyLength === 0 || isBotThinking || !!gameOverResult || undoLocked}
                            title={undoLocked ? t('ladder.undoLocked') : undefined}
                            onClick={onUndoSandboxMove}
                            className="flex items-center justify-center gap-1.5 px-3 py-2 bg-acacia-dark text-boxwood-light text-xs sm:text-sm font-bold rounded-md hover:bg-black/50 transition shadow border border-amber-700/30 disabled:opacity-40 cursor-pointer"
                        >
                            <Undo2 size={15}/> {t('controls.undoMove')}
                        </button>
                        {!gameOverResult && onPauseToggle && (
                            <button
                                type="button"
                                onClick={onPauseToggle}
                                data-testid="bot-pause"
                                className="col-span-2 flex items-center justify-center gap-1.5 px-3 py-2 bg-acacia-dark text-boxwood-light text-xs sm:text-sm font-bold rounded-md hover:bg-black/50 transition shadow border border-amber-700/30 cursor-pointer"
                            >
                                {paused ? <Play size={15}/> : <Pause size={15}/>} {t(paused ? 'controls.resume' : 'controls.pause')}
                            </button>
                        )}
                        {!gameOverResult ? (
                            <button
                                type="button"
                                onClick={onResign}
                                className="flex items-center justify-center gap-1.5 px-3 py-2 bg-red-950/85 text-red-200 text-xs sm:text-sm font-bold rounded-md hover:bg-red-900 transition shadow border border-red-800/50 cursor-pointer"
                            >
                                <Flag size={15}/> {t('controls.resign')}
                            </button>
                        ) : (
                            <button
                                type="button"
                                onClick={onOfferRematch}
                                className="flex items-center justify-center gap-1.5 px-3 py-2 bg-emerald-800 text-emerald-100 text-xs sm:text-sm font-bold rounded-md hover:bg-emerald-700 transition shadow border border-emerald-500/50 cursor-pointer"
                            >
                                <RefreshCw size={15}/> {t('controls.rematch')}
                            </button>
                        )}
                    </div>}
                    {/* Draw with a bot (task 21.4): the bot answers based on the position evaluation and its attitude to draws. */}
                    {!gameOverResult && historyLength >= 2 && (
                        <button
                            type="button"
                            onClick={onOfferDraw}
                            disabled={isBotThinking}
                            data-testid="bot-offer-draw"
                            className="flex items-center justify-center gap-1.5 px-3 py-1.5 bg-acacia-dark text-boxwood-light text-xs font-bold rounded-md hover:bg-black/50 transition shadow border border-amber-700/30 disabled:opacity-40 cursor-pointer"
                        >
                            <Handshake size={14}/> {t('controls.offerDraw')}
                        </button>
                    )}

                    {savedBotGameId && (
                        <div className="grid grid-cols-2 gap-2">
                            <button
                                type="button"
                                onClick={() => navigateToReview(savedBotGameId, 'Regence Bot Arena', 1850)}
                                className="flex items-center justify-center gap-1.5 px-3 py-1.5 bg-emerald-900/80 hover:bg-emerald-800 text-emerald-100 text-xs font-bold rounded-md transition shadow border border-emerald-600/50 cursor-pointer"
                            >
                                <Eye size={14}/> {t('common.gameReview')}
                            </button>
                            <a
                                href={`${API_BASE_URL}/api/v1/profile/games/${savedBotGameId}/pgn`}
                                download
                                className="flex items-center justify-center gap-1.5 px-3 py-1.5 bg-[#1A120B] hover:bg-black text-amber-400 text-xs font-bold rounded-md transition shadow border border-amber-800/60"
                            >
                                <Download size={14}/> {t('common.downloadPgn')}
                            </a>
                        </div>
                    )}
                </div>
            </div>
        );
    }

    return (
        <div className="shrink-0 flex flex-col gap-1.5">
            {onLoadFen && (
                <form onSubmit={submitFen} className="flex flex-col gap-1">
                    <div className="flex gap-1.5">
                        <input
                            type="text"
                            value={fenInput}
                            onChange={(e) => {
                                setFenInput(e.target.value);
                                setFenError(null);
                            }}
                            maxLength={100}
                            spellCheck={false}
                            aria-label={t('controls.fenLabel')}
                            placeholder={t('controls.fenPlaceholder')}
                            className="flex-1 min-w-0 px-2 py-1.5 rounded bg-black/40 border border-amber-900/60 text-boxwood-light text-xs font-mono outline-none focus:border-amber-500"
                        />
                        <button
                            type="submit"
                            disabled={!fenInput.trim()}
                            title={t('controls.setPositionHint')}
                            className="px-2.5 py-1.5 rounded border border-amber-700/50 bg-black/45 text-amber-200 text-xs font-bold hover:bg-black/65 transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5 shrink-0"
                        >
                            <Grid3x3 size={13}/> {t('controls.setPosition')}
                        </button>
                    </div>
                    {fenError && <div role="alert" className="text-xs text-red-300">{fenError}</div>}
                </form>
            )}
            <div className="grid grid-cols-2 gap-2">
                <button
                    type="button"
                    disabled={historyLength === 0}
                    onClick={onUndoSandboxMove}
                    className="flex items-center justify-center gap-1.5 px-3 py-2 bg-acacia-dark text-boxwood-light text-xs sm:text-sm font-bold rounded-md hover:bg-black/50 transition shadow border border-amber-700/30 disabled:opacity-40 cursor-pointer"
                >
                    <Undo2 size={15}/> {t('controls.undoSandbox')}
                </button>
                <button
                    type="button"
                    disabled={historyLength === 0 && !hasCustomPosition}
                    onClick={onResetSandbox}
                    className="flex items-center justify-center gap-1.5 px-3 py-2 bg-acacia-dark text-amber-300 text-xs sm:text-sm font-bold rounded-md hover:bg-black/50 transition shadow border border-amber-700/30 disabled:opacity-40 cursor-pointer"
                >
                    <RotateCcw size={15}/> {t('controls.resetBoard')}
                </button>
            </div>
        </div>
    );
}
