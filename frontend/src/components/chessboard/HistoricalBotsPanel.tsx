// --- FILE: frontend/src/components/chessboard/HistoricalBotsPanel.tsx ---
// Choice of a bot opponent: historical bots and masters with a portrait, years of life and strength (measured, if the bot
// is calibrated: GET /bots/catalog), choice of colour, handicap and starting from one's own position. The bot list, portraits and years are in
// config/champions.ts; names, titles and mottos are the bots.profiles.* catalog. Only numbers come from the server: measured
// strength and strength from games against humans (GET /bots/catalog), the bot's memory of the player (GET /bots/rivalry); they are loaded by
// Chessboard. At the bottom is the bot's remark on the last move (a botComments.* catalog key, already translated by the caller).

import {hasGiver, ODDS} from './odds';
import type {OddsChoice, OddsGiver, OddsKind} from './odds';
import {Link} from 'react-router-dom';
import {MessageSquareQuote} from 'lucide-react';
import {HISTORICAL_BOTS_LIST} from '../../config/champions';
import type {BotOpponentId, HistoricalBotId, HistoricalBotProfile} from '../../config/champions';
import {useI18n} from '../../i18n';
import {scorePoints} from '../../services/botCatalog';
import type {BotRival} from '../../services/botCatalog';

export interface HistoricalBotsPanelProps {
    /** Bot selected in the list (its card is shown), not necessarily the one the game is being played against. */
    selectedBotId: HistoricalBotId;
    onSelectBot: (id: HistoricalBotId) => void;
    selectedBotProfile: HistoricalBotProfile;
    /** Opponent of the current (or just played) bot game; null means no bot game. */
    activeBot: BotOpponentId | null;
    activeBotProfile: HistoricalBotProfile | null;
    /** id of a human game: while it is in progress, a bot game cannot be started. */
    gameId: number | null;
    gameOverResult: string | null;
    isBotThinking: boolean;
    /** Bot remark in the player's language; null means the generic phrase bots.defaultThought is shown. */
    botComment: string | null;
    onStartBotGame: (botId: HistoricalBotId, colorPref: 'white' | 'black' | 'random') => void;
    /** The free board holds a custom position: a bot game can be started from it. */
    canStartFromPosition: boolean;
    startFromPosition: boolean;
    onStartFromPositionChange: (value: boolean) => void;
    /** Measured strength (GET /bots/catalog): bot id -> rating; without calibration, the declared one. */
    measured?: Record<string, number>;
    /** Strength from games against humans (task 32.1): bot id -> rating and number of games. */
    live?: Record<string, { rating: number; games: number }>;
    /** Memory of the opponent (task 32.2): bot id -> games with the player and the bot's points. */
    rivals?: Record<string, BotRival>;
    /** Handicap (task 21.1); without a handler the choice is not shown. */
    odds?: OddsChoice;
    onOddsChange?: (odds: OddsChoice) => void;
}

/**
 * Choice of a historical bot, a card with its motto/rating and game start buttons. The handicap is unavailable when
 * starting from a custom position (a material handicap defines the starting position itself).
 */
export function HistoricalBotsPanel({
    selectedBotId, onSelectBot, selectedBotProfile, activeBot, activeBotProfile, gameId,
    gameOverResult, isBotThinking, botComment, onStartBotGame,
    canStartFromPosition, startFromPosition, onStartFromPositionChange, measured = {}, live = {}, rivals = {}, odds, onOddsChange,
}: HistoricalBotsPanelProps) {
    const {t} = useI18n();
    return (
        <div
            className="flex-1 min-h-0 bg-acacia-dark p-2.5 rounded-md border border-amber-700/40 flex flex-col justify-between gap-2 shadow-inner overflow-y-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-amber-900/50">
            <div className="grid grid-cols-2 gap-1.5">
                {HISTORICAL_BOTS_LIST.map((botItem) => {
                    const isSelected = selectedBotId === botItem.id;
                    return (
                        <button
                            key={botItem.id}
                            type="button"
                            onClick={() => onSelectBot(botItem.id)}
                            className={`p-1.5 rounded-md text-left transition cursor-pointer flex items-center gap-2 border ${
                                isSelected
                                    ? 'bg-amber-800/80 text-white border-amber-400 shadow'
                                    : 'bg-black/35 text-boxwood/85 border-amber-900/40 hover:border-amber-600/50 hover:bg-black/55'
                            }`}
                        >
                            <img
                                src={botItem.avatar}
                                alt={botItem.shortName}
                                onError={(e) => {
                                    const img = e.target as HTMLImageElement;
                                    if (!img.src.endsWith(botItem.fallbackAvatar)) {
                                        img.src = botItem.fallbackAvatar;
                                    }
                                }}
                                className={`w-8 h-8 rounded-full object-cover shrink-0 border ${
                                    isSelected ? 'border-amber-300' : 'border-amber-700/60'
                                }`}
                            />
                            <div className="min-w-0 flex-1">
                                <div className="text-xs font-bold truncate leading-tight">
                                    {botItem.shortName}
                                </div>
                                <div className="text-[11px] font-mono text-amber-300/90">
                                    {t('bots.eloShort', {rating: measured[botItem.id] ?? botItem.rating})}{measured[botItem.id] ? t('bots.measuredMark') : ''}
                                </div>
                            </div>
                        </button>
                    );
                })}
            </div>

            <div className="p-2.5 rounded-md bg-black/40 border border-amber-800/50 flex flex-col gap-2">
                <div className="flex items-center gap-2.5">
                    <img
                        src={selectedBotProfile.avatar}
                        alt={selectedBotProfile.name}
                        onError={(e) => {
                            const img = e.target as HTMLImageElement;
                            if (!img.src.endsWith(selectedBotProfile.fallbackAvatar)) {
                                img.src = selectedBotProfile.fallbackAvatar;
                            }
                        }}
                        className="w-12 h-12 rounded-lg object-cover border-2 border-amber-500/80 shadow-md shrink-0"
                    />
                    <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-1">
                            <span className="text-sm font-bold text-amber-200 truncate">
                                {selectedBotProfile.name}
                            </span>
                            {activeBot === selectedBotProfile.id && !gameOverResult && (
                                <span
                                    className="text-[11px] font-bold px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-600/50 shrink-0">
                                    {t('bots.inGame')}
                                </span>
                            )}
                        </div>
                        <div className="text-xs text-amber-400 font-semibold">
                            {selectedBotProfile.title}
                        </div>
                        <div className="text-[11px] text-boxwood/75 font-mono">
                            {t('bots.eraAndRating', {
                                era: selectedBotProfile.era,
                                rating: measured[selectedBotProfile.id] ?? selectedBotProfile.rating,
                            })}
                            {t(measured[selectedBotProfile.id] ? 'bots.ratingMeasured' : 'bots.ratingDeclared')}
                            {' '}
                            <Link to="/transparency" className="underline hover:text-amber-300" data-testid="bot-strength-how">
                                {t('bots.howMeasured')}
                            </Link>
                        </div>
                        {live[selectedBotProfile.id] && (
                            <div className="text-[11px] text-boxwood/75 font-mono" data-testid="bot-live-strength">
                                {t('bots.liveStrength', live[selectedBotProfile.id])}
                            </div>
                        )}
                        {rivals[selectedBotProfile.id] && (() => {
                            const rival = rivals[selectedBotProfile.id];
                            return (
                                <div className="text-[11px] text-amber-300" data-testid="bot-rivalry">
                                    {t(rival.remembers ? 'bots.remembersYou' : 'bots.metYou', {
                                        name: selectedBotProfile.shortName, games: rival.games,
                                        you: scorePoints(rival.games - rival.bot_points), bot: scorePoints(rival.bot_points),
                                    })}
                                </div>
                            );
                        })()}
                    </div>
                </div>

                <p className="text-xs italic text-boxwood/90 leading-snug bg-black/30 p-2 rounded border border-amber-900/30">
                    {t('bots.quote', {text: selectedBotProfile.motto})}
                </p>

                {canStartFromPosition && (
                    <label className="flex items-center gap-2 text-xs text-amber-200 cursor-pointer select-none">
                        <input
                            type="checkbox"
                            checked={startFromPosition}
                            onChange={(e) => onStartFromPositionChange(e.target.checked)}
                            className="accent-amber-600"
                        />
                        {t('common.startFromPosition')}
                    </label>
                )}

                {odds && onOddsChange && (
                    <div className="flex flex-wrap items-center gap-1.5 text-xs text-amber-200" data-testid="odds-picker">
                        <label className="flex items-center gap-1.5 min-w-0">
                            {t('odds.label')}
                            <select value={odds.kind} disabled={canStartFromPosition && startFromPosition}
                                    onChange={(e) => onOddsChange({...odds, kind: e.target.value as OddsKind})}
                                    data-testid="odds-kind" className="bg-black/40 rounded px-1 py-0.5 min-w-0 max-w-[11rem] disabled:opacity-50">
                                {ODDS.map((kind) => <option key={kind} value={kind}>{t(`odds.kinds.${kind}`)}</option>)}
                            </select>
                        </label>
                        {hasGiver(odds.kind) && (
                            <select value={odds.giver} onChange={(e) => onOddsChange({...odds, giver: e.target.value as OddsGiver})}
                                    aria-label={t('odds.giver')} data-testid="odds-giver" className="bg-black/40 rounded px-1 py-0.5">
                                <option value="opponent">{t('odds.opponentGives')}</option>
                                <option value="me">{t('odds.iGive')}</option>
                            </select>
                        )}
                    </div>
                )}

                <div className="grid grid-cols-3 gap-1.5">
                    <button
                        type="button"
                        disabled={!!gameId && !gameOverResult}
                        onClick={() => onStartBotGame(selectedBotId, 'white')}
                        className="py-1.5 px-2 text-xs font-bold rounded-md bg-boxwood text-acacia-dark hover:bg-boxwood-light disabled:opacity-40 transition cursor-pointer shadow"
                    >
                        {t('common.playAsWhite')}
                    </button>
                    <button
                        type="button"
                        disabled={!!gameId && !gameOverResult}
                        onClick={() => onStartBotGame(selectedBotId, 'random')}
                        className="py-1.5 px-2 text-xs font-bold rounded-md bg-amber-700 text-white border border-amber-500/50 hover:bg-amber-600 disabled:opacity-40 transition cursor-pointer shadow"
                    >
                        {t('common.playRandom')}
                    </button>
                    <button
                        type="button"
                        disabled={!!gameId && !gameOverResult}
                        onClick={() => onStartBotGame(selectedBotId, 'black')}
                        className="py-1.5 px-2 text-xs font-bold rounded-md bg-black/70 text-amber-200 border border-amber-700/60 hover:bg-black disabled:opacity-40 transition cursor-pointer shadow"
                    >
                        {t('common.playAsBlack')}
                    </button>
                </div>
            </div>

            {activeBotProfile && (
                <div className="p-2 rounded-md bg-black/55 border border-amber-600/40 text-xs text-amber-100">
                    <div className="font-bold text-amber-400 mb-0.5 flex items-center justify-between text-xs">
                        <span className="flex items-center gap-1.5">
                            <MessageSquareQuote size={13}/> {t('bots.thought', {name: activeBotProfile.shortName})}
                        </span>
                        {isBotThinking && (
                            <span className="animate-pulse text-amber-300 font-mono text-[11px]">
                                {t('bots.thinking')}
                            </span>
                        )}
                    </div>
                    <div className="text-xs text-boxwood-light leading-snug">
                        {botComment || t('bots.defaultThought')}
                    </div>
                </div>
            )}
        </div>
    );
}
