// --- FILE: frontend/src/components/chessboard/hooks/useGameSocket.ts ---
// Matchmaking, a PvP game over WebSocket, lobby/spectators and chat. The main game state
// (game/history/viewIndex/gameId/myColor/gameOverResult etc.) stays in Chessboard.tsx as
// plain useState and is passed here as parameters: it is needed equally by this hook and by useBotGame
// (a bot game uses the same game/history/gameOverResult/... fields), and the hook call order
// does not let any one of them be the sole owner without a dependency cycle.
//
// Where the data comes from. WebSocket (services/gameSocket.ts, the server is src/api/websockets.py), events: connected,
// match_found (game start or restore), move_made (a move: position, clocks, state version), game_over (the result
// and rating change), berserk, draw_offered / draw_declined, rematch_offered / rematch_declined, invite_created,
// spectate_started, chat_message, error (a refusal with a code from src/core/errors.py). Actions the hook sends:
// join_queue, leave_queue, accept_challenge, create_invite, accept_invite, spectate_game, leave_spectate,
// chat_message, offer_draw, accept_draw, decline_draw, accept_rematch, decline_rematch, berserk (a move, resignation, cancellation
// and a rematch offer are sent by Chessboard itself). HTTP is a safety net in case an event is lost and the source of
// the lists, polled every 1.5 s: GET /profile/games/my-active (the player's game in progress), GET /profile/matchmaking/queue
// (lobby challenges), GET /profile/games/live (games in progress), GET /profile/games/{id}/summary (the result of a missed
// game); joining the lobby and accepting a challenge are duplicated by POST /profile/matchmaking/join, /leave and /accept/{id}.
// The source of truth for position, clocks and result is the server: the hook puts on the board what it sent.

import {inviteOddsFields} from '../odds';
import type {OddsChoice} from '../odds';
import {useCallback, useEffect, useRef, useState} from 'react';
import type {NavigateFunction} from 'react-router-dom';
import {Chess} from 'chess.js';
import {gameSocket} from '../../../services/gameSocket';
import {resolveMoveSound} from '../../../services/soundEngine';
import type {SoundEventType} from '../../../services/soundEngine';
import {API_BASE_URL} from '../../../config/api';
import {GAME_ACTION_ERROR_CODES} from '../types';
import {appendChat, chatItemFrom, sendChatPreset, sendChatText} from '../gameChat';
import type {LiveGameItem, ChatMessageItem, QueuePlayer, PendingPromotion, ChatPresetId} from '../types';
import type {BotOpponentId} from '../../../config/champions';
import {describeGameOver, hasStatusKey, messageParam, status} from '../status';
import type {GameStatus} from '../status';
import {serverErrorMessage} from '../../../services/apiErrors';
import {getToken} from '../../../services/authToken';

// Draw statuses are shared objects: Chessboard uses the status key to decide whether to show the "Accept / Decline" buttons.
const DRAW_OFFER_INCOMING = status('status.drawOffered');
const DRAW_OFFER_OUTGOING = status('status.drawOfferSent');
const DRAW_DECLINED = status('status.drawDeclined');

/** How many polls in a row the server must answer "no active game" for the game to be considered finished. */
const MISSING_GAME_POLLS = 2;

/**
 * What the hook receives from Chessboard: state values, their setters and ref copies. Refs are needed by WebSocket handlers:
 * they subscribe once and must see the current game, not the one at subscription time.
 */
export interface UseGameSocketOptions {
    /** id of one's own game against a human; null means no such game (free board, bot, spectating). */
    gameId: number | null;
    gameIdRef: React.MutableRefObject<number | null>;
    myColorRef: React.MutableRefObject<'white' | 'black'>;
    /** id of someone else's game the player is watching; null means not a spectator. */
    spectatingGameId: number | null;
    /** Game state version on the server (grows with every move): stale snapshots are dropped by it. */
    stateVersionRef: React.MutableRefObject<number>;
    gameOverResult: string | null;
    gameOverResultRef: React.MutableRefObject<string | null>;
    activeBot: BotOpponentId | null;
    currentUsernameRef: React.MutableRefObject<string>;
    /** Code from the /challenge/{code} address: the invitation is accepted right after the page opens. */
    inviteCode: string | undefined;
    navigate: NavigateFunction;
    effectiveWhiteBaseMinutes: number;
    effectiveIncSeconds: number;
    inviteColorPref: 'white' | 'black' | 'random';
    /** Handicap in a game by link (21.1): the server builds the position or time after the colours are assigned. */
    inviteOdds?: OddsChoice;
    /** Variant of a game by link: ordinary chess or Fischer (21.3; 960 runs on a separate page). */
    inviteVariant?: 'standard' | 'chess960';
    /** Type of new games chosen by the player: rated or friendly. */
    ratedChoice: boolean;
    /** Type of the game currently on the board (comes from the server). */
    setIsRatedGame: (rated: boolean) => void;
    /** "Hourglass clock" of the game on the board (21.1, the hourglass field from the server): the waiting side's clock grows while the mover thinks. */
    setHourglass: (on: boolean) => void;

    setGame: (g: Chess) => void;
    setHistory: (h: any[]) => void;
    setViewIndex: (i: number) => void;
    setGameId: (id: number | null) => void;
    setMyColor: (c: 'white' | 'black') => void;
    setSpectatingGameId: (id: number | null) => void;
    setActiveBot: (id: BotOpponentId | null) => void;
    setStateVersion: (v: number) => void;
    setWhitePlayer: (p: { username: string; rating: string }) => void;
    setBlackPlayer: (p: { username: string; rating: string }) => void;
    setRatingInfo: (r: any) => void;
    setGameOverResult: (r: string | null) => void;
    setDrawOfferStatus: React.Dispatch<React.SetStateAction<GameStatus | null>>;
    setRematchStatus: (s: 'none' | 'offered_by_me' | 'offered_by_opponent' | 'declined') => void;
    isSearching: boolean;
    setIsSearching: (v: boolean) => void;
    setIsManualFlip: (v: boolean) => void;
    setSelectedSquare: (s: string | null) => void;
    setPendingPromotion: (p: PendingPromotion | null) => void;
    /** Clears the premove; used at the start/end of a game and on a server refusal. */
    clearPremove: () => void;
    setWhiteTimeMs: (ms: number) => void;
    setBlackTimeMs: (ms: number) => void;
    setLobbyTab: (t: 'lobby' | 'live') => void;
    setIsTimeDropdownOpen: (v: boolean) => void;
    setShowInvitePanel: (v: boolean) => void;
    moveStartTime: React.MutableRefObject<number>;
    resetLowTimeWarning: () => void;
    exitBotGame: () => void;
    playAudio: (type: SoundEventType) => void;
    playOutcomeSound: (result: string, playerColor?: 'white' | 'black') => void;
    updateSessionStats: (result: string) => void;
}

/** "Berserk" in an arena game (33.3): whether it is available in the game and who played it. */
export interface BerserkState {
    allowed: boolean;
    white: boolean;
    black: boolean;
}

const NO_BERSERK: BerserkState = {allowed: false, white: false, black: false};

// Berserk fields from a server event (match_found, spectate_started, berserk): berserk_allowed, white_berserk,
// black_berserk; an absent field means "no".
function berserkFrom(data: any): BerserkState {
    return {allowed: data.berserk_allowed === true, white: data.white_berserk === true, black: data.black_berserk === true};
}

export interface UseGameSocketResult {
    berserk: BerserkState;
    /** Play "berserk": half of one's own time without increment for an extra point for a win. */
    handleBerserk: () => void;
    /** Chat of the game on the board (the last 50 messages); cleared on a new game and when spectating starts. */
    chatMessages: ChatMessageItem[];
    chatInput: string;
    setChatInput: (v: string) => void;
    /** Games in progress (GET /profile/games/live) and lobby challenges (GET /profile/matchmaking/queue), polled. */
    liveGames: LiveGameItem[];
    queuePlayers: QueuePlayer[];
    /** Code of the invitation link from the invite_created event; reset when the game type changes and when a game starts. */
    createdInviteCode: string | null;
    inviteCopied: boolean;
    /** Puts a whole game on the board from a server snapshot: a match_found event or an HTTP response (my-active, join, accept). */
    applyMatchFoundSnapshot: (data: any) => void;
    /** Updates the game in progress from a move snapshot: a move_made event or a fresher my-active response. */
    applyMoveMadeSnapshot: (data: any) => void;
    /** Publishes a lobby challenge with the chosen control and game type (WebSocket and, for reliability, HTTP). */
    startMatchmaking: () => Promise<void>;
    cancelMatchmaking: () => Promise<void>;
    /** Accepts someone else's lobby challenge; the game starts on match_found or on the HTTP response. */
    acceptChallenge: (targetUserId: number) => Promise<void>;
    /** Asks the server to create an invitation link (create_invite); the code arrives in an invite_created event. */
    handleCreatePrivateInvite: () => void;
    handleCopyInviteLink: () => void;
    /** Asks the server to make the player a spectator of a game; the board switches on the spectate_started event. */
    handleSpectateGame: (targetGameId: number) => void;
    handleSendChatMessage: () => void;
    handleSendChatPreset: (preset: ChatPresetId) => void;
    handleAcceptRematch: () => void;
    handleDeclineRematch: () => void;
    handleOfferDraw: () => void;
    acceptDraw: () => void;
    declineDraw: () => void;
}

/**
 * Game against a human, lobby, spectating and chat for the main board (details and data sources are at the start of the file).
 * Works only for a signed-in player: without a token the connection is not opened, only the lobby lists are polled.
 */
export function useGameSocket({
    gameId, gameIdRef, myColorRef, spectatingGameId, stateVersionRef,
    gameOverResult, gameOverResultRef, activeBot, currentUsernameRef, inviteCode, navigate,
    effectiveWhiteBaseMinutes, effectiveIncSeconds, inviteColorPref, inviteOdds, inviteVariant = 'standard',
    ratedChoice, setIsRatedGame, setHourglass,
    setGame, setHistory, setViewIndex, setGameId, setMyColor, setSpectatingGameId,
    setStateVersion, setWhitePlayer, setBlackPlayer, setRatingInfo, setGameOverResult,
    setDrawOfferStatus, setRematchStatus, isSearching, setIsSearching, setIsManualFlip, setSelectedSquare,
    setPendingPromotion, clearPremove, setWhiteTimeMs, setBlackTimeMs,
    setLobbyTab, setIsTimeDropdownOpen, setShowInvitePanel, moveStartTime, resetLowTimeWarning,
    exitBotGame, playAudio, playOutcomeSound, updateSessionStats,
}: UseGameSocketOptions): UseGameSocketResult {
    const [chatMessages, setChatMessages] = useState<ChatMessageItem[]>([]);
    const [chatInput, setChatInput] = useState('');
    const [liveGames, setLiveGames] = useState<LiveGameItem[]>([]);
    const [queuePlayers, setQueuePlayers] = useState<QueuePlayer[]>([]);
    const [createdInviteCode, setCreatedInviteCode] = useState<string | null>(null);
    const [inviteCopied, setInviteCopied] = useState(false);
    const [berserk, setBerserk] = useState<BerserkState>(NO_BERSERK);

    // WebSocket handlers outlive a single render, so current values are read from refs.
    const spectatingRef = useRef<number | null>(spectatingGameId);
    useEffect(() => {
        spectatingRef.current = spectatingGameId;
    }, [spectatingGameId]);
    const isSearchingRef = useRef(isSearching);
    useEffect(() => {
        isSearchingRef.current = isSearching;
    }, [isSearching]);
    // Parameters of the current search, to put the challenge back in the lobby after a WebSocket reconnect.
    const searchParamsRef = useRef<{ base_time_ms: number; increment_ms: number; rated: boolean } | null>(null);
    // How many polls in a row the server found no active game although one is running on screen (see MISSING_GAME_POLLS).
    const missingActivePollsRef = useRef(0);

    // An invitation link is created for a specific game type: after the type changes it is no longer the right one.
    useEffect(() => {
        setCreatedInviteCode(null);
    }, [ratedChoice]);

    /**
     * The event refers to the game currently on the board (one's own or one being watched).
     * Without this check a late game_over of the previous game would end the new one (a rematch),
     * and moves of a game the player was watching before starting their own would land on their board.
     */
    const isCurrentGameEvent = useCallback((data: any): boolean => {
        if (data?.game_id === undefined || data?.game_id === null) return true;
        const gid = Number(data.game_id);
        return gid === gameIdRef.current || gid === spectatingRef.current;
    }, [gameIdRef]);

    /** The event refers to one's own game, not a watched one: draw and rematch offers are not needed by a spectator. */
    const isOwnGameEvent = useCallback((data: any): boolean => {
        if (gameIdRef.current === null) return false;
        if (data?.game_id === undefined || data?.game_id === null) return true;
        return Number(data.game_id) === gameIdRef.current;
    }, [gameIdRef]);

    /** Ends the game on screen: result, sound and statistics, once per game. */
    const concludeGame = useCallback((data: any) => {
        clearPremove();
        setPendingPromotion(null);
        // The result may have already arrived (move_made with game_over, then game_over): we do not announce or
        // count it a second time. The ref is updated immediately: the component's effect fires later.
        const alreadyOver = Boolean(gameOverResultRef.current);
        gameOverResultRef.current = data.result;
        setGameOverResult(data.result);
        setRatingInfo(data);
        if (alreadyOver) return;
        if (gameIdRef.current !== null) {
            playOutcomeSound(data.result);
            updateSessionStats(data.result);
        } else {
            // Spectator: someone else's game does not go into their statistics and does not sound like a win/loss.
            playAudio('draw');
        }
    }, [clearPremove, setPendingPromotion, gameOverResultRef, setGameOverResult, setRatingInfo, gameIdRef,
        playOutcomeSound, updateSessionStats, playAudio]);

    // A whole-game snapshot: a new game (start, rematch, accepted challenge) or restoring one's own game in progress
    // after a page reload. The position is taken from the server PGN (with move history), and from the FEN if parsing fails.
    const applyMatchFoundSnapshot = useCallback((data: any) => {
        if (!data || !data.game_id) return;
        // Fischer Random game (21.3): chess.js cannot replay 960 castling, so the game runs on its own page.
        if (data.variant === 'chess960') {
            navigate('/play/960/live', {state: {match: data}});
            return;
        }
        const incomingGid = Number(data.game_id);
        const assignedColor: 'white' | 'black' = data.color === 'black' ? 'black' : 'white';
        const ver = Number(data.state_version || 0);
        const isNewMatch = gameIdRef.current !== incomingGid;

        if (spectatingRef.current) {
            gameSocket.send('leave_spectate', {game_id: spectatingRef.current});
            spectatingRef.current = null;
        }
        searchParamsRef.current = null;
        isSearchingRef.current = false;
        missingActivePollsRef.current = 0;

        setIsSearching(false);
        setSpectatingGameId(null);
        setCreatedInviteCode(null);
        setShowInvitePanel(false);
        exitBotGame();

        if (isNewMatch) {
            resetLowTimeWarning();
            setChatMessages([]);
            setIsManualFlip(false);
            setRatingInfo(null);
            gameOverResultRef.current = null;
            setGameOverResult(null);
            setRematchStatus('none');
            setSelectedSquare(null);
            setPendingPromotion(null);
            clearPremove();
        }

        gameIdRef.current = incomingGid;
        setGameId(incomingGid);
        setIsRatedGame(data.is_rated !== false);
        // A snapshot of the same game without berserk fields (an HTTP poll) does not erase what is already known.
        if (isNewMatch || data.berserk_allowed !== undefined) setBerserk(berserkFrom(data));
        if (isNewMatch || data.hourglass !== undefined) setHourglass(data.hourglass === true);
        myColorRef.current = assignedColor;
        setMyColor(assignedColor);
        setStateVersion(ver);
        stateVersionRef.current = ver;

        const initialWhiteTime = data.white_time_ms !== undefined ? Number(data.white_time_ms) : Number(data.base_time_ms || 180000);
        const initialBlackTime = data.black_time_ms !== undefined ? Number(data.black_time_ms) : Number(data.base_time_ms || 180000);
        setWhiteTimeMs(initialWhiteTime);
        setBlackTimeMs(initialBlackTime);

        if (data.white_username) {
            setWhitePlayer({username: data.white_username, rating: String(data.white_rating || '1200')});
        }
        if (data.black_username) {
            setBlackPlayer({username: data.black_username, rating: String(data.black_rating || '1200')});
        }

        const restoredGame = new Chess();
        if (data.pgn) {
            try {
                restoredGame.loadPgn(data.pgn);
            } catch {
                if (data.fen) restoredGame.load(data.fen);
            }
        } else if (data.fen) {
            restoredGame.load(data.fen);
        }

        setGame(restoredGame);
        setHistory(restoredGame.history({verbose: true}));
        setViewIndex(-1);
        moveStartTime.current = Date.now();

        // A draw offer made before a page reload or a connection drop is still in force.
        const hasIncomingDrawOffer = data.draw_offer_from !== undefined && data.draw_offer_from !== null
            && Number(data.draw_offer_from) === Number(data.opponent_id);

        if (isNewMatch) {
            const startMessage = status(assignedColor === 'white' ? 'status.gameStartedWhite' : 'status.gameStartedBlack');
            setDrawOfferStatus(hasIncomingDrawOffer ? DRAW_OFFER_INCOMING : startMessage);
            playAudio('start');
            // We remove only our own message: within 3 s another status could have taken its place.
            setTimeout(() => setDrawOfferStatus(prev => (prev === startMessage ? null : prev)), 3000);
        } else if (hasIncomingDrawOffer) {
            setDrawOfferStatus(DRAW_OFFER_INCOMING);
        } else {
            setDrawOfferStatus(prev => (hasStatusKey(prev, 'status.drawOffered') ? null : prev));
        }
    }, [playAudio, navigate]);

    // Snapshot after a move (one's own or the opponent's): the state version, both sides' clocks and the position all come from the server.
    // One's own move is already shown on the board in advance; this snapshot confirms it and sets exact clocks.
    const applyMoveMadeSnapshot = useCallback((data: any) => {
        if (data.state_version !== undefined) {
            const ver = Number(data.state_version);
            setStateVersion(ver);
            stateVersionRef.current = ver;
        }
        if (data.white_time_ms !== undefined) setWhiteTimeMs(Number(data.white_time_ms));
        if (data.black_time_ms !== undefined) setBlackTimeMs(Number(data.black_time_ms));
        moveStartTime.current = Date.now();

        const nextGame = new Chess();
        let loaded = false;

        if (data.pgn) {
            try {
                nextGame.loadPgn(data.pgn);
                loaded = true;
            } catch {
                loaded = false;
            }
        }

        if (!loaded && data.fen) {
            try {
                nextGame.load(data.fen);
                loaded = true;
            } catch {
                loaded = false;
            }
        }

        if (loaded) {
            const newHistory = nextGame.history({verbose: true});
            const lastSan = data.san || (newHistory.length > 0 ? newHistory[newHistory.length - 1].san : '');
            setGame(nextGame);
            setHistory(newHistory);
            setViewIndex(-1);
            // On the final move only the outcome (victory/defeat/draw) is played: the sound of the
            // move itself (for example, "check" on mate) would be a redundant duplicate before the fanfare.
            if (!data.game_over) {
                playAudio(resolveMoveSound(lastSan));
            }

            // A move answers a draw offer with a refusal (the server withdraws it): the move of the one to whom
            // the offer was made. The offerer's own move does not cancel the offer.
            const moverColor = nextGame.turn() === 'w' ? 'black' : 'white';
            const moverIsMe = moverColor === myColorRef.current;
            setDrawOfferStatus(prev => {
                if (hasStatusKey(prev, 'status.drawOffered') && moverIsMe) return null;
                if (hasStatusKey(prev, 'status.drawOfferSent') && !moverIsMe) return null;
                return prev;
            });
        }

        if (data.game_over) {
            concludeGame(data);
        }
    }, [playAudio, concludeGame]);

    // Connecting to the WebSocket and subscribing to server events; when the board unmounts the subscriptions are removed, but
    // the connection itself stays (there is one per tab and notifications need it too).
    useEffect(() => {
        const token = getToken();
        if (!token) return;

        gameSocket.connect(token);

        const handleMatchFound = (data: any) => {
            applyMatchFoundSnapshot(data);
        };

        const handleMoveMade = (data: any) => {
            if (!isCurrentGameEvent(data)) return;
            applyMoveMadeSnapshot(data);
        };

        const handleGameOver = (data: any) => {
            if (!isCurrentGameEvent(data)) return;
            concludeGame(data);
            if (data.white_time_ms !== undefined) setWhiteTimeMs(data.white_time_ms);
            if (data.black_time_ms !== undefined) setBlackTimeMs(data.black_time_ms);
            const summary = describeGameOver(data.result, data.reason);
            if (summary) setDrawOfferStatus(summary);
        };

        // Berserk (one's own or the opponent's): new clocks and a mark on the player.
        const handleBerserkEvent = (data: any) => {
            if (!isCurrentGameEvent(data) || gameOverResultRef.current) return;
            if (data.white_time_ms !== undefined) setWhiteTimeMs(Number(data.white_time_ms));
            if (data.black_time_ms !== undefined) setBlackTimeMs(Number(data.black_time_ms));
            setBerserk(berserkFrom(data));
        };

        const handleDrawOffered = (data: any) => {
            if (!isOwnGameEvent(data) || gameOverResultRef.current) return;
            setDrawOfferStatus(DRAW_OFFER_INCOMING);
            playAudio('offer');
        };

        const handleDrawDeclined = (data: any) => {
            if (!isOwnGameEvent(data) || gameOverResultRef.current) return;
            setDrawOfferStatus(DRAW_DECLINED);
            playAudio('decline');
            setTimeout(() => setDrawOfferStatus(prev => (hasStatusKey(prev, 'status.drawDeclined') ? null : prev)), 3000);
        };

        const handleRematchOffered = (data: any) => {
            if (!isOwnGameEvent(data)) return;
            setRematchStatus('offered_by_opponent');
            playAudio('offer');
        };

        const handleRematchDeclined = (data: any) => {
            if (!isOwnGameEvent(data)) return;
            setRematchStatus('declined');
            playAudio('decline');
        };

        // The server sends connected on every (re)connection. On a drop it removes the player's challenge
        // from the lobby, while the screen would keep showing "searching": we put the challenge back.
        const handleConnected = () => {
            const params = searchParamsRef.current;
            if (params && isSearchingRef.current && !gameIdRef.current) {
                gameSocket.send('join_queue', params);
            }
        };

        // The server created an invitation: the link is copied to the clipboard at once (if the browser allows).
        const handleInviteCreated = (data: any) => {
            if (data.code) {
                setCreatedInviteCode(data.code);
                const url = `${window.location.origin}/challenge/${data.code}`;
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(url).catch(() => {
                    });
                }
                setInviteCopied(true);
                playAudio('offer');
                setTimeout(() => setInviteCopied(false), 3000);
            }
        };

        // The server made the player a spectator and sent a snapshot of someone else's game: players, clocks, position.
        const handleSpectateStarted = (data: any) => {
            if (gameIdRef.current && !gameOverResultRef.current) {
                // While the response was pending, one's own game started: we do not become a spectator.
                gameSocket.send('leave_spectate', {game_id: data.game_id});
                return;
            }
            exitBotGame();
            gameIdRef.current = null;
            setGameId(null);
            spectatingRef.current = Number(data.game_id);
            setSpectatingGameId(Number(data.game_id));
            setIsRatedGame(data.is_rated !== false);
            setBerserk(berserkFrom(data));
            setHourglass(data.hourglass === true);
            // A spectator always watches from White's side and does not inherit the state of a previous game.
            myColorRef.current = 'white';
            setMyColor('white');
            setIsManualFlip(false);
            setRatingInfo(null);
            setRematchStatus('none');
            setSelectedSquare(null);
            setPendingPromotion(null);
            clearPremove();
            setWhitePlayer({username: data.white_username || '', rating: String(data.white_rating || 1200)});
            setBlackPlayer({username: data.black_username || '', rating: String(data.black_rating || 1200)});
            setWhiteTimeMs(data.white_time_ms ?? data.base_time_ms ?? 180000);
            setBlackTimeMs(data.black_time_ms ?? data.base_time_ms ?? 180000);

            const restored = new Chess();
            if (data.pgn) {
                try {
                    restored.loadPgn(data.pgn);
                } catch {
                    if (data.fen) restored.load(data.fen);
                }
            } else if (data.fen) {
                restored.load(data.fen);
            }
            setGame(restored);
            setHistory(restored.history({verbose: true}));
            setViewIndex(-1);
            gameOverResultRef.current = null;
            setGameOverResult(null);
            setChatMessages([]);
            setDrawOfferStatus(status('status.spectating', {
                white: data.white_username || messageParam('common.white'),
                black: data.black_username || messageParam('common.black'),
            }));
            playAudio('start');
        };

        // Chat message (one's own also comes back as an echo from the server). The last 50 are kept in memory; a quick phrase is stored as a code.
        const handleChatMessage = (data: any) => {
            if (!isCurrentGameEvent(data)) return;
            const item = chatItemFrom(data);
            if (item) {
                setChatMessages(prev => appendChat(prev, item));
                if (item.sender !== currentUsernameRef.current) {
                    playAudio('chat');
                }
            }
        };

        const handleServerError = (data: any) => {
            console.warn('Server rejected the action:', data);
            // The action was duplicated (WS + HTTP, a retry after reconnect), and the game has already
            // started from the first of the requests: "you are already playing" is not an error here.
            if (data.code === 'self_in_game' && gameIdRef.current && !gameOverResultRef.current) return;
            if (data.code) {
                // The text comes from the catalog by code; the server's English text only for an unknown code.
                const message = serverErrorMessage(data.code, data.params, data.message);
                if (message) setDrawOfferStatus(message);
                // A matchmaking refusal (already in a game, out of rating range, stale challenge...)
                // takes one out of search mode; chat, offer and rate restrictions do not.
                if (!GAME_ACTION_ERROR_CODES.has(data.code)) {
                    searchParamsRef.current = null;
                    setIsSearching(false);
                }
                // A move rejected by the rate limit comes with the current position:
                // it must be put back on the board (below). Other refusals do not touch the position.
                if (!data.fen && !data.pgn) return;
            }
            clearPremove();
            playAudio('illegal');
            if (data.pgn || data.fen) {
                const syncedGame = new Chess();
                if (data.pgn) {
                    try {
                        syncedGame.loadPgn(data.pgn);
                    } catch {
                        if (data.fen) syncedGame.load(data.fen);
                    }
                } else if (data.fen) {
                    syncedGame.load(data.fen);
                }
                setGame(syncedGame);
                setHistory(syncedGame.history({verbose: true}));
            }
            if (data.state_version !== undefined) {
                const ver = Number(data.state_version);
                setStateVersion(ver);
                stateVersionRef.current = ver;
            }
        };

        gameSocket.on('connected', handleConnected);
        gameSocket.on('match_found', handleMatchFound);
        gameSocket.on('move_made', handleMoveMade);
        gameSocket.on('game_over', handleGameOver);
        gameSocket.on('berserk', handleBerserkEvent);
        gameSocket.on('draw_offered', handleDrawOffered);
        gameSocket.on('draw_declined', handleDrawDeclined);
        gameSocket.on('rematch_offered', handleRematchOffered);
        gameSocket.on('rematch_declined', handleRematchDeclined);
        gameSocket.on('invite_created', handleInviteCreated);
        gameSocket.on('spectate_started', handleSpectateStarted);
        gameSocket.on('chat_message', handleChatMessage);
        gameSocket.on('error', handleServerError);

        return () => {
            gameSocket.off('connected', handleConnected);
            gameSocket.off('match_found', handleMatchFound);
            gameSocket.off('move_made', handleMoveMade);
            gameSocket.off('game_over', handleGameOver);
            gameSocket.off('berserk', handleBerserkEvent);
            gameSocket.off('draw_offered', handleDrawOffered);
            gameSocket.off('draw_declined', handleDrawDeclined);
            gameSocket.off('rematch_offered', handleRematchOffered);
            gameSocket.off('rematch_declined', handleRematchDeclined);
            gameSocket.off('invite_created', handleInviteCreated);
            gameSocket.off('spectate_started', handleSpectateStarted);
            gameSocket.off('chat_message', handleChatMessage);
            gameSocket.off('error', handleServerError);
        };
    }, [applyMatchFoundSnapshot, applyMoveMadeSnapshot, concludeGame, isCurrentGameEvent, isOwnGameEvent,
        exitBotGame, playAudio]);

    // The page was opened by an invitation link /challenge/{code}: we accept the invitation (accept_invite) and remove
    // the code from the address. The action is sent 450 ms after the page opens; leaving the page earlier cancels it.
    // A guest signs in first (the sign-in window is opened by App.tsx); after sign-in the board is recreated and the effect fires.
    useEffect(() => {
        if (!inviteCode || !getToken()) return;
        const timer = setTimeout(() => {
            gameSocket.send('accept_invite', {code: inviteCode});
            navigate('/', {replace: true});
        }, 450);
        return () => clearTimeout(timer);
    }, [inviteCode, navigate]);

    /**
     * The game ended on the server, but game_over did not reach the client: we take the result over HTTP.
     * While the result is not recorded in the DB (status IN_PROGRESS), we do nothing and ask again.
     */
    const concludeMissedGame = useCallback(async (missedGameId: number) => {
        const res = await fetch(`${API_BASE_URL}/api/v1/profile/games/${missedGameId}/summary`);
        if (!res.ok) return;
        const summary = await res.json();
        if (summary.status !== 'COMPLETED' && summary.status !== 'ABORTED') return;
        if (gameIdRef.current !== missedGameId || gameOverResultRef.current) return;

        missingActivePollsRef.current = 0;
        const result: string = summary.status === 'ABORTED' ? '*' : (summary.result || '*');
        concludeGame({...summary, result});
        setDrawOfferStatus(describeGameOver(result, summary.termination));
    }, [gameIdRef, gameOverResultRef, concludeGame, setDrawOfferStatus]);

    // Polling the server every 1.5 s is a WebSocket safety net and the source of the lobby lists. One's own game in progress (my-active):
    // a new one is put on the board, a fresher version is caught up with, a vanished one is finished by summary. While a
    // bot game or spectating is in progress, my-active is not polled. The lobby and Live lists are read when one has no own game against a
    // human or it is over.
    useEffect(() => {
        const syncLobbyAndActiveGame = async () => {
            const token = getToken();
            try {
                if (token && !activeBot && !spectatingGameId) {
                    const activeRes = await fetch(`${API_BASE_URL}/api/v1/profile/games/my-active`, {
                        headers: {'Authorization': `Bearer ${token}`}
                    });
                    if (activeRes.ok) {
                        const activeData = await activeRes.json();
                        if (activeData && activeData.active && activeData.game_id) {
                            missingActivePollsRef.current = 0;
                            if (gameIdRef.current !== Number(activeData.game_id)) {
                                applyMatchFoundSnapshot(activeData);
                                return;
                            } else if (Number(activeData.state_version || 0) > stateVersionRef.current) {
                                applyMoveMadeSnapshot(activeData);
                            }
                        } else if (gameIdRef.current && !gameOverResultRef.current) {
                            // The game is in progress on screen, but the server no longer considers it active: game_over
                            // was lost (a WebSocket drop at the moment of finishing). Two answers in a row,
                            // so as not to confuse it with a request sent before the game started.
                            missingActivePollsRef.current += 1;
                            if (missingActivePollsRef.current >= MISSING_GAME_POLLS) {
                                await concludeMissedGame(gameIdRef.current);
                            }
                        } else {
                            missingActivePollsRef.current = 0;
                        }
                    }
                }

                // The lobby is needed after a game ends too: its result is still on the board, but the player is already
                // choosing the next opponent.
                if (!gameIdRef.current || gameOverResultRef.current) {
                    const [qRes, liveRes] = await Promise.all([
                        fetch(`${API_BASE_URL}/api/v1/profile/matchmaking/queue`),
                        fetch(`${API_BASE_URL}/api/v1/profile/games/live`)
                    ]);
                    if (qRes.ok) {
                        setQueuePlayers(await qRes.json());
                    }
                    if (liveRes.ok) {
                        setLiveGames(await liveRes.json());
                    }
                } else {
                    setQueuePlayers([]);
                }
            } catch (e) {
                console.error('Failed to sync lobby/active game data', e);
            }
        };

        syncLobbyAndActiveGame();
        const interval = setInterval(syncLobbyAndActiveGame, 1500);
        return () => clearInterval(interval);
    }, [activeBot, spectatingGameId, applyMatchFoundSnapshot, applyMoveMadeSnapshot, concludeMissedGame]);

    const startMatchmaking = useCallback(async () => {
        if (spectatingRef.current) {
            // Searching for an opponent ends spectating of someone else's game: the board is needed for one's own.
            gameSocket.send('leave_spectate', {game_id: spectatingRef.current});
            spectatingRef.current = null;
            setSpectatingGameId(null);
            setGame(new Chess());
            setHistory([]);
            setViewIndex(-1);
        }
        gameIdRef.current = null;
        setGameId(null);
        exitBotGame();
        resetLowTimeWarning();
        setPendingPromotion(null);
        clearPremove();
        gameOverResultRef.current = null;
        setGameOverResult(null);
        setRatingInfo(null);
        isSearchingRef.current = true;
        setIsSearching(true);
        setLobbyTab('lobby');
        setIsTimeDropdownOpen(false);
        setDrawOfferStatus(status(ratedChoice ? 'status.challengePublishedRated' : 'status.challengePublishedCasual', {
            timeControl: effectiveIncSeconds > 0
                ? messageParam('timeControl.minutesIncrement', {base: effectiveWhiteBaseMinutes, inc: effectiveIncSeconds})
                : messageParam('timeControl.minutes', {base: effectiveWhiteBaseMinutes}),
        }));

        const baseMs = Math.round(effectiveWhiteBaseMinutes * 60 * 1000);
        const incMs = Math.round(effectiveIncSeconds * 1000);

        searchParamsRef.current = {base_time_ms: baseMs, increment_ms: incMs, rated: ratedChoice};
        gameSocket.send('join_queue', {
            base_time_ms: baseMs,
            increment_ms: incMs,
            rated: ratedChoice
        });

        const token = getToken();
        if (token) {
            try {
                const res = await fetch(`${API_BASE_URL}/api/v1/profile/matchmaking/join`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({base_time_ms: baseMs, increment_ms: incMs, rated: ratedChoice})
                });
                if (res.ok) {
                    const data = await res.json();
                    if (data && data.active && data.game_id) {
                        applyMatchFoundSnapshot(data);
                    }
                }
            } catch {
                // Ignore the error if the WebSocket fired
            }
        }
    }, [
        gameIdRef, setGameId, exitBotGame, resetLowTimeWarning, setPendingPromotion, clearPremove,
        setGameOverResult, setRatingInfo, setIsSearching, setLobbyTab,
        setIsTimeDropdownOpen, setDrawOfferStatus, effectiveWhiteBaseMinutes,
        effectiveIncSeconds, applyMatchFoundSnapshot, gameOverResultRef, setSpectatingGameId, setGame,
        setHistory, setViewIndex, ratedChoice,
    ]);

    const cancelMatchmaking = useCallback(async () => {
        searchParamsRef.current = null;
        isSearchingRef.current = false;
        setIsSearching(false);
        setDrawOfferStatus(null);
        gameSocket.send('leave_queue', {});
        const token = getToken();
        if (token) {
            fetch(`${API_BASE_URL}/api/v1/profile/matchmaking/leave`, {
                method: 'POST',
                headers: {'Authorization': `Bearer ${token}`}
            }).catch(() => {
            });
        }
    }, [setIsSearching, setDrawOfferStatus]);

    const acceptChallenge = useCallback(async (targetUserId: number) => {
        exitBotGame();
        setPendingPromotion(null);
        clearPremove();

        gameSocket.send('accept_challenge', {target_user_id: targetUserId});

        const token = getToken();
        if (!token) return;

        try {
            const res = await fetch(`${API_BASE_URL}/api/v1/profile/matchmaking/accept/${targetUserId}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Accept': 'application/json'
                }
            });
            if (res.ok) {
                const data = await res.json();
                if (data && data.game_id) {
                    applyMatchFoundSnapshot(data);
                }
            }
        } catch (err) {
            console.error('Failed to accept the challenge over HTTP:', err);
        }
    }, [exitBotGame, setPendingPromotion, clearPremove, applyMatchFoundSnapshot]);

    const handleCreatePrivateInvite = useCallback(() => {
        gameSocket.send('create_invite', {
            base_time_ms: Math.round(effectiveWhiteBaseMinutes * 60 * 1000),
            increment_ms: Math.round(effectiveIncSeconds * 1000),
            color_pref: inviteColorPref,
            rated: ratedChoice,
            ...(inviteVariant === 'chess960' ? {variant: 'chess960'} : (inviteOdds ? inviteOddsFields(inviteOdds) : {})),
        });
    }, [effectiveWhiteBaseMinutes, effectiveIncSeconds, inviteColorPref, ratedChoice, inviteOdds, inviteVariant]);

    const handleCopyInviteLink = useCallback(() => {
        if (!createdInviteCode) return;
        const url = `${window.location.origin}/challenge/${createdInviteCode}`;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url).catch(() => {
            });
        }
        setInviteCopied(true);
        setTimeout(() => setInviteCopied(false), 2500);
    }, [createdInviteCode]);

    const handleSpectateGame = useCallback((targetGameId: number) => {
        gameSocket.send('spectate_game', {game_id: targetGameId});
    }, []);

    const handleSendChatMessage = useCallback(() => {
        const activeGid = gameId || spectatingGameId;
        if (activeGid && sendChatText(activeGid, chatInput)) setChatInput('');
    }, [gameId, spectatingGameId, chatInput]);

    /** A quick phrase is sent as a code: each participant sees it in their own language. */
    const handleSendChatPreset = useCallback((preset: ChatPresetId) => {
        const activeGid = gameId || spectatingGameId;
        if (activeGid) sendChatPreset(activeGid, preset);
    }, [gameId, spectatingGameId]);

    const handleAcceptRematch = useCallback(() => {
        if (!gameId) return;
        gameSocket.send('accept_rematch', {game_id: gameId});
    }, [gameId]);

    const handleDeclineRematch = useCallback(() => {
        if (!gameId) return;
        gameSocket.send('decline_rematch', {game_id: gameId});
        setRematchStatus('none');
        playAudio('decline');
    }, [gameId, setRematchStatus, playAudio]);

    const handleOfferDraw = useCallback(() => {
        if (!gameId || gameOverResult) return;
        gameSocket.send('offer_draw', {game_id: gameId});
        setDrawOfferStatus(DRAW_OFFER_OUTGOING);
        playAudio('premove');
    }, [gameId, gameOverResult, setDrawOfferStatus, playAudio]);

    const handleBerserk = useCallback(() => {
        if (!gameId || gameOverResult) return;
        gameSocket.send('berserk', {game_id: gameId});
    }, [gameId, gameOverResult]);

    const acceptDraw = useCallback(() => {
        if (!gameId) return;
        gameSocket.send('accept_draw', {game_id: gameId});
        setDrawOfferStatus(null);
    }, [gameId, setDrawOfferStatus]);

    const declineDraw = useCallback(() => {
        if (!gameId) return;
        gameSocket.send('decline_draw', {game_id: gameId});
        setDrawOfferStatus(null);
        playAudio('decline');
    }, [gameId, setDrawOfferStatus, playAudio]);

    return {
        chatMessages, chatInput, setChatInput, liveGames, queuePlayers, createdInviteCode, inviteCopied,
        applyMatchFoundSnapshot, applyMoveMadeSnapshot, startMatchmaking, cancelMatchmaking, acceptChallenge,
        handleCreatePrivateInvite, handleCopyInviteLink, handleSpectateGame, handleSendChatMessage, handleSendChatPreset,
        handleAcceptRematch, handleDeclineRematch, handleOfferDraw, acceptDraw, declineDraw,
        berserk, handleBerserk,
    };
}
