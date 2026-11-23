// --- FILE: frontend/src/components/chessboard/PlayerInfoBar.tsx ---
// Player bar above and below the board: avatar, name, rating (with the change after a game), berserk mark, captured pieces,
// material advantage and clock. Markup only, all numbers come from Chessboard: name and rating from the match_found event
// (in a bot game, from the bot profile), rating change from game_over, time from the useClock hook, captured pieces
// and advantage are computed from the position (calculateMaterialBalance).

import {Zap} from 'lucide-react';
import {formatTime} from './hooks/useClock';
import {useI18n} from '../../i18n';
import type {HistoricalBotProfile} from '../../config/champions';

export interface PlayerInfoBarProps {
    boardWidthPx: number;
    isResizing: boolean;
    /** Avatar of a historical bot instead of the default pawn placeholder, when the bot plays this side. */
    botProfile: HistoricalBotProfile | null;
    isWhiteSide: boolean;
    /** Label when no game is in progress yet (free analysis); set by the caller because it differs for the top/bottom bar. */
    idleLabel: string;
    /** A game (PvP/bot/spectating) is in progress; otherwise idleLabel and a time preview are shown instead of the clock. */
    showGameInfo: boolean;
    playerInfo: { username: string; rating: string };
    /** The player played "berserk" in an arena game (33.3): half the time without increment. */
    berserk?: boolean;
    /** The game has just ended and the server sent a rating change (may be absent for a particular side). */
    hasRatingInfo: boolean;
    ratingDelta?: number;
    /** Icons of the opponent's pieces captured by this side; empty in a game from a non-standard starting position. */
    capturedSymbols: string[];
    /** This side's material advantage in pawns; 0 means no advantage, the badge is not shown. */
    advantage: number;
    timeMs: number;
    /** Time of the selected control: shown on the clock while no game is in progress. */
    idlePreviewMs: number;
}

/**
 * Player bar above/below the board: avatar, name, rating (with the change after a game), captured
 * pieces, material advantage and clock. Used mirrored for the top and bottom side.
 */
export function PlayerInfoBar({
    boardWidthPx, isResizing, botProfile, isWhiteSide, idleLabel, showGameInfo, playerInfo,
    hasRatingInfo, ratingDelta, capturedSymbols, advantage, timeMs, idlePreviewMs, berserk = false,
}: PlayerInfoBarProps) {
    const {t} = useI18n();
    return (
        <div
            style={{width: `${boardWidthPx}px`}}
            className={`bg-acacia-dark px-3 py-1.5 rounded-lg shadow-heavy border-2 border-amber-900/50 flex justify-between items-center text-boxwood-light shrink-0 ${isResizing ? 'transition-none' : 'transition-colors'}`}
        >
            <div className="flex items-center gap-2.5 min-w-0">
                {botProfile ? (
                    <img
                        src={botProfile.avatar}
                        alt={botProfile.name}
                        onError={(e) => {
                            const img = e.target as HTMLImageElement;
                            if (!img.src.endsWith(botProfile.fallbackAvatar)) {
                                img.src = botProfile.fallbackAvatar;
                            }
                        }}
                        className="w-9 h-9 rounded-md object-cover border-2 border-amber-500/70 shrink-0 shadow"
                    />
                ) : (
                    <div
                        className={`w-9 h-9 rounded-md flex items-center justify-center border border-amber-600/30 font-bold text-lg shrink-0 ${
                            isWhiteSide ? 'bg-boxwood text-acacia-dark' : 'bg-acacia text-amber-200'
                        }`}
                    >
                        {isWhiteSide ? '♙' : '♟'}
                    </div>
                )}
                <div className="min-w-0">
                    <div className="font-bold text-sm sm:text-base flex items-center gap-2 leading-tight">
                        <span className="truncate">
                            {showGameInfo ? playerInfo.username : idleLabel}
                        </span>
                        {showGameInfo && (
                            <span
                                className="text-xs px-1.5 py-0.5 rounded bg-black/45 text-amber-400 border border-amber-600/25 flex items-center gap-1 font-mono">
                                {playerInfo.rating}
                                {hasRatingInfo && typeof ratingDelta === 'number' && (
                                    <span className={Number(ratingDelta) >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                                        ({Number(ratingDelta) >= 0 ? `+${ratingDelta}` : ratingDelta})
                                    </span>
                                )}
                            </span>
                        )}
                        {showGameInfo && berserk && (
                            <span role="img" aria-label={t('board.berserk')} title={t('board.berserk')}
                                  data-testid="berserk-mark" className="shrink-0 text-orange-400">
                                <Zap size={15} aria-hidden="true"/>
                            </span>
                        )}
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-amber-200/90 min-h-[16px]">
                        <span className="tracking-tight truncate">{capturedSymbols.join('')}</span>
                        {advantage > 0 && (
                            <span className="text-[11px] font-mono font-bold px-1.5 rounded bg-amber-900/60 text-amber-300">
                                +{advantage}
                            </span>
                        )}
                    </div>
                </div>
            </div>
            <div
                className="bg-[#1A120B] px-3.5 py-1 rounded-md border-2 border-amber-700/50 shadow-inner font-mono text-xl sm:text-2xl font-bold tracking-wider text-amber-400 min-w-[116px] sm:min-w-[124px] text-center">
                {showGameInfo ? formatTime(timeMs) : formatTime(idlePreviewMs)}
            </div>
        </div>
    );
}
