// --- FILE: frontend/src/components/chessboard/hooks/useBotGame.ts ---
// Bot game. It runs on the client: the browser keeps the position and clocks, the bot's move is requested from the server (/bots/move or
// /bots/custom-move) with a retry on a temporary failure, the "thinking" pause follows the time the server sent. After
// the game ends it is saved in full (/bots/save-game), and the server determines the result. Special games are also here: the club
// ladder, a tournament game, a handicap. Server requests: POST /bots/move (a historical bot, by its id), POST
// /bots/custom-move (a workshop opponent: the id of a saved one or the sliders themselves), POST /bots/draw-offer (a draw
// offer), POST /bots/save-game (saving; only for a signed-in player, a guest's game is not saved). The bot's remark
// arrives as a botComments.* catalog key; the server sends no text. Saving responds with the game id in the archive,
// a corrected result (if the server counts differently), and for the ladder and tournament, their result.

import {giverColor, oddsFen, oddsTimes} from '../odds';
import type {OddsChoice} from '../odds';
import {getBlindfold} from '../../../config/blindfold';
import {useCallback, useEffect, useRef, useState} from 'react';
import {Chess} from 'chess.js';
import {gameSocket} from '../../../services/gameSocket';
import {resolveMoveSound} from '../../../services/soundEngine';
import type {SoundEventType} from '../../../services/soundEngine';
import {API_BASE_URL} from '../../../config/api';
import {HISTORICAL_BOTS} from '../../../config/champions';
import type {BotOpponentId, HistoricalBotId, HistoricalBotProfile} from '../../../config/champions';
import {archetypeKey, customBotProfile} from '../../../config/archetypes';
import type {CustomOpponent} from '../../../config/archetypes';
import {cloneChessInstance, customStartFen} from '../boardUtils';
import {clocksAfterGap} from '../../../services/botGameSnapshot';
import type {BotGameSnapshot} from '../../../services/botGameSnapshot';
import type {PendingPromotion} from '../types';
import {readApiError} from '../../../services/apiErrors';
import {hasMessage, t, uiMessage} from '../../../i18n';
import type {MessageKey} from '../../../i18n';
import {messageParam, status} from '../status';
import type {GameStatus, StatusParam} from '../status';
import {getToken} from '../../../services/authToken';

// Pauses between retries of the bot move request; after the fourth attempt, every 8 s while the game is in progress.
const BOT_RETRY_DELAYS_MS = [1000, 2000, 4000, 8000];

/** 4xx, except 408/429, is a request error (position, bot): repeating the same request will not help. */
export function isPermanentBotError(status: number): boolean {
    return status >= 400 && status < 500 && status !== 408 && status !== 429;
}

/** Pause before retrying the bot move: the server's Retry-After (at most 10 s) or 1 -> 2 -> 4 -> 8 s. */
export function botRetryDelayMs(attempt: number, response: Response | null): number {
    const retryAfterS = Number(response?.headers.get('Retry-After'));
    if (retryAfterS > 0) return Math.min(retryAfterS, 10) * 1000;
    return BOT_RETRY_DELAYS_MS[Math.min(attempt, BOT_RETRY_DELAYS_MS.length - 1)];
}

/**
 * What the hook receives from Chessboard. The position, history, clocks, result and player cards belong to the component (useGameSocket
 * uses them too), so values and setters come in here, not own state.
 */
export interface UseBotGameOptions {
    game: Chess;
    myColor: 'white' | 'black';
    gameOverResult: string | null;
    whiteTimeMs: number;
    blackTimeMs: number;
    isSearching: boolean;
    setIsSearching: (v: boolean) => void;
    /**
     * Owned by the component, not by this hook: isTicking/isParticipant in useClock must know
     * about an active bot game before this hook gets called (useClock
     * is called earlier to hand resetLowTimeWarning/applyIncrement over to this one).
     */
    activeBot: BotOpponentId | null;
    setActiveBot: (id: BotOpponentId | null) => void;
    effectiveWhiteBaseMinutes: number;
    effectiveBlackBaseMinutes: number;
    effectiveIncSeconds: number;
    /** Handicap "hourglass clock": the clocks live in the component (useClock is called before this hook). */
    setHourglass?: (on: boolean) => void;
    currentUsername: string;
    currentUserRating: number;
    setGame: (g: Chess) => void;
    setHistory: (h: any[]) => void;
    setViewIndex: (i: number) => void;
    setSelectedSquare: (s: string | null) => void;
    setMyColor: (c: 'white' | 'black') => void;
    setIsManualFlip: (v: boolean) => void;
    setPendingPromotion: (p: PendingPromotion | null) => void;
    /** Clears the premove; used only at the start/end of a bot game. */
    clearPremove: () => void;
    setGameOverResult: (r: string | null) => void;
    setRatingInfo: (r: any) => void;
    setDrawOfferStatus: (s: GameStatus | null) => void;
    setRematchStatus: (s: 'none' | 'offered_by_me' | 'offered_by_opponent' | 'declined') => void;
    setWhiteTimeMs: (ms: number) => void;
    setBlackTimeMs: (ms: number) => void;
    resetLowTimeWarning: () => void;
    applyIncrement: (moverColor: 'white' | 'black', incrementSeconds: number) => void;
    moveStartTime: React.MutableRefObject<number>;
    myColorRef: React.MutableRefObject<'white' | 'black'>;
    gameIdRef: React.MutableRefObject<number | null>;
    setGameId: (id: number | null) => void;
    setWhitePlayer: (p: { username: string; rating: string }) => void;
    setBlackPlayer: (p: { username: string; rating: string }) => void;
    playAudio: (type: SoundEventType) => void;
    playOutcomeSound: (result: string, playerColor?: 'white' | 'black') => void;
    updateSessionStats: (result: string) => void;
    /** Playing with the coach (11.3): the bot waits while the player's move is being checked or the player decides whether to switch. */
    holdBot?: boolean;
    /** Whether the player used the coach in this game: the game is saved as a training one. */
    isAssisted?: () => boolean;
    /** Start of a new bot game: reset the coach state. */
    onNewGame?: () => void;
}

/**
 * Result of a club ladder game: the ladder field of the /bots/save-game response (or forfeited of the /bots/ladder/start response).
 * counted=false means the game is not counted, reason is the reason code (LADDER_REASONS in src/services/ladder.py).
 */
export interface LadderOutcome {
    counted: boolean;
    reason: string | null;
    delta: number;
    rating: number;
    step: number;
    promoted: boolean;
    opponent: string;
}

export interface BotGameStartOptions {
    /** Club ladder game: no take-backs, the result changes the ladder rating. */
    ladder?: boolean;
    /** Tournament game (task 15.3): no take-backs, the result is recorded in the tournament. */
    tournamentGameId?: number;
    /** Handicap (task 21.1): material means the starting position, time means the sides' clocks, "hourglass clock". */
    odds?: OddsChoice;
}

/** Ladder game result for the status line: counted gives the new rating and the change, otherwise the reason by the server code. */
export function ladderOutcomeMessage(outcome: LadderOutcome): GameStatus & { key: MessageKey } {
    if (!outcome.counted) {
        // The reason is a server code (ladder.reasons); an unknown one (a stale response) is shown as is.
        const reasonKey = `ladder.reasons.${outcome.reason ?? ''}`;
        const reason = hasMessage(reasonKey) ? messageParam(reasonKey) : (outcome.reason ?? '');
        return {key: 'ladder.notCounted', params: {reason}};
    }
    const delta = outcome.delta > 0 ? `+${outcome.delta}` : String(outcome.delta);
    return {key: outcome.promoted ? 'ladder.resultPromoted' : 'ladder.result', params: {rating: outcome.rating, delta}};
}

/** Bot remark for a move: a botComments catalog key and parameters; an unknown key gives no remark. */
export function botCommentMessage(comment: unknown): GameStatus | null {
    if (!comment || typeof comment !== 'object') return null;
    const {key, params} = comment as { key?: unknown; params?: unknown };
    const messageKey = `botComments.${String(key)}`;
    if (typeof key !== 'string' || !hasMessage(messageKey)) return null;
    const safeParams: Record<string, string | number> = {};
    if (params && typeof params === 'object') {
        for (const [name, value] of Object.entries(params as Record<string, unknown>)) {
            if (typeof value === 'string' || typeof value === 'number') safeParams[name] = value;
        }
    }
    return uiMessage(messageKey, safeParams);
}

export interface UseBotGameResult {
    selectedBotId: HistoricalBotId;
    setSelectedBotId: (id: HistoricalBotId) => void;
    /** Bot remark; null means the opponent's motto is shown. */
    botComment: GameStatus | null;
    isBotThinking: boolean;
    /** id of the saved game in the archive (the /bots/save-game response); null means the game is in progress or not saved. */
    savedBotGameId: number | null;
    /**
     * Starts a bot game: a historical bot by id or 'custom' (this is how startCustomBotGame calls it).
     * startFen starts the game from this position instead of the ordinary setup (a handicap is then not applied).
     */
    startHistoricalBotGame: (
        botId: BotOpponentId, colorPref?: 'white' | 'black' | 'random', startFen?: string | null,
        options?: BotGameStartOptions,
    ) => void;
    /** Game with a workshop opponent (a personality with sliders). */
    startCustomBotGame: (
        opponent: CustomOpponent, colorPref?: 'white' | 'black' | 'random', startFen?: string | null,
        options?: BotGameStartOptions,
    ) => void;
    /** A club ladder game is in progress (or was just played). */
    isLadderGame: boolean;
    /** A tournament game is in progress (or was just played). */
    isTournamentGame: boolean;
    /** Tournament that received the result of the last saved game (for the "To tournament" link). */
    savedTournamentId: number | null;
    /** Result of the last saved ladder game (to refresh the ladder panel). */
    ladderOutcome: LadderOutcome | null;
    /** Bot profile for the board and the panel: a historical one or one built in the workshop. */
    botProfileFor: (id: BotOpponentId) => HistoricalBotProfile;
    /** Bot name for the status line: translated at display time (for a workshop opponent, its own name). */
    botNameParam: (id: BotOpponentId) => StatusParam;
    /**
     * Saves a finished game (POST /bots/save-game), once per game. The server replays the moves and
     * determines the result itself. A game without moves is saved only if it counts (ladder, tournament).
     */
    saveBotGameToDatabase: (
        botId: BotOpponentId,
        playerColor: 'white' | 'black',
        result: string,
        completedGame: Chess,
        termination?: 'resignation' | 'timeout' | 'agreement',
    ) => Promise<void>;
    /** Offer the bot a draw (task 21.4): the answer is based on the position evaluation and the bot's attitude to draws. */
    offerDrawToBot: () => Promise<void>;
    /** Full exit from a bot game (matchmaking/challenge/rematch/sandbox reset). */
    exitBotGame: () => void;
    /** Archetype of the current (or last) workshop opponent, if it is an unchanged archetype. */
    customArchetypeId: () => string | null;
    /** Resumes a game from a snapshot (after a page reload): position, clocks and flags as they were. */
    resumeBotGame: (snapshot: BotGameSnapshot) => void;
    /** Flags of the game in progress for a snapshot: ladder, tournament game number, workshop opponent. */
    botGameInfo: () => { ladder: boolean; tournamentGameId: number | null; custom: CustomOpponent | null };
}

/**
 * Bot game, a historical bot or one built in the workshop: launch, requesting moves from /bots/move or
 * /bots/custom-move (with a retry on network failure, 5xx, 408 and 429), a loss on time,
 * a draw by offer, saving the finished game to the archive via /bots/save-game.
 */
export function useBotGame({
    game, myColor, gameOverResult, whiteTimeMs, blackTimeMs, isSearching, setIsSearching,
    activeBot, setActiveBot,
    effectiveWhiteBaseMinutes, effectiveBlackBaseMinutes, effectiveIncSeconds, setHourglass,
    currentUsername, currentUserRating,
    setGame, setHistory, setViewIndex, setSelectedSquare, setMyColor, setIsManualFlip, setPendingPromotion, clearPremove,
    setGameOverResult, setRatingInfo, setDrawOfferStatus, setRematchStatus,
    setWhiteTimeMs, setBlackTimeMs, resetLowTimeWarning, applyIncrement,
    moveStartTime, myColorRef, gameIdRef, setGameId, setWhitePlayer, setBlackPlayer,
    playAudio, playOutcomeSound, updateSessionStats, holdBot = false, isAssisted, onNewGame,
}: UseBotGameOptions): UseBotGameResult {
    const [selectedBotId, setSelectedBotId] = useState<HistoricalBotId>('philidor');
    const [botComment, setBotComment] = useState<GameStatus | null>(null);
    const [isBotThinking, setIsBotThinking] = useState<boolean>(false);
    const [savedBotGameId, setSavedBotGameId] = useState<number | null>(null);
    // The game has already been sent for saving: two places can notice the end of the game at once (a move and a flag).
    const botGameSavedRef = useRef<boolean>(false);
    // Workshop opponent of the current (or last) game is a ref, so that a move, saving and
    // a rematch read it without extra effect dependencies.
    const customOpponentRef = useRef<CustomOpponent | null>(null);
    // Flags of a counted game are both in a ref (saving reads them) and in state (Chessboard hides help by them).
    const ladderRef = useRef<boolean>(false);
    const [isLadderGame, setIsLadderGame] = useState<boolean>(false);
    const tournamentGameRef = useRef<number | null>(null);
    const [isTournamentGame, setIsTournamentGame] = useState<boolean>(false);
    const [savedTournamentId, setSavedTournamentId] = useState<number | null>(null);
    const [ladderOutcome, setLadderOutcome] = useState<LadderOutcome | null>(null);

    const botProfileFor = useCallback((id: BotOpponentId): HistoricalBotProfile => {
        if (id === 'custom') {
            return customBotProfile(customOpponentRef.current ?? {
                name: t('workshop.defaultName'), config: {} as CustomOpponent['config'],
            });
        }
        return HISTORICAL_BOTS[id];
    }, []);

    const botNameParam = useCallback((id: BotOpponentId): StatusParam => {
        if (id === 'custom') {
            const opponent = customOpponentRef.current;
            if (opponent?.archetypeId) return messageParam(`archetypes.${opponent.archetypeId}.name`);
            return opponent?.name || messageParam('workshop.defaultName');
        }
        return messageParam(`bots.profiles.${id}.shortName`);
    }, []);

    const saveBotGameToDatabase = useCallback(async (
        botId: BotOpponentId,
        playerColor: 'white' | 'black',
        result: string,
        completedGame: Chess,
        termination?: 'resignation' | 'timeout' | 'agreement'
    ) => {
        if (botGameSavedRef.current) return;
        const token = getToken();
        if (!token) return;
        const verboseMoves = completedGame.history({verbose: true});
        // Without moves only a counted game is saved (ladder, tournament): resigning before the first move is also a result.
        if (verboseMoves.length === 0 && !ladderRef.current && !tournamentGameRef.current) return;
        botGameSavedRef.current = true;
        const movesUci = verboseMoves.map((m: any) => `${m.from}${m.to}${m.promotion || ''}`);
        try {
            const response = await fetch(`${API_BASE_URL}/api/v1/bots/save-game`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'Authorization': `Bearer ${token}`},
                body: JSON.stringify({
                    bot_id: botId, player_color: playerColor, result,
                    ladder: ladderRef.current,
                    ...(tournamentGameRef.current ? {tournament_game_id: tournamentGameRef.current} : {}),
                    assisted: Boolean(isAssisted?.()),
                    // Blindfold play (task 19.5): the level and the peeks go to the archive.
                    ...(getBlindfold().level > 0 ? {blindfold: getBlindfold().level, peeks: getBlindfold().peeks} : {}),
                    // Workshop opponent: a saved one by id, an unsaved one by name.
                    ...(botId === 'custom' && customOpponentRef.current
                        ? (customOpponentRef.current.personalityId
                            ? {personality_id: customOpponentRef.current.personalityId}
                            // An unchanged archetype by key: in the archive its name will be in the player's language.
                            : {personality_name: customOpponentRef.current.archetypeId
                                ? archetypeKey(customOpponentRef.current.archetypeId)
                                : customOpponentRef.current.savedName ?? customOpponentRef.current.name})
                        : {}),
                    termination: termination ?? null, moves_uci: movesUci,
                    // A game from a custom position: the server checks the moves from the same position.
                    start_fen: customStartFen(completedGame),
                    base_time_ms: Math.round(effectiveWhiteBaseMinutes * 60 * 1000),
                    increment_ms: Math.round(effectiveIncSeconds * 1000)
                })
            });
            if (response.ok) {
                const data = await response.json();
                if (data.game_id) setSavedBotGameId(data.game_id);
                // The server judged otherwise (for example, the flag fell while the opponent lacked material, a draw):
                // its result stays on screen.
                if (data.result && data.result !== result) {
                    setGameOverResult(data.result);
                    setDrawOfferStatus(status('status.fideResult', {result: data.result}));
                }
                if (data.tournament_id) {
                    setSavedTournamentId(data.tournament_id);
                    // A hint, analysis, take-back or coach during a tournament game is a loss (task A.2).
                    const reasonKey = `tournaments.forfeitReasons.${data.tournament_forfeit ?? ''}`;
                    setDrawOfferStatus(data.tournament_forfeit
                        ? status('tournaments.forfeited', {
                            reason: hasMessage(reasonKey) ? messageParam(reasonKey as MessageKey) : String(data.tournament_forfeit),
                        })
                        : typeof data.rating_delta === 'number'
                            // All tournaments are rated (15.4): show the rating change.
                            ? status('tournaments.gameSavedRated', {
                                before: data.rating_before, after: data.rating_after,
                                delta: `${data.rating_delta >= 0 ? '+' : ''}${data.rating_delta}`,
                            })
                            : status('tournaments.gameSaved'));
                }
                if (data.ladder) {
                    setLadderOutcome(data.ladder);
                    setDrawOfferStatus(ladderOutcomeMessage(data.ladder));
                }
            }
        } catch (err) {
            console.error('Failed to save the bot game:', err);
        }
    }, [effectiveWhiteBaseMinutes, effectiveIncSeconds, setGameOverResult, setDrawOfferStatus, isAssisted]);

    // Common start of a bot game, new or resumed from a snapshot: resets the board state and sets the position, clocks,
    // player colour and side labels. The ladder, tournament and handicap flags are set by the caller.
    const enterBotGame = useCallback((
        botId: BotOpponentId, chosenColor: 'white' | 'black', freshGame: Chess, whiteStartMs: number, blackStartMs: number,
    ) => {
        const botInfo = botProfileFor(botId);

        botGameSavedRef.current = false;
        onNewGame?.();
        resetLowTimeWarning();
        setSavedBotGameId(null);
        gameIdRef.current = null;
        setGameId(null);
        if (botId !== 'custom') setSelectedBotId(botId);
        setActiveBot(botId);
        myColorRef.current = chosenColor;
        setMyColor(chosenColor);
        setIsManualFlip(false);
        setGame(freshGame);
        setHistory(freshGame.history({verbose: true}));
        setViewIndex(-1);
        setSelectedSquare(null);
        setPendingPromotion(null);
        clearPremove();
        setGameOverResult(null);
        setRatingInfo(null);
        setDrawOfferStatus(null);
        setRematchStatus('none');
        setWhiteTimeMs(whiteStartMs);
        setBlackTimeMs(blackStartMs);
        moveStartTime.current = Date.now();

        if (chosenColor === 'white') {
            setWhitePlayer({username: currentUsername, rating: String(currentUserRating)});
            setBlackPlayer({username: botInfo.playerLabel, rating: String(botInfo.rating)});
        } else {
            setWhitePlayer({username: botInfo.playerLabel, rating: String(botInfo.rating)});
            setBlackPlayer({username: currentUsername, rating: String(currentUserRating)});
        }

        setBotComment(null);
    }, [
        resetLowTimeWarning, gameIdRef, setGameId, setActiveBot, myColorRef, setMyColor, setIsManualFlip, setGame,
        setHistory, setViewIndex, setSelectedSquare, setPendingPromotion, clearPremove, setGameOverResult,
        setRatingInfo, setDrawOfferStatus, setRematchStatus, setWhiteTimeMs, setBlackTimeMs, moveStartTime,
        currentUsername, currentUserRating, setWhitePlayer, setBlackPlayer, botProfileFor, onNewGame,
    ]);

    const startHistoricalBotGame = useCallback((
        botId: BotOpponentId,
        colorPref: 'white' | 'black' | 'random' = 'random',
        startFen: string | null = null,
        options: BotGameStartOptions = {},
    ) => {
        ladderRef.current = Boolean(options.ladder);
        setIsLadderGame(Boolean(options.ladder));
        tournamentGameRef.current = options.tournamentGameId ?? null;
        setIsTournamentGame(Boolean(options.tournamentGameId));
        setSavedTournamentId(null);
        if (isSearching) {
            setIsSearching(false);
            gameSocket.send('leave_queue', {});
        }

        const chosenColor: 'white' | 'black' =
            colorPref === 'random'
                ? (Math.random() < 0.5 ? 'white' : 'black')
                : colorPref;

        // Handicap: material sets the starting position (unless the game started from a custom position), time
        // reduces the giver's clock, "hourglass clock" turns on a special clock mode in useClock.
        const odds = options.odds && options.odds.kind !== 'none' ? options.odds : null;
        const giver = odds ? giverColor(odds.giver, chosenColor) : 'white';
        const oddsStart = odds && !startFen ? oddsFen(odds.kind, giver) : null;
        const times = oddsTimes(odds?.kind ?? 'none', giver,
            Math.round(effectiveWhiteBaseMinutes * 60 * 1000), Math.round(effectiveBlackBaseMinutes * 60 * 1000));
        const whiteStartMs = times.white;
        const blackStartMs = times.black;
        setHourglass?.(odds?.kind === 'hourglass');
        const firstFen = startFen ?? oddsStart;
        const freshGame = firstFen ? new Chess(firstFen) : new Chess();
        enterBotGame(botId, chosenColor, freshGame, whiteStartMs, blackStartMs);
        playAudio('start');
    }, [
        isSearching, setIsSearching, effectiveWhiteBaseMinutes, effectiveBlackBaseMinutes, enterBotGame, playAudio,
        setHourglass,
    ]);

    // Resuming a game from a snapshot (services/botGameSnapshot.ts): the same entry into a game, but the position, clocks and flags
    // of the ladder and tournament come from the snapshot; the server is not notified of the start (for it the game is already running). No start sound.
    const resumeBotGame = useCallback((snapshot: BotGameSnapshot) => {
        const restored = new Chess();
        try {
            restored.loadPgn(snapshot.pgn);
        } catch {
            return;
        }
        ladderRef.current = snapshot.ladder;
        setIsLadderGame(snapshot.ladder);
        tournamentGameRef.current = snapshot.tournamentGameId;
        setIsTournamentGame(Boolean(snapshot.tournamentGameId));
        setSavedTournamentId(null);
        customOpponentRef.current = snapshot.botId === 'custom' ? snapshot.custom : null;
        setHourglass?.(snapshot.odds?.kind === 'hourglass');
        const clocks = clocksAfterGap(snapshot, restored.turn() === 'w');  // on pause the clocks do not run down
        enterBotGame(snapshot.botId as BotOpponentId, snapshot.color, restored, clocks.white, clocks.black);
    }, [enterBotGame, setHourglass]);

    const startCustomBotGame = useCallback((
        opponent: CustomOpponent,
        colorPref: 'white' | 'black' | 'random' = 'random',
        startFen: string | null = null,
        options: BotGameStartOptions = {},
    ) => {
        customOpponentRef.current = opponent;
        startHistoricalBotGame('custom', colorPref, startFen, options);
    }, [startHistoricalBotGame]);

    // Bot move: when it is the bot's turn, requests /bots/move (or /bots/custom-move), waits out the "thinking"
    // time from the response (thinking_time_ms minus the request time, not less than 80 ms) and applies the move. A change of
    // position, the end of the game or a coach pause (holdBot) cancels the request and the deferred move.
    useEffect(() => {
        if (!activeBot || gameOverResult || game.isGameOver() || holdBot) return;

        const currentTurnColor = game.turn() === 'w' ? 'white' : 'black';
        if (currentTurnColor === myColor) return;

        let isCancelled = false;
        let delayTimer: ReturnType<typeof setTimeout> | null = null;
        setIsBotThinking(true);
        const botName = botNameParam(activeBot);
        const requestStartedAt = Date.now();
        const custom = activeBot === 'custom' ? customOpponentRef.current : null;
        const moveUrl = custom ? `${API_BASE_URL}/api/v1/bots/custom-move` : `${API_BASE_URL}/api/v1/bots/move`;
        const moveBody = (fen: string) => (custom
            ? (custom.personalityId ? {fen, personality_id: custom.personalityId} : {fen, config: custom.config})
            : {bot_id: activeBot, fen});

        (async () => {
            try {
                const authToken = getToken();
                const headers: Record<string, string> = {'Content-Type': 'application/json'};
                // With a token the request limit is counted per user, not per shared IP.
                if (authToken) headers['Authorization'] = `Bearer ${authToken}`;

                // Temporary failures (network, server restart (deploy), 5xx, 429 (limit), 503 (engine
                // pool busy)) are retried while the game is in progress. Before, after a network error or a 500
                // the bot silently stopped moving and lost on time.
                let response: Response | null = null;
                for (let attempt = 0; !isCancelled; attempt++) {
                    try {
                        response = await fetch(moveUrl, {
                            method: 'POST',
                            headers,
                            body: JSON.stringify(moveBody(game.fen())),
                        });
                    } catch {
                        response = null;
                    }
                    if (response?.ok) break;
                    if (response && isPermanentBotError(response.status)) break;

                    if (attempt === 1 && !isCancelled) {
                        setBotComment(status('bots.noConnection'));
                    }
                    await new Promise((resolve) => setTimeout(resolve, botRetryDelayMs(attempt, response)));
                }
                if (isCancelled || !response) return;

                if (!response.ok) {
                    // A permanent error (invalid position, unknown bot): a retry will not help.
                    const detail = await readApiError(response);
                    setBotComment(status('bots.moveFailed', {
                        detail: detail ?? messageParam('bots.moveFailedStatus', {status: response.status}),
                    }));
                    setIsBotThinking(false);
                    return;
                }
                const data = await response.json();
                if (isCancelled) return;

                const targetThinkMs = typeof data.thinking_time_ms === 'number' ? data.thinking_time_ms : 600;
                const networkElapsed = Date.now() - requestStartedAt;
                const remainingDelay = Math.max(80, targetThinkMs - networkElapsed);

                delayTimer = setTimeout(() => {
                    if (isCancelled) return;

                    const from = data.uci.slice(0, 2);
                    const to = data.uci.slice(2, 4);
                    const promotion = data.uci.length > 4 ? data.uci.slice(4, 5) : 'q';

                    const nextGame = cloneChessInstance(game);
                    const moveObj = nextGame.move({from, to, promotion});

                    if (moveObj) {
                        const newHistory = nextGame.history({verbose: true});
                        const botColor: 'white' | 'black' = myColor === 'white' ? 'black' : 'white';

                        applyIncrement(botColor, effectiveIncSeconds);
                        setGame(nextGame);
                        setHistory(newHistory);
                        setViewIndex(-1);
                        setBotComment(botCommentMessage(data.comment));
                        moveStartTime.current = Date.now();

                        // On the final move only the outcome (win/loss/draw) is played:
                        // the sound of the move itself ("check" etc.) would be a redundant duplicate before it.
                        if (!nextGame.isGameOver()) {
                            playAudio(resolveMoveSound(moveObj.san));
                        }

                        if (nextGame.isGameOver()) {
                            let result = '1/2-1/2';
                            if (nextGame.isCheckmate()) {
                                result = nextGame.turn() === 'w' ? '0-1' : '1-0';
                            }
                            clearPremove();
                            setGameOverResult(result);
                            setDrawOfferStatus(status('status.botGameOver', {bot: botName, result}));
                            updateSessionStats(result);
                            playOutcomeSound(result, myColor);
                            saveBotGameToDatabase(activeBot, myColor, result, nextGame);
                        }
                    }
                    setIsBotThinking(false);
                }, remainingDelay);
            } catch (err) {
                console.error('Failed to get the bot move:', err);
                if (!isCancelled) {
                    setIsBotThinking(false);
                }
            }
        })();

        return () => {
            isCancelled = true;
            if (delayTimer) clearTimeout(delayTimer);
        };
    }, [activeBot, game, myColor, gameOverResult, holdBot, playAudio, playOutcomeSound, updateSessionStats, saveBotGameToDatabase, applyIncrement, effectiveIncSeconds, setGame, setHistory, setViewIndex, clearPremove, setGameOverResult, setDrawOfferStatus, moveStartTime, botNameParam]);

    // Loss on time in a bot game: time ran out for either side (the bot's clock runs too while it is "thinking").
    // The result here is preliminary; the final one is returned by the server on saving.
    useEffect(() => {
        if (!activeBot || gameOverResult) return;

        if (whiteTimeMs <= 0 || blackTimeMs <= 0) {
            const flagWinner = whiteTimeMs <= 0 ? '0-1' : '1-0';
            const botName = botNameParam(activeBot);
            clearPremove();
            setPendingPromotion(null);
            setGameOverResult(flagWinner);
            setDrawOfferStatus(status('status.botFlagFell', {bot: botName, result: flagWinner}));
            updateSessionStats(flagWinner);
            playOutcomeSound(flagWinner, myColor);
            saveBotGameToDatabase(activeBot, myColor, flagWinner, game, 'timeout');
        }
    }, [whiteTimeMs, blackTimeMs, activeBot, gameOverResult, myColor, game, playOutcomeSound, updateSessionStats, saveBotGameToDatabase, clearPremove, setPendingPromotion, setGameOverResult, setDrawOfferStatus, botNameParam]);

    const exitBotGame = useCallback(() => {
        ladderRef.current = false;
        setIsLadderGame(false);
        tournamentGameRef.current = null;
        setIsTournamentGame(false);
        setActiveBot(null);
        setBotComment(null);
        setIsBotThinking(false);
        setSavedBotGameId(null);
        botGameSavedRef.current = false;
    }, [setActiveBot]);

    const customArchetypeId = useCallback(() => customOpponentRef.current?.archetypeId ?? null, []);
    const botGameInfo = useCallback(() => ({
        ladder: ladderRef.current, tournamentGameId: tournamentGameRef.current, custom: customOpponentRef.current,
    }), []);

    const offerDrawToBot = useCallback(async () => {
        if (!activeBot || gameOverResult) return;
        // In the ladder and tournament the server does not remember the bot's agreement: a draw there is on the board only.
        if (ladderRef.current || tournamentGameRef.current) {
            setDrawOfferStatus(status('status.botDrawNotHere'));
            return;
        }
        const custom = activeBot === 'custom' ? customOpponentRef.current : null;
        const myColorNow = myColorRef.current;
        const body = {
            fen: game.fen(), bot_id: activeBot, bot_color: myColorNow === 'white' ? 'black' : 'white',
            ...(custom ? (custom.personalityId ? {personality_id: custom.personalityId} : {config: custom.config}) : {}),
        };
        const token = getToken();
        setDrawOfferStatus(status('status.drawOfferSent'));
        try {
            const res = await fetch(`${API_BASE_URL}/api/v1/bots/draw-offer`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json', ...(token ? {Authorization: `Bearer ${token}`} : {})},
                body: JSON.stringify(body),
            });
            if (!res.ok) {
                setDrawOfferStatus(status('status.botDrawFailed'));
                return;
            }
            const data = await res.json() as { accepted: boolean; comment: unknown };
            setBotComment(botCommentMessage(data.comment));
            if (!data.accepted) {
                setDrawOfferStatus(status('status.botDrawDeclined', {bot: botNameParam(activeBot)}));
                return;
            }
            const result = '1/2-1/2';
            setGameOverResult(result);
            setDrawOfferStatus(status('status.botDrawAccepted', {bot: botNameParam(activeBot)}));
            updateSessionStats(result);
            playOutcomeSound(result, myColorNow);
            await saveBotGameToDatabase(activeBot, myColorNow, result, game, 'agreement');
        } catch {
            setDrawOfferStatus(status('status.botDrawFailed'));
        }
    }, [activeBot, gameOverResult, game, setDrawOfferStatus, setGameOverResult, updateSessionStats, playOutcomeSound,
        saveBotGameToDatabase, botNameParam, myColorRef]);

    return {
        selectedBotId, setSelectedBotId, botComment, isBotThinking, savedBotGameId,
        startHistoricalBotGame, startCustomBotGame, botProfileFor, botNameParam, saveBotGameToDatabase, exitBotGame,
        isLadderGame, ladderOutcome, customArchetypeId, isTournamentGame, savedTournamentId, offerDrawToBot,
        resumeBotGame, botGameInfo,
    };
}
