// --- FILE: frontend/src/components/Chessboard.tsx ---
// Main board (routes "/" and "/challenge/{code}", entry by an invitation link): a game against a human, a game against a
// bot and free analysis on one board. Here are the position state and markup; the logic is moved into hooks in
// chessboard/hooks/: useGameSocket (human game events and the lobby), useBotGame (a bot game), useClock
// (clocks), usePremoves (premoves), useCoachMode (playing with the coach).
// In a game against a human the source of truth is the server: the client shows its own move at once, but takes the position, clocks and result from
// the response (move_made, game_over); a rejected move goes back to its place. The panels around the board are components of the folder
// chessboard/.
//
// The board mode is determined by three values: gameId (one's own game against a human), activeBot (a bot game),
// spectatingGameId (watching someone else's game); if all three are empty, it is the free board. A guest gets a stub instead of the board
// asking to sign in. The player's data is GET /profile/me, the bot catalog is GET /bots/catalog. Appearance and
// board size are remembered in localStorage (regence_board_theme, regence_piece_set, regence_board_size), board
// settings are config/boardPrefs.ts. Other pages start an action here through the route state: tournamentGame
// (a tournament game), guestGame (a master of the past), firstGame (the first game after registration), analyzeFen (a position
// for review with the coach), spectate (watching a game), challenge (a player challenge from the profile).

import type {OddsChoice} from './chessboard/odds';
import {useState, useEffect, useRef, useCallback} from 'react';
import {socialApi} from '../services/social';
import {useLocation, useNavigate, useParams} from 'react-router-dom';
import {Chess} from 'chess.js';
import {ListOrdered, Zap, MessageSquare, GraduationCap, ScanEye, Swords} from 'lucide-react';
import {Button, SegmentedControl} from './ui';
import {NewGameDialog} from './chessboard/NewGameDialog';
import {gameSocket} from '../services/gameSocket';
import {soundEngine, resolveMoveSound} from '../services/soundEngine';
import type {SoundEventType} from '../services/soundEngine';
import {
    BOARD_THEMES,
    lastMoveColor,
    PIECE_SETS,
    getSavedBoardThemeKey,
    getSavedPieceSetKey,
    getPieceSvgUrl,
    getHarmoniousPieceStyle
} from '../config/boardAppearance';
import {BoardTextureLayer} from './chessboard/BoardTextureLayer';
import type {BoardTheme} from '../config/boardAppearance';
import {HISTORICAL_BOTS} from '../config/champions';
import type {BotOpponentId, HistoricalBotId, HistoricalBotProfile} from '../config/champions';
import {ALL_TIME_CONTROLS, DEFAULT_TIME_CONTROL, TIME_CONTROLS, timeControlCategory} from '../config/timeControls';
import {clearBotGameSnapshot, loadBotGameSnapshot, saveBotGameSnapshot} from '../services/botGameSnapshot';
import type {TournamentGameStart} from '../services/tournaments';
import {ContinueTournaments, TournamentGameBar} from './tournaments/TournamentGameBar';
import {pickFirstOpponent} from '../services/onboarding';
import type {FirstGameStart} from '../services/onboarding';
import type {MasterGameStart} from '../services/masters';
import type {TimeControlOption, TimeControlGroup} from '../config/timeControls';
import {
    FILES, RANKS, MIN_BOARD_SIZE, MAX_BOARD_SIZE,
    getMaxViewportBoardSize, getDefaultBoardSize, fittedBoardSize, calculateMaterialBalance, cloneChessInstance, prevIndexHelper,
    customStartFen, pairHalfMoves, validateFen, STANDARD_START_FEN
} from './chessboard/boardUtils';
import type {PromotionPiece} from './chessboard/boardUtils';
import type {PendingPromotion} from './chessboard/types';
import {useClock} from './chessboard/hooks/useClock';
import {usePremoves} from './chessboard/hooks/usePremoves';
import {useBotGame} from './chessboard/hooks/useBotGame';
import {useCoachMode} from './chessboard/hooks/useCoachMode';
import {CoachPanel} from './chessboard/CoachPanel';
import {CoachArrowsOverlay} from './chessboard/CoachArrowsOverlay';
import {AnnotationsOverlay, useBoardAnnotations} from './chessboard/annotations';
import {coachArrows, coachHighlights} from '../services/coach';
import {AuxBoard} from './chessboard/AuxBoard';
import {XrayOverlay} from './xray/XrayOverlay';
import {XrayPanel} from './xray/XrayPanel';
import {useXraySettings} from './xray/useXraySettings';
import {GameSummaryPanel} from './chessboard/GameSummaryPanel';
import {outcomeFor, recommendOpponent} from '../services/gameSummary';
import type {PoolOpponent} from '../services/gameSummary';
import type {BotCatalog, BotRival} from '../services/botCatalog';
import {useGameSocket} from './chessboard/hooks/useGameSocket';
import {PromotionDialog} from './chessboard/PromotionDialog';
import {MoveList} from './chessboard/MoveList';
import {scrollMoveIntoList} from './chessboard/scrollMove';
import {BoardNavigationControls} from './chessboard/BoardNavigationControls';
import {GameChatPanel} from './chessboard/GameChatPanel';
import {PlayerInfoBar} from './chessboard/PlayerInfoBar';
import {GameControlsPanel} from './chessboard/GameControlsPanel';
import {GameHallHeader} from './chessboard/GameHallHeader';
import {TimeControlPicker} from './chessboard/TimeControlPicker';
import {MatchmakingPanel, PvpGameStatus} from './chessboard/MatchmakingPanel';
import {HistoricalBotsPanel} from './chessboard/HistoricalBotsPanel';
import {PersonalityWorkshop} from './chessboard/PersonalityWorkshop';
import {LadderPanel} from './chessboard/LadderPanel';
import type {LadderStart} from '../services/ladder';
import {ladderOutcomeMessage} from './chessboard/hooks/useBotGame';
import {hasStatusKey, renderStatus, status} from './chessboard/status';
import type {GameStatus} from './chessboard/status';
import {useI18n} from '../i18n';
import {fetchBotCatalog, fetchRivalry} from '../services/botCatalog';
import {isArchetypeId} from '../config/archetypes';
import type {ArchetypeId} from '../config/archetypes';
import type {CustomOpponent} from '../config/archetypes';
import {LobbyPanel} from './chessboard/LobbyPanel';
import {AppearancePickerDropdown} from './chessboard/AppearancePickerDropdown';
import {getToken} from '../services/authToken';
import {accountApi} from '../services/account';
import {profileApi} from '../services/profile';
import {orderCaptured, quickMoveFrom, useBoardPrefs} from '../config/boardPrefs';
import {LastMoveArrow} from './chessboard/LastMoveArrow';
import {BlindfoldPanel} from './chessboard/BlindfoldPanel';
import {parseMoveInput, startBlindfold, useBlindfold, visibleSquares} from '../config/blindfold';
import {squareLabel} from '../services/a11y/speech';
import {useBoardKeyboard} from './chessboard/hooks/useBoardKeyboard';
import type {Translate} from '../services/a11y/speech';
import {BoardSpeech} from './chessboard/BoardSpeech';
import {squareCenter} from './chessboard/CoachArrowsOverlay';

// Re-export for modules that historically import these names from Chessboard (GameViewer, tests).
export {MIN_BOARD_SIZE, MAX_BOARD_SIZE, getMaxViewportBoardSize, getDefaultBoardSize, TIME_CONTROLS};
export type {PromotionPiece, TimeControlOption, TimeControlGroup};

export {BOARD_THEMES, HISTORICAL_BOTS};
export type {BoardTheme, HistoricalBotId, HistoricalBotProfile};

/** Right column tab of the game hall. */
type SideTab = 'moves' | 'chat' | 'coach' | 'xray';

/** Board side saved by the player; unavailable storage (private mode) counts as "not saved". */
function savedBoardSize(): string | null {
    try {
        return localStorage.getItem('regence_board_size');
    } catch {
        return null;
    }
}

/**
 * Main board with all the panels around it. Owns the game state (position, history, own colour, result) and
 * hands it to the hooks: useGameSocket and useBotGame change the same state, so it lives here.
 */
export default function Chessboard() {
    const {t} = useI18n();
    const navigate = useNavigate();
    // Invitation code from the /challenge/{code} address; accepted by useGameSocket.
    const {inviteCode} = useParams<{ inviteCode?: string }>();

    const [lobbyTab, setLobbyTab] = useState<'lobby' | 'live'>('lobby');
    const [showInvitePanel, setShowInvitePanel] = useState(false);
    const [showAppearanceDropdown, setShowAppearanceDropdown] = useState(false);
    const [isSoundMuted, setIsSoundMuted] = useState<boolean>(() => soundEngine.isMuted());
    const appearanceDropdownRef = useRef<HTMLDivElement>(null);

    const [spectatingGameId, setSpectatingGameId] = useState<number | null>(null);
    const [inviteColorPref, setInviteColorPref] = useState<'white' | 'black' | 'random'>('random');
    const [inviteOdds, setInviteOdds] = useState<OddsChoice>({kind: 'none', giver: 'me'});
    const [inviteVariant, setInviteVariant] = useState<'standard' | 'chess960'>('standard');
    // Type of new games (a lobby challenge and an invitation by link) and the type of the game on the board.
    const [ratedChoice, setRatedChoice] = useState<boolean>(true);
    const [isRatedGame, setIsRatedGame] = useState<boolean>(true);
    // A bot game can be started from the position standing on the free board.
    const [startFromPosition, setStartFromPosition] = useState<boolean>(false);

    // Live position of the game (chess.js) and its moves in detailed form (history({verbose: true})) change together.
    const [game, setGame] = useState(new Chess());
    const [history, setHistory] = useState<any[]>([]);
    // Board square with keyboard focus (task 26.3) and the squares themselves, to move focus with the arrows.
    // Which position is on screen: -1 is live, -2 is the start of the game before the first move, otherwise the index of the ply in history
    // after which the position is shown. One can move only on the live position.
    const [viewIndex, setViewIndex] = useState<number>(-1);
    const [selectedSquare, setSelectedSquare] = useState<string | null>(null);
    // The board is flipped by the "Flip" button relative to the usual view (one's own colour at the bottom).
    const [isManualFlip, setIsManualFlip] = useState<boolean>(false);

    const [pendingPromotion, setPendingPromotion] = useState<PendingPromotion | null>(null);

    const [boardThemeKey, setBoardThemeKey] = useState<string>(() => getSavedBoardThemeKey());
    const [pieceSetKey, setPieceSetKey] = useState<string>(() => getSavedPieceSetKey());

    // id of one's own game against a human (comes in match_found); stays after it ends until the player leaves
    // for the lobby. Ref copies (gameIdRef, myColorRef and others below) are read by WebSocket handlers and timers: they need the
    // current value, not the one at subscription time.
    const [gameId, setGameId] = useState<number | null>(null);
    const gameIdRef = useRef<number | null>(null);
    const [myColor, setMyColor] = useState<'white' | 'black'>('white');
    const myColorRef = useRef<'white' | 'black'>('white');
    const [isSearching, setIsSearching] = useState(false);
    // Player: id, name and blitz rating from GET /profile/me (the effect below).
    const [currentUserId, setCurrentUserId] = useState<number | null>(null);
    const [currentUsername, setCurrentUsername] = useState<string>('');
    const currentUsernameRef = useRef<string>('');
    const [currentUserRating, setCurrentUserRating] = useState<number>(1200);
    // Game state version on the server: it arrives with every snapshot and goes back with the move (make_move) so that the
    // server does not accept a move made from a stale position.
    const [stateVersion, setStateVersion] = useState(0);
    const stateVersionRef = useRef<number>(0);

    // activeBot lives here (not inside useBotGame) because useClock uses it
    // for isTicking/isParticipant and must be called before useBotGame.
    const [activeBot, setActiveBot] = useState<BotOpponentId | null>(null);
    // Bot game pause (friendly only, no ladder or tournament): the clocks stop, the bot does not move, the position is hidden.
    const [botPaused, setBotPaused] = useState(false);
    // Bot tab: historical masters, the opponent workshop or the club ladder.
    const [botsView, setBotsView] = useState<'historical' | 'workshop' | 'ladder'>('historical');
    // Measured strength of historical bots (calibration by matches), if present.
    const [measuredBotRatings, setMeasuredBotRatings] = useState<Record<string, number>>({});
    // Strength from games against humans (task 32.1).
    const [liveBotStrength, setLiveBotStrength] = useState<Record<string, { rating: number; games: number }>>({});
    // Which bots remember the player (task 32.2); refreshed after every game.
    const [botRivals, setBotRivals] = useState<Record<string, BotRival>>({});
    // The whole catalog, for recommending the next opponent in the game result (task 11.5).
    const [botCatalog, setBotCatalog] = useState<BotCatalog | null>(null);
    // The bot catalog (GET /bots/catalog) is read once when the board opens; on failure the declared ratings remain.
    useEffect(() => {
        fetchBotCatalog()
            .then((catalog) => {
                setBotCatalog(catalog);
                setMeasuredBotRatings(Object.fromEntries(
                    catalog.historical.filter((h) => h.measured).map((h) => [h.id, h.rating]),
                ));
                setLiveBotStrength(Object.fromEntries(catalog.historical.flatMap((h) => (h.live && h.live.games > 0
                    ? [[h.id, {rating: h.live.rating, games: h.live.games}]] : []))));
            })
            .catch(() => undefined);
    }, []);

    const [selectedTimeControl, setSelectedTimeControl] = useState<TimeControlOption>(DEFAULT_TIME_CONTROL);
    const [manualBaseMinutes, setManualBaseMinutes] = useState<number>(5);
    const [manualIncSeconds, setManualIncSeconds] = useState<number>(3);
    const [isTimeDropdownOpen, setIsTimeDropdownOpen] = useState(false);
    const timeDropdownRef = useRef<HTMLDivElement>(null);
    const boardContainerRef = useRef<HTMLDivElement>(null);
    const notationScrollRef = useRef<HTMLDivElement>(null);

    // An empty name means the player is unknown: on screen "White"/"Black" in the current language instead of it.
    const [whitePlayer, setWhitePlayer] = useState({username: '', rating: '1200'});
    const [blackPlayer, setBlackPlayer] = useState({username: '', rating: '1200'});
    const shownWhitePlayer = {...whitePlayer, username: whitePlayer.username || t('common.white')};
    const shownBlackPlayer = {...blackPlayer, username: blackPlayer.username || t('common.black')};
    const [ratingInfo, setRatingInfo] = useState<{
        white_delta?: number;
        black_delta?: number;
        white_new_rating?: number;
        black_new_rating?: number;
    } | null>(null);

    // The moment from which the thinking time of one's own move is counted: it goes to the server with the move (time_taken_ms)
    // and is needed for the lag quota and anti-cheat. The game clock is kept by the server, not by this value.
    const moveStartTime = useRef<number>(Date.now());

    // Board settings (task 18.4, config/boardPrefs.ts, localStorage regence_board_prefs): last-move display,
    // move input method, "quick move", opponent move animation, order of captured pieces.
    const boardPrefs = useBoardPrefs();
    // Blindfold play (task 19.5): the level of the current game, peeks.
    const blind = useBlindfold();
    // Blindfold mode is already on for the game in progress (it is turned on once, at its start).
    const blindStartedRef = useRef(false);
    // The game for which the "blindfold" mark has already been sent to the archive, so as not to send it twice.
    const blindMarkedRef = useRef<number | null>(null);
    // Opponent move animation: the piece already stands on the new square and "slides" onto it from the old one (go turns
    // the transition on). animatedHistoryLength is the history length for which the animation has already been shown.
    const [moveAnim, setMoveAnim] = useState<{ from: string; to: string; go: boolean } | null>(null);
    const animatedHistoryLength = useRef(0);
    // The piece currently dragged by the pointer and the pointer coordinates (its "ghost" is drawn over the page).
    const [dragState, setDragState] = useState<{
        from: string;
        piece: { type: string; color: string };
        x: number;
        y: number;
    } | null>(null);

    // Board side in pixels: the one saved by the player (localStorage regence_board_size), but no larger than
    // fits in the window; when the window changes the board both shrinks and grows back (fittedBoardSize, the effect below).
    const [boardSize, setBoardSize] = useState<number>(() => fittedBoardSize(savedBoardSize()));
    const [isResizing, setIsResizing] = useState(false);
    const resizeStartRef = useRef<{ startX: number; startY: number; startSize: number } | null>(null);

    useEffect(() => {
        const handleWindowResize = () => setBoardSize(fittedBoardSize(savedBoardSize()));
        window.addEventListener('resize', handleWindowResize);
        return () => window.removeEventListener('resize', handleWindowResize);
    }, []);

    // Session score: wins, losses and draws since the page was opened; not saved anywhere.
    const [sessionStats, setSessionStats] = useState({wins: 0, losses: 0, draws: 0});
    // Game result on the board: '1-0', '0-1', '1/2-1/2', '*' (cancelled); null means the game is in progress or there is none.
    const [gameOverResult, setGameOverResult] = useState<string | null>(null);
    const gameOverResultRef = useRef<string | null>(null);
    useEffect(() => {
        gameOverResultRef.current = gameOverResult;
    }, [gameOverResult]);
    // The status line above the move list. The name is historical: besides a draw offer, it shows the start of the
    // game, its result, bot replies and server refusals (see chessboard/status.ts).
    const [drawOfferStatus, setDrawOfferStatus] = useState<GameStatus | null>(null);
    const [rematchStatus, setRematchStatus] = useState<'none' | 'offered_by_me' | 'offered_by_opponent' | 'declined'>('none');

    const activeTheme = BOARD_THEMES[boardThemeKey] || BOARD_THEMES.walnut;
    const activePieceSet = PIECE_SETS[pieceSetKey] || PIECE_SETS.merida;

    // The chosen time control: minutes and increment. It is the same for both sides; a different starting time is given only by a
    // time handicap (computed by useBotGame or the server).
    const effectiveWhiteBaseMinutes = selectedTimeControl.isManual ? manualBaseMinutes : selectedTimeControl.base;
    const effectiveBlackBaseMinutes = effectiveWhiteBaseMinutes;
    const effectiveIncSeconds = selectedTimeControl.isManual ? manualIncSeconds : selectedTimeControl.inc;

    const isBoardFlipped = (myColor === 'black') !== isManualFlip;

    const playAudio = useCallback((type: SoundEventType) => {
        soundEngine.play(type);
    }, []);

    // Playing with the coach (task 11.3): checking the player's moves and advice, in a bot game and on the free board.
    const coach = useCoachMode(currentUserRating);
    // Board x-ray (task 12.1): the free board, a bot game with the coach on (except the ladder and
    // tournament), a spectator. Not for the player of a human game in progress (rule 2).
    const xray = useXraySettings();
    // The fresh value of "the game is a training one" for saving the game: useBotGame reads it at the moment of saving.
    const coachAssistedRef = useRef(false);
    coachAssistedRef.current = coach.assisted;
    const isCoachAssisted = useCallback(() => coachAssistedRef.current, []);

    // Handicap (task 21.1): the choice before a bot game and the handicap of the game in progress (for a rematch and the "hourglass clock").
    const [oddsChoice, setOddsChoice] = useState<OddsChoice>({kind: 'none', giver: 'opponent'});
    const [activeOdds, setActiveOdds] = useState<OddsChoice | null>(null);
    const [hourglass, setHourglass] = useState(false);

    // The clock on screen runs in one's own game, in a bot game and for a spectator, until the game is over. The coach does not
    // stop it (owner's decision 18.11): its advice appears next to the board, and the game goes on.
    const {
        whiteTimeMs, setWhiteTimeMs, blackTimeMs, setBlackTimeMs, resetLowTimeWarning, applyIncrement,
    } = useClock({
        isTicking: Boolean(gameId || activeBot || spectatingGameId) && !gameOverResult && !botPaused,
        isParticipant: Boolean(gameId || activeBot) && !gameOverResult,
        currentTurn: game.turn() === 'w' ? 'white' : 'black',
        myColor,
        onLowTime: () => playAudio('low_time'),
        // "Hourglass clock": in a bot game the flag is set by useBotGame, in a human game and for a spectator by useGameSocket.
        hourglass,
    });

    // The result sound for a participant: a win or loss by one's own colour; a draw and a cancelled game have their own sounds.
    const playOutcomeSound = useCallback((result: string, playerColor: 'white' | 'black' = myColorRef.current) => {
        if (!result || result === '*') {
            soundEngine.play('decline');
            return;
        }
        if (result === '1/2-1/2' || result.includes('draw')) {
            soundEngine.play('draw');
            return;
        }
        const whiteWon = result === '1-0' || result === 'white_won_on_time';
        const isWin = (whiteWon && playerColor === 'white') || (!whiteWon && playerColor === 'black');
        soundEngine.play(isWin ? 'victory' : 'defeat');
    }, []);

    const handleToggleSound = () => {
        const nextMuted = soundEngine.toggleMute();
        setIsSoundMuted(nextMuted);
        if (!nextMuted) {
            soundEngine.play('move');
        }
    };

    const updateSessionStats = useCallback((result: string) => {
        if (!result || result === '*') return;
        setSessionStats(prev => {
            if (result === '1/2-1/2' || result.includes('draw')) {
                return {...prev, draws: prev.draws + 1};
            }
            const whiteWon = result === '1-0' || result === 'white_won_on_time';
            const userIsWhite = myColorRef.current === 'white';
            if ((whiteWon && userIsWhite) || (!whiteWon && !userIsWhite)) {
                return {...prev, wins: prev.wins + 1};
            } else {
                return {...prev, losses: prev.losses + 1};
            }
        });
    }, []);

    // usePremoves owns setPremove, but is called later (it needs executeMove, and that needs
    // values from useBotGame). Safe: the closure body reads setPremove lazily, after
    // usePremoves has already run in this same render.
    const clearPremove = useCallback(() => setPremove(null), []);

    const {
        selectedBotId, setSelectedBotId, botComment, isBotThinking, savedBotGameId,
        startHistoricalBotGame, startCustomBotGame, botProfileFor, botNameParam, saveBotGameToDatabase, exitBotGame,
        isLadderGame, ladderOutcome, customArchetypeId, isTournamentGame, savedTournamentId, offerDrawToBot,
        resumeBotGame, botGameInfo,
    } = useBotGame({
        game, myColor, gameOverResult, whiteTimeMs, blackTimeMs, isSearching, setIsSearching,
        activeBot, setActiveBot,
        effectiveWhiteBaseMinutes, effectiveBlackBaseMinutes, effectiveIncSeconds, setHourglass,
        currentUsername, currentUserRating,
        setGame, setHistory, setViewIndex, setSelectedSquare, setMyColor, setIsManualFlip, setPendingPromotion,
        clearPremove, setGameOverResult, setRatingInfo, setDrawOfferStatus, setRematchStatus,
        setWhiteTimeMs, setBlackTimeMs, resetLowTimeWarning, applyIncrement,
        moveStartTime, myColorRef, gameIdRef, setGameId, setWhitePlayer, setBlackPlayer,
        playAudio, playOutcomeSound, updateSessionStats,
        isAssisted: isCoachAssisted, onNewGame: coach.reset, holdBot: botPaused,
    });

    const selectedBotProfile = HISTORICAL_BOTS[selectedBotId];
    // The bots' memory of the player (GET /bots/rivalry): when the board opens and after every saved bot game.
    useEffect(() => {
        const token = getToken();
        if (!token) return;
        fetchRivalry(token).then((list) => setBotRivals(Object.fromEntries(list.map((r) => [r.bot_id, r]))))
            .catch(() => undefined);
    }, [savedBotGameId]);
    // A counted game, ladder or tournament (task A.2): no coach, x-ray or take-back: the server would count such
    // help as a loss anyway or would not count the game.
    const isRatedBotGame = isLadderGame || isTournamentGame;
    // A pause is given only by a friendly bot game: in a ladder or tournament game it would let one think without a clock.
    const canPauseBot = Boolean(activeBot) && !gameId && !isRatedBotGame && !gameOverResult;
    useEffect(() => {
        if (botPaused && !canPauseBot) setBotPaused(false);
    }, [botPaused, canPauseBot]);
    const activeBotProfile = activeBot ? botProfileFor(activeBot) : null;

    const {
        chatMessages, chatInput, setChatInput, liveGames, queuePlayers, createdInviteCode, inviteCopied,
        startMatchmaking, cancelMatchmaking, acceptChallenge,
        handleCreatePrivateInvite, handleCopyInviteLink, handleSpectateGame, handleSendChatMessage, handleSendChatPreset,
        handleAcceptRematch, handleDeclineRematch, handleOfferDraw, acceptDraw, declineDraw,
        berserk, handleBerserk,
    } = useGameSocket({
        gameId, gameIdRef, myColorRef, spectatingGameId, stateVersionRef,
        gameOverResult, gameOverResultRef, activeBot, currentUsernameRef, inviteCode, navigate,
        effectiveWhiteBaseMinutes, effectiveIncSeconds,
        inviteColorPref, inviteOdds, inviteVariant, ratedChoice, setIsRatedGame, setHourglass,
        setGame, setHistory, setViewIndex, setGameId, setMyColor, setSpectatingGameId, setActiveBot,
        setStateVersion, setWhitePlayer, setBlackPlayer, setRatingInfo, setGameOverResult,
        setDrawOfferStatus, setRematchStatus, isSearching, setIsSearching, setIsManualFlip, setSelectedSquare,
        setPendingPromotion, clearPremove, setWhiteTimeMs, setBlackTimeMs,
        setLobbyTab, setIsTimeDropdownOpen, setShowInvitePanel, moveStartTime, resetLowTimeWarning,
        exitBotGame, playAudio, playOutcomeSound, updateSessionStats,
    });

    // The appearance and board size choice is saved in this browser's localStorage (it does not go to the server).
    const handleThemeChange = (themeId: string) => {
        setBoardThemeKey(themeId);
        localStorage.setItem('regence_board_theme', themeId);
    };

    const handlePieceSetChange = (setId: string) => {
        setPieceSetKey(setId);
        localStorage.setItem('regence_piece_set', setId);
    };

    const handleBoardSizeChange = (size: number) => {
        setBoardSize(size);
        localStorage.setItem('regence_board_size', String(size));
    };

    // Stretching the board by the corner: while dragging, movement is caught on window, the size changes to the average of the shift
    // along the two axes and is saved at once; the cursor and the text selection ban are restored at the end.
    useEffect(() => {
        if (!isResizing) return;

        const prevCursor = document.body.style.cursor;
        const prevUserSelect = document.body.style.userSelect;
        document.body.style.cursor = 'nwse-resize';
        document.body.style.userSelect = 'none';

        const handleResizeMove = (e: PointerEvent) => {
            if (!resizeStartRef.current) return;
            const {startX, startY, startSize} = resizeStartRef.current;
            const deltaX = e.clientX - startX;
            const deltaY = e.clientY - startY;
            const delta = Math.round((deltaX + deltaY) / 2);

            const dynamicMax = getMaxViewportBoardSize();
            const nextSize = Math.min(Math.max(startSize + delta, MIN_BOARD_SIZE), dynamicMax);
            setBoardSize(nextSize);
            localStorage.setItem('regence_board_size', String(nextSize));
        };

        const handleResizeEnd = () => {
            setIsResizing(false);
            resizeStartRef.current = null;
        };

        window.addEventListener('pointermove', handleResizeMove);
        window.addEventListener('pointerup', handleResizeEnd);
        window.addEventListener('pointercancel', handleResizeEnd);

        return () => {
            document.body.style.cursor = prevCursor;
            document.body.style.userSelect = prevUserSelect;
            window.removeEventListener('pointermove', handleResizeMove);
            window.removeEventListener('pointerup', handleResizeEnd);
            window.removeEventListener('pointercancel', handleResizeEnd);
        };
    }, [isResizing]);

    const handleResizePointerDown = (e: React.PointerEvent) => {
        e.preventDefault();
        e.stopPropagation();
        resizeStartRef.current = {
            startX: e.clientX,
            startY: e.clientY,
            startSize: boardSize
        };
        setIsResizing(true);
    };

    const handleResizeDoubleClick = (e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        const defaultSize = getDefaultBoardSize();
        setBoardSize(defaultSize);
        localStorage.setItem('regence_board_size', String(defaultSize));
    };

    // The key handler hangs on window: it reads the history and the current move through a ref updated on every
    // render. From the effect closure (it is re-registered only after rendering) a key press right after
    // a move saw the previous position, the same race that was in GameViewer.
    const navigationRef = useRef({history, viewIndex});
    navigationRef.current = {history, viewIndex};

    // Keys: Esc clears the selection, premoves, the promotion window and the appearance dropdown; the left and right arrows
    // page through the game by move, up goes to the start, down to the live position. Arrows are not intercepted in input fields.
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                setPendingPromotion(null);
                setPremove(null);
                setSelectedSquare(null);
                setShowAppearanceDropdown(false);
                return;
            }
            const {history, viewIndex} = navigationRef.current;
            if (history.length === 0) return;
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
            // Focus on a board square: the arrows move focus between squares (onSquareKey), they do not page through moves.
            if (e.target instanceof HTMLElement && e.target.dataset.square) return;

            // setViewIndex takes only a ready value, not an updater function: React
            // StrictMode in development calls such a function twice, and the sound from a side effect
            // inside it would play twice in a row (out of sync, on different Audio ticks).
            // Audio).
            if (e.key === 'ArrowLeft') {
                e.preventDefault();
                const current = viewIndex === -1 ? history.length - 1 : prevIndexHelper(viewIndex, history.length);
                const nextIdx = current <= 0 ? -2 : current - 1;
                if (nextIdx === viewIndex) return;
                setViewIndex(nextIdx);
                if (nextIdx >= 0 && history[nextIdx]) {
                    playAudio(resolveMoveSound(history[nextIdx].san));
                } else {
                    playAudio('move');
                }
            } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                if (viewIndex === -1) return;
                const nextIdx = viewIndex === -2
                    ? (history.length > 1 ? 0 : -1)
                    : (viewIndex + 1 >= history.length - 1 ? -1 : viewIndex + 1);
                setViewIndex(nextIdx);
                const targetMove = nextIdx === -1 ? history[history.length - 1] : history[nextIdx];
                if (targetMove) {
                    playAudio(resolveMoveSound(targetMove.san));
                }
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (viewIndex === -2) return;
                setViewIndex(-2);
                playAudio('move');
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                if (viewIndex === -1) return;
                setViewIndex(-1);
                playAudio('move');
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [playAudio]);

    // The move list follows the shown move: the active move to the middle of the list window, and if there is none
    // (hidden or no moves yet) on the live position, scrolling to the end.
    useEffect(() => {
        if (notationScrollRef.current) {
            const activeEl = notationScrollRef.current.querySelector<HTMLElement>('.active-move-btn');
            if (activeEl) {
                // Only the move list window: the page and the board do not move (scrollMove.ts).
                scrollMoveIntoList(notationScrollRef.current, activeEl);
            } else if (viewIndex === -1) {
                notationScrollRef.current.scrollTop = notationScrollRef.current.scrollHeight;
            }
        }
    }, [history.length, viewIndex]);

    // A click outside the dropdowns (time control, appearance) closes them.
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (timeDropdownRef.current && !timeDropdownRef.current.contains(event.target as Node)) {
                setIsTimeDropdownOpen(false);
            }
            if (appearanceDropdownRef.current && !appearanceDropdownRef.current.contains(event.target as Node)) {
                setShowAppearanceDropdown(false);
            }
        };

        if (isTimeDropdownOpen || showAppearanceDropdown) {
            document.addEventListener('mousedown', handleClickOutside);
        }
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [isTimeDropdownOpen, showAppearanceDropdown]);

    // The player's own profile (GET /profile/me): id, to remove one's own challenge from the lobby, name for the card and chat, blitz
    // rating for the card in a bot game and the coach level.
    useEffect(() => {
        const token = getToken();
        if (!token) return;

        accountApi.me()
            .then(data => {
                if (data) {
                    setCurrentUserId(data.id);
                    if (data.username) {
                        setCurrentUsername(data.username);
                        currentUsernameRef.current = data.username;
                    }
                    // Blitz is for display in the player card before a bot game starts;
                    // for real PvP games the cards are updated with the authoritative rating
                    // from the server (by the category of exactly this game) in applyMatchFoundSnapshot.
                    if (data.blitz_rating) setCurrentUserRating(data.blitz_rating);
                }
            })
            .catch(() => {
            });
    }, []);

    // The player's move is the single point for clicks, dragging, premoves and notation input. It checks the turn
    // and legality (chess.js), for a promotion without a chosen piece opens the choice window, then at once shows
    // the move on the board. After that it depends on the mode. A game against a human: the move goes to the server (make_move: the move, command_id
    // so that a repeated send does not apply the move twice, the state version, the thinking time, the "tab
    // was hidden" and "premove" flags); the server confirms it with a move_made event or returns the previous position
    // with an error event. A bot game: the time increment, the coach check (except the ladder and tournament), on mate
    // or a draw, the result and saving. Free board: the coach only. Returns true if the move was made or
    // the promotion window was opened.
    const executeMove = useCallback((
        from: string,
        to: string,
        explicitPromotion?: PromotionPiece,
        isPremoveMove: boolean = false
    ): boolean => {
        if (gameOverResult || viewIndex !== -1 || spectatingGameId || botPaused) return false;

        const piece = game.get(from as any);
        const currentTurnColor = game.turn() === 'w' ? 'white' : 'black';

        if (!piece || piece.color !== (game.turn() === 'w' ? 'w' : 'b') || ((gameId || activeBot || spectatingGameId) && currentTurnColor !== myColor)) {
            setSelectedSquare(null);
            return false;
        }

        const targetRank = to[1];
        const isPawnPromotion =
            piece.type === 'p' &&
            ((piece.color === 'w' && targetRank === '8') || (piece.color === 'b' && targetRank === '1'));

        if (isPawnPromotion && !explicitPromotion && !isPremoveMove) {
            try {
                const probeGame = cloneChessInstance(game);
                const testMove = probeGame.move({from, to, promotion: 'q'});
                if (testMove) {
                    setPendingPromotion({
                        from,
                        to,
                        color: piece.color as 'w' | 'b',
                        isPremove: false
                    });
                    setSelectedSquare(null);
                    setDragState(null);
                    return true;
                }
            } catch {
                setSelectedSquare(null);
                setDragState(null);
                return false;
            }
        }

        const chosenPromotion: PromotionPiece = explicitPromotion || 'q';

        try {
            const nextGame = cloneChessInstance(game);
            const move = nextGame.move({
                from,
                to,
                ...(isPawnPromotion ? {promotion: chosenPromotion} : {})
            });

            if (move) {
                const timeTaken = isPremoveMove ? 0 : Math.max(0, Date.now() - moveStartTime.current);
                const uciMove = (move as any).uci || `${move.from}${move.to}${move.promotion || ''}`;
                const newHistory = nextGame.history({verbose: true});

                if (activeBot) {
                    applyIncrement(myColor, effectiveIncSeconds);
                }

                setPendingPromotion(null);
                setGame(nextGame);
                setHistory(newHistory);
                setViewIndex(-1);
                if (!gameId && !nextGame.isGameOver()) {
                    // In PvP the move sound is played by applyMoveMadeSnapshot when the server echoes
                    // move_made (both players receive it); otherwise one's own move sounds
                    // twice: at once here and again from the echo. On the final move (mate/stalemate)
                    // only the outcome is played: the sound of the move itself would be a redundant duplicate.
                    playAudio(resolveMoveSound(move.san));
                }
                moveStartTime.current = Date.now();
                if (!gameId && !isRatedBotGame && !nextGame.isGameOver()) {
                    coach.onPlayerMove(game, game.fen(), uciMove, nextGame.fen());
                }

                if (gameId) {
                    const commandId = typeof crypto !== 'undefined' && crypto.randomUUID
                        ? crypto.randomUUID()
                        : Math.random().toString(36).substring(2, 15) + Date.now().toString(36);

                    gameSocket.send('make_move', {
                        game_id: gameId,
                        move: uciMove,
                        command_id: commandId,
                        state_version: stateVersionRef.current,
                        time_taken_ms: timeTaken,
                        window_blurred: document.hidden,
                        is_premove: isPremoveMove
                    });
                } else if (activeBot && nextGame.isGameOver()) {
                    let result = '1/2-1/2';
                    if (nextGame.isCheckmate()) {
                        result = nextGame.turn() === 'w' ? '0-1' : '1-0';
                    }
                    setGameOverResult(result);
                    setDrawOfferStatus(status('status.botGameOver', {bot: botNameParam(activeBot), result}));
                    updateSessionStats(result);
                    playOutcomeSound(result, myColor);
                    saveBotGameToDatabase(activeBot, myColor, result, nextGame);
                }
                setSelectedSquare(null);
                setDragState(null);
                return true;
            }
        } catch {
            setSelectedSquare(null);
        }
        setDragState(null);
        return false;
    }, [game, gameId, activeBot, spectatingGameId, myColor, stateVersion, viewIndex, gameOverResult, playAudio, playOutcomeSound, updateSessionStats, saveBotGameToDatabase, applyIncrement, effectiveIncSeconds, isRatedBotGame, botPaused, coach.onPlayerMove]);

    const {premove, premoves, premoveView, setPremove, scheduleOrPromotePremove} = usePremoves({
        game,
        myColor,
        gameOverResult,
        viewIndex,
        isOpponentControlled: Boolean(gameId || activeBot),
        executeMove,
        playAudio,
        clearSelection: useCallback(() => {
            setSelectedSquare(null);
            setDragState(null);
            setPendingPromotion(null);
        }, []),
        openPromotionDialog: useCallback((p) => setPendingPromotion(p), []),
    });

    // Piece dragging: movement and release are caught on window. The square under the pointer is found by the data-square
    // attribute, and if another layer turned out to be under it, by the coordinates inside the board frame. On the opponent's turn
    // release sets a premove, on one's own it makes a move.
    useEffect(() => {
        const handlePointerMove = (e: PointerEvent) => {
            if (!dragState) return;
            setDragState(prev => prev ? {...prev, x: e.clientX, y: e.clientY} : null);
        };

        const handlePointerUp = (e: PointerEvent) => {
            if (!dragState) return;

            let targetSquare: string | null = null;

            const elements = document.elementsFromPoint(e.clientX, e.clientY);
            const squareEl = Array.from(elements || []).find(el => el.hasAttribute('data-square'));
            if (squareEl) {
                targetSquare = squareEl.getAttribute('data-square');
            }

            if (!targetSquare && boardContainerRef.current) {
                const rect = boardContainerRef.current.getBoundingClientRect();
                const padding = 10;
                const innerLeft = rect.left + padding;
                const innerTop = rect.top + padding;
                const innerWidth = rect.width - padding * 2;
                const innerHeight = rect.height - padding * 2;

                const x = e.clientX - innerLeft;
                const y = e.clientY - innerTop;

                if (x >= 0 && x <= innerWidth && y >= 0 && y <= innerHeight) {
                    const fileIdx = Math.floor((x / innerWidth) * 8);
                    const rankIdx = Math.floor((y / innerHeight) * 8);

                    const files = isBoardFlipped ? [...FILES].reverse() : FILES;
                    const ranks = isBoardFlipped
                        ? ['1', '2', '3', '4', '5', '6', '7', '8']
                        : ['8', '7', '6', '5', '4', '3', '2', '1'];

                    if (files[fileIdx] && ranks[rankIdx]) {
                        targetSquare = `${files[fileIdx]}${ranks[rankIdx]}`;
                    }
                }
            }

            if (targetSquare && targetSquare !== dragState.from) {
                const turnColor = game.turn() === 'w' ? 'white' : 'black';
                if ((gameId || activeBot || spectatingGameId) && turnColor !== myColor) {
                    scheduleOrPromotePremove(dragState.from, targetSquare);
                } else {
                    executeMove(dragState.from, targetSquare);
                }
            }

            setDragState(null);
        };

        if (dragState) {
            window.addEventListener('pointermove', handlePointerMove);
            window.addEventListener('pointerup', handlePointerUp);
            window.addEventListener('pointercancel', handlePointerUp);
        }

        return () => {
            window.removeEventListener('pointermove', handlePointerMove);
            window.removeEventListener('pointerup', handlePointerUp);
            window.removeEventListener('pointercancel', handlePointerUp);
        };
    }, [dragState, isBoardFlipped, game, gameId, activeBot, spectatingGameId, myColor, executeMove, scheduleOrPromotePremove]);

    const handleLeaveSpectate = () => {
        if (spectatingGameId) {
            gameSocket.send('leave_spectate', {game_id: spectatingGameId});
        }
        setSpectatingGameId(null);
        handleResetSandbox();
    };

    // Cancelling a game before the second ply is only in a game against a human: the server decides (abort_game -> game_over with the result '*').
    // In a bot game there is no cancel: leaving means resigning or pausing (owner's decision 22.11).
    const handleAbortGame = () => {
        if (!gameId || gameOverResult || history.length >= 2) return;
        setPendingPromotion(null);
        setPremove(null);
        gameSocket.send('abort_game', {game_id: gameId});
    };

    // Rematch: for a human, an offer through the server (offer_rematch), against a bot, a new game at once with the other colour.
    const handleOfferRematch = () => {
        if (gameId && gameOverResult) {
            gameSocket.send('offer_rematch', {game_id: gameId});
            setRematchStatus('offered_by_me');
            playAudio('premove');
        } else if (activeBot && gameOverResult) {
            const nextColor = myColor === 'white' ? 'black' : 'white';
            // A rematch uses the same starting position as the played game; with a handicap, the same handicap (the position
            // is recomputed: the colours change).
            if (activeOdds) startHistoricalBotGame(activeBot, nextColor, null, {odds: activeOdds});
            else startHistoricalBotGame(activeBot, nextColor, startFen);
        }
    };

    // Resignation (after confirmation): in a game against a human the server announces the result (resign -> game_over), in a game against a
    // bot the result is set at once and the game is saved with the reason "resignation".
    const handleResign = () => {
        if ((!gameId && !activeBot) || gameOverResult) return;
        if (window.confirm(t('controls.resignConfirm'))) {
            setPendingPromotion(null);
            setPremove(null);
            if (gameId) {
                gameSocket.send('resign', {game_id: gameId});
            } else if (activeBot) {
                const res = myColor === 'white' ? '0-1' : '1-0';
                setGameOverResult(res);
                setDrawOfferStatus(status('status.resigned', {bot: botNameParam(activeBot), result: res}));
                updateSessionStats(res);
                playOutcomeSound(res, myColor);
                saveBotGameToDatabase(activeBot, myColor, res, game, 'resignation');
            }
        }
    };

    // Return to an empty free board: sandbox reset, "To lobby" after a game against a human, leaving spectating.
    // A game against a human in progress cannot be left this way.
    const handleResetSandbox = () => {
        if (gameId && !gameOverResult) return;
        if (gameId && (rematchStatus === 'offered_by_me' || rematchStatus === 'offered_by_opponent')) {
            // On leaving a finished game, we withdraw a pending rematch offer: otherwise the opponent could
            // accept it later and drag the player into a game they no longer expect.
            gameSocket.send('decline_rematch', {game_id: gameId});
        }
        setRematchStatus('none');
        gameIdRef.current = null;
        setGameId(null);
        exitBotGame();
        resetLowTimeWarning();
        setGameOverResult(null);
        setRatingInfo(null);
        setDrawOfferStatus(null);
        setSelectedSquare(null);
        setPendingPromotion(null);
        setPremove(null);
        setViewIndex(-1);
        setGame(new Chess());
        setHistory([]);
    };

    // "Switch" on coach advice: the position before the player's move. The game did not wait for the advice, so the bot may have already replied;
    // then its move is taken back too; the increment for each undone move is removed from its own side.
    const handleCoachTakeBack = () => {
        const previous = coach.takeBack();
        if (!previous) return;
        if (activeBot) {
            applyIncrement(myColor, -effectiveIncSeconds);
            if (game.history().length - previous.history().length > 1) {
                applyIncrement(myColor === 'white' ? 'black' : 'white', -effectiveIncSeconds);
            }
        }
        setGame(previous);
        setHistory(previous.history({verbose: true}));
        setViewIndex(-1);
        setSelectedSquare(null);
        setPendingPromotion(null);
        setPremove(null);
        moveStartTime.current = Date.now();
        playAudio('move');
    };

    // Result of a bot game: the next opponent by result and strength (measured, if available).
    const recommendedOpponent = (() => {
        if (!activeBot || !gameOverResult || isRatedBotGame) return null;
        const pool: PoolOpponent[] = [
            ...(Object.keys(HISTORICAL_BOTS) as HistoricalBotId[]).map((id) => ({
                kind: 'historical' as const, id, rating: measuredBotRatings[id] ?? HISTORICAL_BOTS[id].rating,
            })),
            ...(botCatalog?.archetypes ?? []).map((a) => ({kind: 'archetype' as const, id: a.id, rating: a.rating})),
        ];
        const profile = botProfileFor(activeBot);
        const currentId = activeBot === 'custom' ? (customArchetypeId() ?? 'custom') : activeBot;
        const current = pool.find((o) => o.id === currentId) ?? {id: currentId, rating: profile.rating};
        return recommendOpponent(pool, current, outcomeFor(gameOverResult, myColor));
    })();
    const recommendationLabel = recommendedOpponent
        ? {
            name: recommendedOpponent.kind === 'historical'
                ? HISTORICAL_BOTS[recommendedOpponent.id as HistoricalBotId].shortName
                : t(`archetypes.${recommendedOpponent.id as ArchetypeId}.name`),
            rating: recommendedOpponent.rating,
        }
        : null;
    const handlePlayRecommended = () => {
        if (!recommendedOpponent) return;
        if (recommendedOpponent.kind === 'historical') {
            startHistoricalBotGame(recommendedOpponent.id as HistoricalBotId, 'random', null);
            return;
        }
        const archetype = botCatalog?.archetypes.find((a) => a.id === recommendedOpponent.id);
        if (archetype) {
            startCustomBotGame(
                {name: t(`archetypes.${archetype.id}.name`), config: archetype.config, archetypeId: archetype.id},
                'random', null,
            );
        }
    };

    const handleCoachAdvice = () => {
        void coach.requestHint(game.fen());
    };
    // Auxiliary board: a copy of the current position; on every opening, fresh from the game position.
    const [auxOpen, setAuxOpen] = useState(false);

    // Arrows and the explanation belong to the position they were requested for: any move clears them.
    const coachClearOverlay = coach.clearOverlay;
    const currentFen = game.fen();
    useEffect(() => {
        coachClearOverlay();
    }, [currentFen, coachClearOverlay]);

    // Take-back on the free board and in an ordinary bot game. In a bot game two plies are removed:
    // the bot's reply and one's own move, so that the turn returns to the player. The clocks are not returned.
    const handleUndoSandboxMove = () => {
        if (gameId || spectatingGameId || history.length === 0 || isBotThinking || !!gameOverResult) return;
        // A ladder or tournament game has no take-backs (the server would not count such a game anyway).
        if (isRatedBotGame) return;
        const nextGame = cloneChessInstance(game);
        nextGame.undo();
        if (activeBot && nextGame.history().length > 0) {
            const turnAfterFirstUndo = nextGame.turn() === 'w' ? 'white' : 'black';
            if (turnAfterFirstUndo !== myColor) {
                nextGame.undo();
            }
        }
        coach.keepMove();
        setGame(nextGame);
        setHistory(nextGame.history({verbose: true}));
        setGameOverResult(null);
        setDrawOfferStatus(null);
        setPendingPromotion(null);
        setPremove(null);
        setViewIndex(-1);
        setSelectedSquare(null);
        playAudio('move');
    };

    const handlePromotionSelect = (pieceType: PromotionPiece) => {
        if (!pendingPromotion) return;
        const {from, to, isPremove} = pendingPromotion;
        setPendingPromotion(null);
        if (isPremove) {
            scheduleOrPromotePremove(from, to, pieceType);
        } else {
            executeMove(from, to, pieceType, false);
        }
    };

    // Click on a square. On the opponent's turn clicks set a premove (pieces are taken from the "after premoves" position), on
    // one's own they select a piece and make a move; a click on an empty square with premoves set clears the whole queue.
    const handleSquareClick = (squareId: string) => {
        if (viewIndex !== -1 || gameOverResult || spectatingGameId || botPaused) return;

        if (pendingPromotion) {
            setPendingPromotion(null);
            return;
        }

        const turnChar = game.turn();
        const currentTurnColor = turnChar === 'w' ? 'white' : 'black';
        const myColorChar = myColor === 'white' ? 'w' : 'b';
        const isOpponentTurn = (gameId || activeBot || spectatingGameId) && currentTurnColor !== myColor;

        if (isOpponentTurn) {
            if (selectedSquare) {
                if (selectedSquare === squareId) {
                    setSelectedSquare(null);
                } else {
                    const pieceOnTarget = premoveView.get(squareId as never);
                    if (pieceOnTarget && pieceOnTarget.color === myColorChar) {
                        setSelectedSquare(squareId);
                    } else {
                        scheduleOrPromotePremove(selectedSquare, squareId);
                    }
                }
            } else {
                const piece = premoveView.get(squareId as never);
                if (piece && piece.color === myColorChar) {
                    setSelectedSquare(squareId);
                } else if (premove) {
                    setPremove(null);
                }
            }
            return;
        }

        if (selectedSquare) {
            if (selectedSquare === squareId) {
                setSelectedSquare(null);
            } else {
                const pieceOnTarget = game.get(squareId as any);
                if (pieceOnTarget && pieceOnTarget.color === turnChar && ((!gameId && !activeBot) || currentTurnColor === myColor)) {
                    setSelectedSquare(squareId);
                } else {
                    executeMove(selectedSquare, squareId);
                }
            }
        } else {
            const piece = game.get(squareId as any);
            if (piece && piece.color === turnChar && ((!gameId && !activeBot) || currentTurnColor === myColor)) {
                setSelectedSquare(squareId);
            } else if (boardPrefs.quickMove && ((!gameId && !activeBot) || currentTurnColor === myColor)) {
                // "Quick move" (task 18.4): only one piece can go to this square, so the move is made at once.
                const from = quickMoveFrom(game.moves({verbose: true}), squareId);
                if (from) executeMove(from, squareId);
            }
        }
    };

    // Starting position of the game on the board: null means the ordinary setup.
    const startFen = customStartFen(game);

    // Position on screen: the live one or, when viewing history, restored by replaying moves from the start of the game.
    const currentGame = viewIndex === -1 ? game : (() => {
        const tg = startFen ? new Chess(startFen) : new Chess();
        const limit = viewIndex === -2 ? -1 : viewIndex;
        for (let i = 0; i <= limit; i++) {
            if (history[i]) tg.move(history[i]);
        }
        return tg;
    })();
    // While premoves are set, the board shows pieces on their squares (a premove chain, task B.2).
    const boardState = (viewIndex === -1 && premoves.length > 0 ? premoveView : currentGame).board();
    // The player's right-button marks (task B.1); cleared when the position changes. While a premove is set or a
    // promotion is being chosen, the right button cancels them (onContextMenu below) and draws no arrow. A selected piece does not
    // interfere with marks: the right button clears the selection and draws an arrow; calculating a variation does not require releasing the piece first.
    const annotations = useBoardAnnotations(currentGame.fen(), !(premove || pendingPromotion));
    const xrayAvailable = Boolean(spectatingGameId) || (!gameId && (!activeBot || (coach.enabled && !isRatedBotGame)));
    // "Own" side: in a bot game, the player's colour; on the free board and for a spectator, the side to move.
    const xraySide: 'w' | 'b' = activeBot && !spectatingGameId ? (myColor === 'white' ? 'w' : 'b') : currentGame.turn();
    // Right column tabs (owner's plan 18.11): the move log with game controls, the game chat against a human (for
    // the player; for a spectator the chat is always visible, see tabPanel), the coach (except in a game against a human) and the x-ray when it is
    // allowed. A hidden tab stays in the markup and is just not shown: a message draft, the auxiliary board
    // and settings are not reset when switching.
    const sideTabs: SideTab[] = [
        'moves',
        ...((gameId && !spectatingGameId) ? ['chat' as const] : []),
        ...((!gameId && !spectatingGameId) ? ['coach' as const] : []),
        ...(xrayAvailable ? ['xray' as const] : []),
    ];
    const [sideTab, setSideTab] = useState<SideTab>('moves');
    // "New game" window (owner's scheme 18.11). While a game is in progress or the player watches someone else's, a new one cannot be started; as
    // soon as a game has started (from the window or from the lobby), the window closes by itself.
    const [newGameOpen, setNewGameOpen] = useState(false);
    const gameRunning = Boolean(spectatingGameId) || (Boolean(gameId || activeBot) && !gameOverResult);
    useEffect(() => {
        if (gameRunning) setNewGameOpen(false);
    }, [gameRunning]);
    const shownTab: SideTab = sideTabs.includes(sideTab) ? sideTab : 'moves';
    // A coach blunder warning cannot be missed: the "Coach" tab opens by itself, and when the player has answered
    // ("keep the move" or "take back"), the column returns to the moves, unless the player opened it themselves.
    const coachPending = Boolean(coach.pending);
    const coachOpenedItself = useRef(false);
    useEffect(() => {
        if (coachPending) {
            setSideTab((current) => {
                if (current !== 'coach') coachOpenedItself.current = true;
                return 'coach';
            });
        } else if (coachOpenedItself.current) {
            coachOpenedItself.current = false;
            setSideTab('moves');
        }
    }, [coachPending]);
    // Unread chat messages are a number on the tab while it is closed.
    const [chatSeen, setChatSeen] = useState(0);
    useEffect(() => {
        if (shownTab === 'chat') setChatSeen(chatMessages.length);
    }, [shownTab, chatMessages.length]);
    const chatUnread = Math.max(0, chatMessages.length - chatSeen);
    const SIDE_TAB_ICONS = {moves: ListOrdered, chat: MessageSquare, coach: GraduationCap, xray: ScanEye};
    // For a spectator the chat panel has a "Leave spectating" button: it is always visible, on any tab, and a separate
    // "Chat" tab does not exist for a spectator.
    const tabPanel = (id: SideTab) => ({
        role: 'tabpanel' as const,
        'data-testid': `side-panel-${id}`,
        className: shownTab === id || (id === 'chat' && spectatingGameId) ? 'contents' : 'hidden',
    });

    const material = calculateMaterialBalance(boardState);

    const activeMoveIndex = viewIndex === -1 ? history.length - 1 : viewIndex;
    // One's own game is in progress (against a human or a bot): not finished and the player is a participant, not a spectator.
    const liveGame = Boolean(gameId || activeBot) && !gameOverResult && !spectatingGameId;
    // Blindfold: which pieces are visible (null means all are visible: an ordinary game, a peek or a finished game).
    const blindVisible = blind.level > 0 && liveGame && blind.peekUntil <= Date.now()
        ? visibleSquares(blind.level, boardState, history.slice(0, activeMoveIndex + 1), myColor === 'white' ? 'w' : 'b')
        : null;

    // A new game is blindfold if a level is chosen and the game is unrated (the ladder, tournament and rated games are ordinary).
    useEffect(() => {
        if (!liveGame) {
            blindStartedRef.current = false;
            return;
        }
        if (blindStartedRef.current || history.length > 1) return;
        blindStartedRef.current = true;
        startBlindfold(activeBot ? !isRatedBotGame : !isRatedGame);
    }, [liveGame, history.length, activeBot, isRatedBotGame, isRatedGame]);

    // A friendly blindfold game against a human gets a mark in the archive after it ends (a bot one, when the game is saved):
    // POST /profile/games/{id}/blindfold with the level and the number of peeks; the server accepts it only from a participant
    // of a finished unrated game.
    useEffect(() => {
        if (!gameId || !gameOverResult || activeBot || isRatedGame || blind.level === 0 || blindMarkedRef.current === gameId) return;
        blindMarkedRef.current = gameId;
        if (!getToken()) return;
        profileApi.markBlindfold(gameId, blind.level, blind.peeks).catch(() => undefined);
    }, [gameId, gameOverResult, activeBot, isRatedGame, blind.level, blind.peeks]);

    // Opponent move animation (task 18.4): only a new opponent move in a live game against a bot or a human.
    useEffect(() => {
        const previous = animatedHistoryLength.current;
        animatedHistoryLength.current = history.length;
        const last = history[history.length - 1];
        const mine = myColor === 'white' ? 'w' : 'b';
        if (!boardPrefs.animateOpponent || viewIndex !== -1 || history.length !== previous + 1 || !(gameId || activeBot)
            || !last || last.color === mine) return;
        setMoveAnim({from: last.from, to: last.to, go: false});
        const frame = requestAnimationFrame(() => setMoveAnim((anim) => anim && {...anim, go: true}));
        const timer = setTimeout(() => setMoveAnim(null), 240);
        return () => {
            cancelAnimationFrame(frame);
            clearTimeout(timer);
            setMoveAnim(null);
        };
    }, [history.length]); // eslint-disable-line react-hooks/exhaustive-deps
    const lastMove = activeMoveIndex >= 0 ? history[activeMoveIndex] : null;

    // Squares the selected piece can go to (hint dots): only on one's own turn and on the live position.
    const legalTargetSquares = new Set<string>();
    if (selectedSquare && viewIndex === -1 && !gameOverResult) {
        const currentTurnColor = currentGame.turn() === 'w' ? 'white' : 'black';
        const isMyTurnNow = (!gameId && !activeBot) || currentTurnColor === myColor;
        if (isMyTurnNow) {
            try {
                const movesForSquare = currentGame.moves({square: selectedSquare as any, verbose: true});
                movesForSquare.forEach((m: any) => legalTargetSquares.add(m.to));
            } catch {
                // Ignore an invalid square
            }
        }
    }

    const displayedRanks = isBoardFlipped ? ['1', '2', '3', '4', '5', '6', '7', '8'] : ['8', '7', '6', '5', '4', '3', '2', '1'];
    const displayedFiles = isBoardFlipped ? [...FILES].reverse() : FILES;
    // Accessibility (task 26.3): the board can be played from the keyboard: button squares with a label "e4, white knight", arrows and
    // Enter/Space (like a click: select a piece, make a move); a hook shared with the puzzle board, useBoardKeyboard.
    const boardKeys = useBoardKeyboard(`${displayedFiles[0]}${displayedRanks[0]}`, isBoardFlipped, handleSquareClick);

    const topIsWhite = isBoardFlipped;
    // Berserk marks belong to a game between humans (one's own or watched), not to a bot or the free board.
    const isLivePvp = Boolean(gameId || spectatingGameId);
    // Berserk is possible before one's own first move: White has no moves at all, Black no more than one (White's move).
    const canBerserk = Boolean(gameId) && berserk.allowed && !gameOverResult && !berserk[myColor]
        && history.length <= (myColor === 'white' ? 0 : 1);
    const topPlayerInfo = topIsWhite ? shownWhitePlayer : shownBlackPlayer;
    const bottomPlayerInfo = topIsWhite ? shownBlackPlayer : shownWhitePlayer;
    const topPlayerTime = topIsWhite ? whiteTimeMs : blackTimeMs;
    const bottomPlayerTime = topIsWhite ? blackTimeMs : whiteTimeMs;
    const topIdlePreviewMs = Math.round((topIsWhite ? effectiveWhiteBaseMinutes : effectiveBlackBaseMinutes) * 60 * 1000);
    const bottomIdlePreviewMs = Math.round((!topIsWhite ? effectiveWhiteBaseMinutes : effectiveBlackBaseMinutes) * 60 * 1000);
    // "Captured pieces" are computed from the full set: for a game from a custom position this
    // would be almost the whole set from the first move. We show only the material advantage.
    const showCaptured = startFen === null;
    // Order of captured pieces (task 18.4): by value, by kind or by order of capture.
    const captured = orderCaptured(boardPrefs.captured, {white: material.whiteCapturedSymbols, black: material.blackCapturedSymbols},
        history.slice(0, activeMoveIndex + 1));
    const topCaptured = !showCaptured ? [] : topIsWhite ? captured.white : captured.black;
    const bottomCaptured = !showCaptured ? [] : topIsWhite ? captured.black : captured.white;
    const topAdvantage = topIsWhite ? material.whiteAdvantage : material.blackAdvantage;
    const bottomAdvantage = topIsWhite ? material.blackAdvantage : material.whiteAdvantage;

    const isBotOnTop = !!activeBotProfile && ((topIsWhite && myColor === 'black') || (!topIsWhite && myColor === 'white'));
    const isBotOnBottom = !!activeBotProfile && !isBotOnTop;

    const movePairs = pairHalfMoves(history, startFen);

    // A free board with a position different from the starting one and not final: one can play a bot from it.
    const isSandbox = !gameId && !activeBot && !spectatingGameId;
    const sandboxFen = game.fen();
    const canStartFromPosition = isSandbox && sandboxFen !== STANDARD_START_FEN && !game.isGameOver();

    const handleStartBotGame = (botId: HistoricalBotId, colorPref: 'white' | 'black' | 'random') => {
        const fromPosition = canStartFromPosition && startFromPosition;
        // A handicap only from the ordinary setup (a material handicap sets the position itself).
        const odds = !fromPosition && oddsChoice.kind !== 'none' ? oddsChoice : null;
        setActiveOdds(odds);
        startHistoricalBotGame(botId, colorPref, fromPosition ? sandboxFen : null, odds ? {odds} : {});
    };

    const handleStartCustomGame = (opponent: CustomOpponent, colorPref: 'white' | 'black' | 'random') => {
        setActiveOdds(null);
        startCustomBotGame(opponent, colorPref, canStartFromPosition && startFromPosition ? sandboxFen : null);
    };

    // A ladder game is always from the ordinary setup and against an opponent chosen by the server.
    const handleLadderStart = ({opponent, color, forfeited}: LadderStart) => {
        if (opponent.kind === 'historical' && opponent.bot_id) {
            startHistoricalBotGame(opponent.bot_id as HistoricalBotId, color, null, {ladder: true});
        } else if (opponent.config && isArchetypeId(opponent.id)) {
            // A ladder opponent is an archetype: the name and description in the player's language, in the archive by the archetype key.
            startCustomBotGame(
                {name: t(`archetypes.${opponent.id}.name`), config: opponent.config, archetypeId: opponent.id},
                color, null, {ladder: true},
            );
        }
        if (forfeited) setDrawOfferStatus(status('ladder.forfeited', {message: ladderOutcomeMessage(forfeited)}));
    };

    // Tournament game (task 15.3): the hall's time control is set to the tournament one, and the game starts when it is applied:
    // that way the time increments of the player and the bot match the tournament's, and the server will accept saving.
    const routeLocation = useLocation();
    const tournamentStart = (routeLocation.state as { tournamentGame?: TournamentGameStart } | null)?.tournamentGame;
    // A tournament game waiting until its time control is applied (the first effect sets it, the second starts it).
    const [pendingTournament, setPendingTournament] = useState<TournamentGameStart | null>(null);
    // The tournament and tournament game the game on the board belongs to, for the TournamentGameBar banner.
    const [tournamentLinkId, setTournamentLinkId] = useState<number | null>(null);
    const [tournamentGameRefId, setTournamentGameRefId] = useState<number | null>(null);
    const inTournamentGame = Boolean(tournamentLinkId && (isTournamentGame || savedTournamentId));

    // A bot game survives a page reload and leaving for another page (services/botGameSnapshot.ts): the snapshot is written
    // after every move, on closing the page and on leaving the board; when the board opens it is applied if the player is the same,
    // the game is not over and the board is not taken by another start (a tournament game, a guest game, the first game).
    const writeBotSnapshot = () => {
        if (!activeBot || gameId || gameOverResult || !currentUsername) return;
        const info = botGameInfo();
        saveBotGameSnapshot({
            username: currentUsername, botId: activeBot, custom: info.custom, color: myColor, pgn: game.pgn(),
            whiteTimeMs, blackTimeMs, baseMinutes: effectiveWhiteBaseMinutes, incrementSeconds: effectiveIncSeconds,
            odds: activeOdds ? {kind: activeOdds.kind, giver: activeOdds.giver} : null,
            ladder: info.ladder, tournamentGameId: info.tournamentGameId, tournamentId: tournamentLinkId,
            paused: botPaused,
        });
    };
    // Fresh version of the record for page-close handlers (they outlive a single render).
    const writeBotSnapshotRef = useRef(writeBotSnapshot);
    writeBotSnapshotRef.current = writeBotSnapshot;
    const botGameWasLiveRef = useRef(false);
    useEffect(() => {
        const live = Boolean(activeBot) && !gameId && !gameOverResult;
        if (live) {
            botGameWasLiveRef.current = true;
            writeBotSnapshotRef.current();
        } else if (botGameWasLiveRef.current) {
            // The game is over or abandoned: nothing to continue.
            botGameWasLiveRef.current = false;
            clearBotGameSnapshot();
        }
    }, [activeBot, gameId, gameOverResult, game, botPaused]);
    useEffect(() => {
        const save = () => writeBotSnapshotRef.current();
        window.addEventListener('pagehide', save);
        window.addEventListener('beforeunload', save);
        return () => {
            window.removeEventListener('pagehide', save);
            window.removeEventListener('beforeunload', save);
            save(); // leaving for another page: the clocks and the position at this moment
        };
    }, []);
    const resumedBotGameRef = useRef(false);
    useEffect(() => {
        if (resumedBotGameRef.current || !currentUsername || gameId || activeBot || spectatingGameId) return;
        const routeState = routeLocation.state as Record<string, unknown> | null;
        if (routeState && (routeState.tournamentGame || routeState.guestGame || routeState.firstGame)) return;
        resumedBotGameRef.current = true;
        const snapshot = loadBotGameSnapshot(currentUsername);
        if (!snapshot) return;
        const manual = ALL_TIME_CONTROLS.find((o) => o.isManual
            && o.category === timeControlCategory(snapshot.baseMinutes * 60000, snapshot.incrementSeconds * 1000));
        if (manual) setSelectedTimeControl(manual);
        setManualBaseMinutes(snapshot.baseMinutes);
        setManualIncSeconds(snapshot.incrementSeconds);
        setActiveOdds(snapshot.odds as OddsChoice | null);
        setTournamentLinkId(snapshot.tournamentId);
        setTournamentGameRefId(snapshot.tournamentGameId);
        setBotPaused(snapshot.paused === true);
        resumeBotGame(snapshot);
    }, [currentUsername, gameId, activeBot, spectatingGameId, routeLocation.state, resumeBotGame]);
    useEffect(() => {
        if (!tournamentStart || gameId || (activeBot && !gameOverResult)) return;
        const category = timeControlCategory(tournamentStart.baseTimeMs, tournamentStart.incrementMs);
        const manual = ALL_TIME_CONTROLS.find((o) => o.isManual && o.category === category);
        if (manual) setSelectedTimeControl(manual);
        setManualBaseMinutes(tournamentStart.baseTimeMs / 60000);
        setManualIncSeconds(tournamentStart.incrementMs / 1000);
        setPendingTournament(tournamentStart);
        navigate('.', {replace: true, state: null});
    }, [tournamentStart]); // eslint-disable-line react-hooks/exhaustive-deps
    useEffect(() => {
        if (!pendingTournament) return;
        const applied = Math.round(effectiveWhiteBaseMinutes * 60000) === pendingTournament.baseTimeMs
            && Math.round(effectiveIncSeconds * 1000) === pendingTournament.incrementMs;
        if (!applied) return;
        const options = {tournamentGameId: pendingTournament.gameId};
        if (pendingTournament.custom) {
            startCustomBotGame(pendingTournament.custom, pendingTournament.color, null, options);
        } else if (pendingTournament.botId) {
            startHistoricalBotGame(pendingTournament.botId as HistoricalBotId, pendingTournament.color, null, options);
        }
        setTournamentLinkId(pendingTournament.tournamentId);
        setTournamentGameRefId(pendingTournament.gameId);
        setPendingTournament(null);
    }, [pendingTournament, effectiveWhiteBaseMinutes, effectiveIncSeconds]); // eslint-disable-line react-hooks/exhaustive-deps

    // A game against a master of the past from the catalog (task 28.5): the same character as in the "Time Machine", but outside a tournament.
    // On the board the name is in the player's language, the game goes to the archive under the name from the PGN.
    const guestGame = (routeLocation.state as { guestGame?: MasterGameStart } | null)?.guestGame;
    useEffect(() => {
        if (!guestGame || gameId || (activeBot && !gameOverResult)) return;
        navigate('.', {replace: true, state: null});
        setActiveOdds(null);
        startCustomBotGame({name: guestGame.name, savedName: guestGame.savedName, config: guestGame.config}, guestGame.color, null);
    }, [guestGame]); // eslint-disable-line react-hooks/exhaustive-deps

    // The first game after registration (task 17.8): an archetype by the starting rating, the player plays White.
    const firstGame = (routeLocation.state as { firstGame?: FirstGameStart } | null)?.firstGame;
    useEffect(() => {
        if (!firstGame || gameId || (activeBot && !gameOverResult)) return;
        navigate('.', {replace: true, state: null});
        fetchBotCatalog()
            .then((catalog) => {
                const archetype = pickFirstOpponent(catalog.archetypes, firstGame.rating);
                if (!archetype) return;
                startCustomBotGame(
                    {name: t(`archetypes.${archetype.id}.name`), config: archetype.config, archetypeId: archetype.id},
                    'white', null,
                );
            })
            .catch(() => undefined);
    }, [firstGame]); // eslint-disable-line react-hooks/exhaustive-deps

    // "Review with the coach" from the puzzle page (13.3): the puzzle position goes to the free board, the coach is on.
    const location = useLocation();
    const analyzeFen = (location.state as { analyzeFen?: string } | null)?.analyzeFen;
    useEffect(() => {
        if (!analyzeFen || gameId || activeBot) return;
        if (handleLoadFen(analyzeFen) === null) coach.setEnabled(true);
        navigate('.', {replace: true, state: null});
    }, [analyzeFen]); // eslint-disable-line react-hooks/exhaustive-deps

    // "Watch" from the "Viewing" page (16.3): spectator mode for a game from location.state.
    const spectateId = (location.state as { spectate?: number } | null)?.spectate;
    useEffect(() => {
        if (!spectateId || gameId) return;
        handleSpectateGame(spectateId);
        navigate('.', {replace: true, state: null});
    }, [spectateId]); // eslint-disable-line react-hooks/exhaustive-deps

    // A direct challenge from the profile (17.1): we create a private invitation and, once the server has created it, send it to the opponent.
    const challengeTarget = (location.state as { challenge?: string } | null)?.challenge;
    const pendingChallenge = useRef<string | null>(null);
    const [challengeSent, setChallengeSent] = useState<string | null>(null);
    useEffect(() => {
        if (!challengeTarget || gameId) return;
        pendingChallenge.current = challengeTarget;
        handleCreatePrivateInvite();
        navigate('.', {replace: true, state: null});
    }, [challengeTarget]); // eslint-disable-line react-hooks/exhaustive-deps
    useEffect(() => {
        const target = pendingChallenge.current;
        if (!target || !createdInviteCode) return;
        pendingChallenge.current = null;
        socialApi.challenge(target, createdInviteCode).then(() => setChallengeSent(target)).catch(() => undefined);
    }, [createdInviteCode]);

    // Sets a position from FEN on the free board (the input field under the move list and "Review with the coach");
    // returns an error text or null. After loading, "start from this position" is marked for a bot game.
    const handleLoadFen = (fen: string): string | null => {
        const error = validateFen(fen);
        if (error) return error;
        setGame(new Chess(fen.trim()));
        setHistory([]);
        setViewIndex(-1);
        setSelectedSquare(null);
        setPendingPromotion(null);
        setPremove(null);
        setGameOverResult(null);
        setDrawOfferStatus(null);
        setStartFromPosition(true);
        playAudio('move');
        return null;
    };

    // Navigation through the game (a click in the move list and the rewind buttons) changes only viewIndex; the sound is as for
    // the shown move. Selecting the last move returns to the live position.
    const handleSelectMoveFromList = (targetIdx: number) => {
        setSelectedSquare(null);
        const isAlreadyActive = viewIndex === -1
            ? targetIdx >= history.length - 1
            : targetIdx === viewIndex;
        if (isAlreadyActive) return;
        if (history[targetIdx]) {
            playAudio(resolveMoveSound(history[targetIdx].san));
        }
        if (targetIdx >= history.length - 1) {
            setViewIndex(-1);
        } else {
            setViewIndex(targetIdx);
        }
    };

    const handleNavigateFirst = () => {
        setViewIndex(-2);
        playAudio('move');
    };

    const handleNavigateBack = () => {
        if (history.length === 0) return;
        const current = viewIndex === -1 ? history.length - 1 : prevIndexHelper(viewIndex, history.length);
        const nextIdx = current <= 0 ? -2 : current - 1;
        setViewIndex(nextIdx);
        if (nextIdx >= 0 && history[nextIdx]) {
            playAudio(resolveMoveSound(history[nextIdx].san));
        } else {
            playAudio('move');
        }
    };

    const handleNavigateForward = () => {
        let nextIdx = -1;
        if (viewIndex === -2 && history.length > 0) {
            nextIdx = history.length === 1 ? -1 : 0;
        } else if (viewIndex !== -1 && viewIndex < history.length - 2) {
            nextIdx = viewIndex + 1;
        }
        setViewIndex(nextIdx);
        const targetMove = nextIdx === -1 ? history[history.length - 1] : history[nextIdx];
        if (targetMove) {
            playAudio(resolveMoveSound(targetMove.san));
        }
    };

    const handleNavigateLast = () => {
        setViewIndex(-1);
        if (history.length > 0) {
            playAudio(resolveMoveSound(history[history.length - 1].san));
        }
    };

    // Piece image of the chosen set (SVG from /assets/pieces/{set}/, the address is built by getPieceSvgUrl); the style
    // sets the set's scale and a shadow matched to the board theme (getHarmoniousPieceStyle).
    const renderPieceSvg = (piece: { type: string; color: string }) => {
        const styleProps = getHarmoniousPieceStyle(pieceSetKey, boardThemeKey, piece.color);
        return (
            <div className="relative w-full h-full pointer-events-none flex items-center justify-center">
                <img
                    src={getPieceSvgUrl(pieceSetKey, piece.color, piece.type)}
                    className="object-contain select-none transition-transform duration-75"
                    style={styleProps}
                    draggable={false}
                    alt={`${piece.color}${piece.type}`}
                />
            </div>
        );
    };

    // Guest: instead of the board, a request to sign in (all hooks above have already been called, so the check is here and not at the start).
    if (!getToken()) {
        return (
            <div
                className="my-auto flex flex-col items-center justify-center p-8 bg-acacia rounded-lg shadow-heavy border-4 border-acacia-dark text-boxwood-light text-center">
                <div className="text-2xl font-bold mb-2">{t('hall.authRequired')}</div>
                <p className="text-base text-boxwood/85 mb-2">
                    {t('hall.authRequiredText')}
                </p>
            </div>
        );
    }

    // One's own challenge is not shown in the lobby list.
    const filteredQueue = queuePlayers.filter(p => p.user_id !== currentUserId);
    // Size the board is drawn at: the saved one, but no wider than the window (on a phone almost the full width).
    const responsiveBoardPx = typeof window !== 'undefined' ? Math.min(boardSize, window.innerWidth - 24) : boardSize;

    // Tournament game: the tournament, round, opponent, table; after the game, the next game and a path to the tournament. After the end of the
    // game it stands next to the end-of-game buttons, above the result (owner's feedback 18.11: the button back to the tournament was not
    // visible: the result pushed it past the column edge).
    const tournamentBar = inTournamentGame && tournamentLinkId ? (
        <TournamentGameBar tournamentId={savedTournamentId ?? tournamentLinkId} tournamentGameId={tournamentGameRefId}
                           gameOver={Boolean(gameOverResult)}/>
    ) : null;

    // Game control panel. Not shown to a spectator: "take back" and "reset the board" would spoil someone else's game on
    // their screen (leaving is in the chat panel). During a game it is at the bottom of the right column; after the end, right under the navigation,
    // above the "Game result": otherwise the result pushed "Game analysis", "Rematch" and "To lobby" past the column edge (owner's
    // feedback 18.11).
    const controlsPanel = (
        <GameControlsPanel
            mode={gameId ? 'pvp' : activeBot ? 'bot' : 'sandbox'}
            hideRematch={inTournamentGame}
            gameId={gameId}
            savedBotGameId={savedBotGameId}
            historyLength={history.length}
            gameOverResult={gameOverResult}
            rematchStatus={rematchStatus}
            isBotThinking={isBotThinking}
            whitePlayer={shownWhitePlayer}
            blackPlayer={shownBlackPlayer}
            navigate={navigate}
            onAbortGame={handleAbortGame}
            onPauseToggle={canPauseBot ? () => setBotPaused((p) => !p) : undefined}
            paused={botPaused}
            onBerserk={canBerserk ? handleBerserk : undefined}
            onResign={handleResign}
            onOfferDraw={activeBot ? () => void offerDrawToBot() : handleOfferDraw}
            onAcceptRematch={handleAcceptRematch}
            onDeclineRematch={handleDeclineRematch}
            onOfferRematch={handleOfferRematch}
            onResetSandbox={handleResetSandbox}
            onUndoSandboxMove={handleUndoSandboxMove}
            undoLocked={isRatedBotGame && !gameOverResult}
            hasCustomPosition={isSandbox && startFen !== null}
            onLoadFen={handleLoadFen}
        />
    );

    return (
        <div
            className="w-full max-w-[1920px] h-full flex flex-col xl:flex-row items-center xl:items-stretch justify-between gap-3 px-1 xl:overflow-hidden relative">
            {challengeSent && !gameId && (
                <div role="status" data-testid="challenge-sent"
                     className="absolute top-1 left-1/2 -translate-x-1/2 z-40 bg-amber-900/90 border border-amber-500 text-amber-100 text-sm rounded px-3 py-1.5">
                    {t('social.challengeSent', {name: challengeSent})}
                </div>
            )}

            {dragState && (
                <div
                    data-testid="drag-ghost"
                    className="fixed pointer-events-none z-50 scale-110"
                    style={{
                        left: `${dragState.x}px`,
                        top: `${dragState.y}px`,
                        width: `${responsiveBoardPx / 8}px`,
                        height: `${responsiveBoardPx / 8}px`,
                        transform: 'translate(-50%, -50%)'
                    }}
                >
                    {/* In blindfold play a dragged hidden piece is not shown: a move "from an empty square". */}
                    {!(blindVisible && !blindVisible.has(dragState.from)) && renderPieceSvg(dragState.piece)}
                </div>
            )}

            {/* LEFT COLUMN: "NEW GAME" (A STEPPED WINDOW: TIME CONTROL, OPPONENT SEARCH, BOTS), SEARCH IN PROGRESS,
                BOT OPPONENT, TOURNAMENTS, LOBBY AND LIVE */}
            <div
                className="w-full xl:w-[400px] 2xl:w-[440px] xl:h-full bg-acacia p-3 rounded-lg shadow-heavy border-2 border-acacia-dark flex flex-col gap-2 text-boxwood-light order-2 xl:order-1 shrink-0 xl:overflow-hidden">

                <GameHallHeader
                    sessionStats={sessionStats}
                    isSoundMuted={isSoundMuted}
                    onToggleSound={handleToggleSound}
                    onFlipBoard={() => setIsManualFlip(prev => !prev)}
                />

                <Button variant="primary" size="lg" icon={<Swords size={18}/>} onClick={() => setNewGameOpen(true)}
                        disabled={gameRunning} data-testid="new-game-open" className="w-full shrink-0">
                    {t('newGame.open')}
                </Button>

                {gameId && <PvpGameStatus gameOverResult={gameOverResult} isRatedGame={isRatedGame}/>}

                {isSearching && !newGameOpen && (
                    <div role="status" data-testid="searching-bar"
                         className="flex items-center justify-between gap-2 rounded-md bg-emerald-950/70 border border-emerald-600/50 px-3 py-2 text-sm text-emerald-100 shrink-0">
                        <span className="animate-pulse">{t('newGame.searching')}</span>
                        <Button size="sm" onClick={cancelMatchmaking}>{t('common.cancel')}</Button>
                    </div>
                )}

                {/* Bot opponent of the current game: name, "thinking...", a remark or a motto. */}
                {activeBotProfile && activeBot && (
                    <div className="p-2 rounded-md bg-black/55 border border-amber-600/40 text-xs text-amber-100 shrink-0" data-testid="opponent-note">
                        <div className="font-bold text-amber-400 mb-0.5 flex justify-between">
                            <span>{t('bots.thought', {name: activeBotProfile.shortName})}</span>
                            {isBotThinking && <span className="animate-pulse text-amber-300 font-mono text-[11px]">{t('bots.thinking')}</span>}
                        </div>
                        <div className="text-boxwood-light leading-snug">{botComment ? renderStatus(botComment, t) : activeBotProfile.motto}</div>
                    </div>
                )}

                {/* Tournaments waiting for the player's game: the way back, also after a page reload. */}
                {!inTournamentGame && !gameId && !(activeBot && !gameOverResult) && <ContinueTournaments/>}

                <div className="flex-1 min-h-0 flex flex-col">
                    <LobbyPanel
                        lobbyTab={lobbyTab}
                        onLobbyTabChange={setLobbyTab}
                        queuePlayers={filteredQueue}
                        liveGames={liveGames}
                        isSearching={isSearching}
                        gameId={gameId}
                        gameOverResult={gameOverResult}
                        onAcceptChallenge={acceptChallenge}
                        onSpectateGame={handleSpectateGame}
                    />
                </div>

                <NewGameDialog
                    open={newGameOpen}
                    onClose={() => setNewGameOpen(false)}
                    timeControl={(
                        <TimeControlPicker
                            selectedTimeControl={selectedTimeControl}
                            manualBaseMinutes={manualBaseMinutes}
                            manualIncSeconds={manualIncSeconds}
                            onManualBaseMinutesChange={setManualBaseMinutes}
                            onManualIncSecondsChange={setManualIncSeconds}
                            isOpen={isTimeDropdownOpen}
                            onToggleOpen={() => setIsTimeDropdownOpen(!isTimeDropdownOpen)}
                            onSelect={(opt) => {
                                setSelectedTimeControl(opt);
                                if (opt.isManual) {
                                    setManualBaseMinutes(Math.max(1, Math.round(opt.base)));
                                    setManualIncSeconds(opt.inc);
                                }
                                setIsTimeDropdownOpen(false);
                            }}
                            disabled={isSearching || !!gameId || (!!activeBot && !gameOverResult)}
                            dropdownRef={timeDropdownRef}
                        />
                    )}
                    human={(
                        <MatchmakingPanel
                            gameId={gameId}
                            gameOverResult={gameOverResult}
                            isRatedGame={isRatedGame}
                            ratedChoice={ratedChoice}
                            onRatedChoiceChange={setRatedChoice}
                            isSearching={isSearching}
                            onStartMatchmaking={startMatchmaking}
                            onCancelMatchmaking={cancelMatchmaking}
                            showInvitePanel={showInvitePanel}
                            onToggleInvitePanel={() => setShowInvitePanel(prev => !prev)}
                            inviteColorPref={inviteColorPref}
                            inviteOdds={inviteOdds}
                            onInviteOddsChange={setInviteOdds}
                            inviteVariant={inviteVariant}
                            onInviteVariantChange={setInviteVariant}
                            onInviteColorPrefChange={setInviteColorPref}
                            createdInviteCode={createdInviteCode}
                            inviteCopied={inviteCopied}
                            onCreatePrivateInvite={handleCreatePrivateInvite}
                            onCopyInviteLink={handleCopyInviteLink}
                        />
                    )}
                    bots={(
                        <div className="flex-1 min-h-0 flex flex-col gap-1.5">
                        <div className="grid grid-cols-3 gap-1 text-xs font-bold" role="tablist">
                            {(['historical', 'workshop', 'ladder'] as const).map((view) => (
                                <button key={view} type="button" role="tab" aria-selected={botsView === view}
                                        onClick={() => setBotsView(view)}
                                        className={`py-1 rounded border cursor-pointer ${botsView === view
                                            ? 'bg-amber-800 text-white border-amber-400'
                                            : 'bg-black/35 text-boxwood/85 border-amber-900/40 hover:border-amber-600/50'}`}>
                                    {t(view === 'historical' ? 'hall.viewHistorical' : view === 'workshop' ? 'hall.viewWorkshop' : 'hall.viewLadder')}
                                </button>
                            ))}
                        </div>
                        {botsView !== 'historical' ? (
                            <div className="flex-1 min-h-0 bg-acacia-dark p-2.5 rounded-md border border-amber-700/40 overflow-y-auto flex flex-col gap-2">
                                {botsView === 'ladder' ? (
                                    <LadderPanel
                                        playDisabled={(!!gameId || !!activeBot) && !gameOverResult}
                                        onStart={handleLadderStart}
                                        lastOutcome={ladderOutcome}
                                    />
                                ) : (
                                    <PersonalityWorkshop
                                        token={getToken()}
                                        playDisabled={!!gameId && !gameOverResult}
                                        onPlay={(opponent: CustomOpponent, colorPref) => handleStartCustomGame(opponent, colorPref)}
                                        canStartFromPosition={canStartFromPosition}
                                        startFromPosition={startFromPosition}
                                        onStartFromPositionChange={setStartFromPosition}
                                    />
                                )}
                            </div>
                        ) : (
                        <HistoricalBotsPanel
                            selectedBotId={selectedBotId}
                            onSelectBot={setSelectedBotId}
                            selectedBotProfile={selectedBotProfile}
                            activeBot={activeBot}
                            activeBotProfile={activeBotProfile}
                            gameId={gameId}
                            gameOverResult={gameOverResult}
                            isBotThinking={isBotThinking}
                            botComment={botComment ? renderStatus(botComment, t) : null}
                            onStartBotGame={handleStartBotGame}
                            canStartFromPosition={canStartFromPosition}
                            startFromPosition={startFromPosition}
                            onStartFromPositionChange={setStartFromPosition}
                            measured={measuredBotRatings}
                            live={liveBotStrength}
                            rivals={botRivals}
                            odds={oddsChoice}
                            onOddsChange={setOddsChoice}
                        />
                        )}
                        </div>
                    )}
                />
            </div>

            {/* CENTRE COLUMN: PLAYERS AND THE CHESS BOARD */}
            <div className="xl:h-full flex flex-col items-center justify-center gap-2 order-1 xl:order-2 shrink-0">

                <PlayerInfoBar
                    boardWidthPx={responsiveBoardPx}
                    isResizing={isResizing}
                    botProfile={isBotOnTop ? activeBotProfile : null}
                    isWhiteSide={topIsWhite}
                    idleLabel={t(topIsWhite ? 'board.idleWhite' : 'board.idleBlack')}
                    showGameInfo={Boolean(gameId || activeBot || spectatingGameId)}
                    playerInfo={topPlayerInfo}
                    berserk={isLivePvp && (topIsWhite ? berserk.white : berserk.black)}
                    hasRatingInfo={!!ratingInfo && isRatedGame}
                    ratingDelta={ratingInfo ? (topIsWhite ? ratingInfo.white_delta : ratingInfo.black_delta) : undefined}
                    capturedSymbols={topCaptured}
                    advantage={topAdvantage}
                    timeMs={topPlayerTime}
                    idlePreviewMs={topIdlePreviewMs}
                />

                {/* CHESS BOARD WITH TOUCH / POINTER EVENTS SUPPORT */}
                <div
                    ref={boardContainerRef}
                    onPointerDown={annotations.handlers.onPointerDown}
                    onPointerUp={annotations.handlers.onPointerUp}
                    onContextMenu={(e) => {
                        e.preventDefault();
                        if (premove || pendingPromotion || selectedSquare) {
                            setPremove(null);
                            setPendingPromotion(null);
                            setSelectedSquare(null);
                        }
                    }}
                    style={{
                        width: `${responsiveBoardPx}px`,
                        height: `${responsiveBoardPx}px`,
                        backgroundColor: activeTheme.border
                    }}
                    className={`p-2.5 rounded-lg shadow-heavy border-2 border-amber-950/80 relative select-none touch-none group/board shrink-0 ${isResizing ? 'transition-none ring-2 ring-amber-500/60' : 'transition-colors'}`}
                >
                    <BoardTextureLayer theme={activeTheme} where="frame"/>

                    {botPaused && (
                        <div className="absolute inset-0 z-40 rounded-lg bg-black/85 flex flex-col items-center justify-center gap-3 text-center p-4"
                             data-testid="bot-paused-overlay">
                            <span className="text-xl font-bold text-amber-200">{t('controls.pausedTitle')}</span>
                            <span className="text-sm text-boxwood/80">{t('controls.pausedHint')}</span>
                            <button type="button" onClick={() => setBotPaused(false)} data-testid="bot-resume"
                                    className="px-4 py-2 rounded bg-emerald-700 hover:bg-emerald-600 text-white font-bold cursor-pointer">
                                {t('controls.resume')}
                            </button>
                        </div>
                    )}

                    {pendingPromotion && (
                        <PromotionDialog
                            pendingPromotion={pendingPromotion}
                            displayedFiles={displayedFiles}
                            displayedRanks={displayedRanks}
                            renderPieceSvg={renderPieceSvg}
                            onSelect={handlePromotionSelect}
                            onCancel={() => setPendingPromotion(null)}
                        />
                    )}

                    <div role="group" aria-label={t('a11y.board')}
                        className="grid grid-cols-8 grid-rows-8 w-full h-full border border-black/60 relative z-10 shadow-inner-board rounded-[2px] overflow-hidden">
                        {xrayAvailable && xray.modes.size > 0 && (
                            <XrayOverlay fen={currentGame.fen()} flipped={isBoardFlipped} modes={xray.modes}
                                         selectedSquare={selectedSquare}
                                         side={xray.forOpponent ? (xraySide === 'w' ? 'b' : 'w') : xraySide}/>
                        )}
                        {viewIndex === -1 && (
                            <CoachArrowsOverlay arrows={coachArrows(coach.explanation ?? coach.advice)}
                                                highlights={[...coachHighlights(coach.explanation ?? coach.advice)]}
                                                flipped={isBoardFlipped} idPrefix="play-coach"/>
                        )}
                        <AnnotationsOverlay arrows={annotations.arrows} squares={annotations.squares}
                                            flipped={isBoardFlipped} idPrefix="play-notes"/>
                        {lastMove && boardPrefs.lastMove !== 'highlight' && (
                            <LastMoveArrow from={lastMove.from} to={lastMove.to} flipped={isBoardFlipped}/>
                        )}
                        {displayedRanks.map((rank) =>
                            displayedFiles.map((file) => {
                                const rIdx = RANKS.indexOf(rank);
                                const fIdx = FILES.indexOf(file);
                                const isDark = (rIdx + fIdx) % 2 !== 0;
                                const squareId = `${file}${rank}`;

                                const piece = boardState[rIdx][fIdx];

                                const isSelected = selectedSquare === squareId;
                                const isLastMove = lastMove && (lastMove.from === squareId || lastMove.to === squareId);
                                const isPremoveSquare = premoves.some((p) => p.from === squareId || p.to === squareId);
                                const isLegalTarget = legalTargetSquares.has(squareId);
                                const isBeingDragged = dragState?.from === squareId;
                                // Opponent move animation: the piece already stands on its square and slides there from the old one
                                // (an offset in squares), so the board squares always show the real position.
                                const slide = moveAnim?.to === squareId ? (() => {
                                    const a = squareCenter(moveAnim.from, isBoardFlipped);
                                    const b = squareCenter(moveAnim.to, isBoardFlipped);
                                    return a && b ? {dx: (a.x - b.x) / 12.5, dy: (a.y - b.y) / 12.5, go: moveAnim.go} : null;
                                })() : null;

                                return (
                                    <div
                                        key={squareId}
                                        data-square={squareId}
                                        {...boardKeys.squareProps(squareId)}
                                        aria-pressed={isSelected}
                                        aria-label={squareLabel(squareId, piece, t as Translate,
                                            Boolean(blindVisible && !blindVisible.has(squareId)))}
                                        onClick={() => handleSquareClick(squareId)}
                                        style={{
                                            backgroundColor: isDark ? activeTheme.dark : activeTheme.light
                                        }}
                                        className="w-full h-full flex items-center justify-center relative cursor-pointer transition-colors duration-75 board-square"
                                    >
                                        <BoardTextureLayer theme={activeTheme} where="square" isDark={isDark}/>

                                        {isLastMove && boardPrefs.lastMove !== 'arrow' && !isSelected && !isPremoveSquare && (
                                            <div className="absolute inset-0 z-10 pointer-events-none" style={{backgroundColor: lastMoveColor(activeTheme)}}/>
                                        )}

                                        {isPremoveSquare && (
                                            <div
                                                className="absolute inset-0 bg-rose-500/45 ring-2 ring-inset ring-rose-300/80 z-10 pointer-events-none"/>
                                        )}

                                        {isSelected && (
                                            <div
                                                className="absolute inset-0 bg-amber-400/50 ring-2 ring-inset ring-amber-300/80 z-10 pointer-events-none"/>
                                        )}

                                        {isLegalTarget && (
                                            piece ? (
                                                <div
                                                    className="absolute inset-0 rounded-full border-[5px] border-black/25 z-30 pointer-events-none m-1"/>
                                            ) : (
                                                <div
                                                    className="w-3.5 h-3.5 rounded-full bg-black/25 z-30 pointer-events-none"/>
                                            )
                                        )}

                                        {piece && !isBeingDragged && (
                                            <div
                                                onPointerDown={(e) => {
                                                    if ((e.pointerType === 'mouse' && e.button !== 0) || viewIndex !== -1 || gameOverResult) return;
                                                    // "Clicks only" (task 18.4): no dragging, a move is a click on the piece and on the square.
                                                    if (boardPrefs.moveInput === 'click') return;
                                                    // A spectator does not move pieces (and does not set premoves on someone else's board).
                                                    if (spectatingGameId) return;
                                                    const turnChar = currentGame.turn();
                                                    const myColorChar = myColor === 'white' ? 'w' : 'b';

                                                    if (gameId || activeBot || spectatingGameId) {
                                                        if (piece.color !== myColorChar) return;
                                                    } else {
                                                        if (piece.color !== turnChar) return;
                                                    }

                                                    e.stopPropagation();
                                                    if ((currentGame.turn() === 'w' ? 'white' : 'black') === myColor) {
                                                        moveStartTime.current = Date.now();
                                                    }
                                                    setSelectedSquare(squareId);
                                                    setDragState({
                                                        from: squareId,
                                                        piece,
                                                        x: e.clientX,
                                                        y: e.clientY
                                                    });
                                                }}
                                                data-testid={slide ? 'move-animation' : undefined}
                                                style={slide ? {
                                                    transform: slide.go ? 'translate(0, 0)' : `translate(${slide.dx * 100}%, ${slide.dy * 100}%)`,
                                                    transition: slide.go ? 'transform 200ms ease-out' : 'none',
                                                    zIndex: 40,
                                                } : undefined}
                                                data-hidden={blindVisible && !blindVisible.has(squareId) ? 'true' : undefined}
                                                className={`relative w-full h-full p-[1.5%] z-20 transition-transform duration-75 ${blindVisible && !blindVisible.has(squareId) ? 'opacity-0' : ''} ${
                                                    viewIndex === -1 && !gameOverResult && !spectatingGameId && (
                                                        (gameId || activeBot)
                                                            ? piece.color === (myColor === 'white' ? 'w' : 'b')
                                                            : piece.color === currentGame.turn()
                                                    )
                                                        ? 'cursor-grab active:cursor-grabbing hover:scale-[1.03]'
                                                        : ''
                                                }`}
                                            >
                                                {renderPieceSvg(piece)}
                                            </div>
                                        )}

                                        {file === displayedFiles[0] && (
                                            <span
                                                style={{color: isDark ? activeTheme.coordDark : activeTheme.coordLight}}
                                                className="absolute top-0.5 left-1 text-xs font-sans font-bold opacity-90 z-20 pointer-events-none leading-none"
                                            >
                                                {rank}
                                            </span>
                                        )}
                                        {rank === displayedRanks[7] && (
                                            <span
                                                style={{color: isDark ? activeTheme.coordDark : activeTheme.coordLight}}
                                                className="absolute bottom-0.5 right-1 text-xs font-sans font-bold opacity-90 z-20 pointer-events-none leading-none"
                                            >
                                                {file}
                                            </span>
                                        )}
                                    </div>
                                );
                            })
                        )}
                    </div>

                    {isResizing && (
                        <div
                            className="absolute bottom-5 right-5 z-40 px-2.5 py-1 rounded bg-black/85 border border-amber-500/60 text-amber-300 font-mono text-xs font-bold shadow-lg pointer-events-none">
                            {responsiveBoardPx} × {responsiveBoardPx} px
                        </div>
                    )}

                    <div
                        onPointerDown={handleResizePointerDown}
                        onDoubleClick={handleResizeDoubleClick}
                        title={t('hall.resizeHint')}
                        className={`absolute bottom-0 right-0 w-6 h-6 z-40 cursor-nwse-resize flex items-end justify-end p-0.5 rounded-tl transition-opacity ${
                            isResizing
                                ? 'opacity-100 text-amber-400'
                                : 'opacity-50 group-hover/board:opacity-90 hover:opacity-100! text-amber-200/80 hover:text-amber-300'
                        }`}
                    >
                        <svg
                            viewBox="0 0 16 16"
                            className="w-3.5 h-3.5 drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)]"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                        >
                            <line x1="14" y1="4" x2="4" y2="14"/>
                            <line x1="14" y1="9" x2="9" y2="14"/>
                            <line x1="14" y1="14" x2="14" y2="14"/>
                        </svg>
                    </div>
                </div>

                <PlayerInfoBar
                    boardWidthPx={responsiveBoardPx}
                    isResizing={isResizing}
                    botProfile={isBotOnBottom ? activeBotProfile : null}
                    isWhiteSide={!topIsWhite}
                    idleLabel={t(!topIsWhite ? 'board.youWhite' : 'board.youBlack')}
                    showGameInfo={Boolean(gameId || activeBot || spectatingGameId)}
                    playerInfo={bottomPlayerInfo}
                    berserk={isLivePvp && (topIsWhite ? berserk.black : berserk.white)}
                    hasRatingInfo={!!ratingInfo && isRatedGame}
                    ratingDelta={ratingInfo ? (!topIsWhite ? ratingInfo.white_delta : ratingInfo.black_delta) : undefined}
                    capturedSymbols={bottomCaptured}
                    advantage={bottomAdvantage}
                    timeMs={bottomPlayerTime}
                    idlePreviewMs={bottomIdlePreviewMs}
                />

                {/* Moves in words for screen readers and the position as text (task 26.3). */}
                <BoardSpeech lastMove={history.length ? history[history.length - 1] : null}
                             board={boardState} blind={Boolean(blindVisible)}/>

            </div>

            {/* RIGHT COLUMN: MOVE LOG, APPEARANCE, STATUS, CHAT, RESULT, COACH, X-RAY AND GAME CONTROL -
                by the tabs "Moves / Chat / Coach / X-ray" (sideTabs above).
                On a wide screen the column height follows the window; what does not fit scrolls (it used to be cut off). */}
            <div
                className="w-full xl:w-[390px] 2xl:w-[430px] xl:h-full bg-acacia p-3 rounded-lg shadow-heavy border-2 border-acacia-dark flex flex-col gap-2 text-boxwood-light order-3 shrink-0 xl:overflow-y-auto relative">

                <div
                    className="border-b border-acacia-light pb-2 flex justify-between items-center gap-2 shrink-0 relative"
                    ref={appearanceDropdownRef}
                >
                    <div className="min-w-0">
                        <div
                            className="text-xs tracking-wider uppercase text-boxwood/75 font-bold flex items-center gap-1.5">
                            <ListOrdered className="text-amber-400" size={15}/> {t('board.moveLog')}
                        </div>
                        <div className="text-xs sm:text-sm font-bold text-amber-200 mt-0.5 truncate">
                            {(gameId || activeBot || spectatingGameId)
                                ? t('board.versus', {white: shownWhitePlayer.username, black: shownBlackPlayer.username})
                                : t('board.freeBoard')}
                        </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                        <AppearancePickerDropdown
                            isOpen={showAppearanceDropdown}
                            onToggleOpen={() => setShowAppearanceDropdown(prev => !prev)}
                            onClose={() => setShowAppearanceDropdown(false)}
                            activeTheme={activeTheme}
                            pieceSetKey={pieceSetKey}
                            activePieceSetName={activePieceSet.name}
                            activePieceSetShortName={activePieceSet.shortName}
                            onPieceSetChange={handlePieceSetChange}
                            onThemeChange={handleThemeChange}
                            boardSize={boardSize}
                            responsiveBoardPx={responsiveBoardPx}
                            onBoardSizeChange={handleBoardSizeChange}
                        />

                        <span
                            className="px-2 py-1 rounded-md bg-acacia-dark border border-amber-700/40 font-mono text-xs text-amber-400 font-bold">
                            {gameOverResult || (history.length > 0 ? t('board.movesShort', {count: Math.ceil(history.length / 2)}) : t('board.start'))}
                        </span>
                    </div>
                </div>

                {premove && (
                    <div
                        className="bg-rose-950/90 px-3 py-1.5 rounded-md border border-rose-500/60 text-xs text-rose-100 flex items-center justify-between shadow shrink-0">
                        <span className="flex items-center gap-1.5 font-bold font-mono">
                            <Zap size={14} className="text-rose-400"/>
                            <span data-testid="premove-queue">
                                {premoves.map((p) => t('controls.premove', {
                                    from: p.from,
                                    to: p.to,
                                    promotion: p.promotion
                                        ? t('controls.premovePromotion', {piece: p.promotion.toUpperCase()})
                                        : '',
                                })).join(' · ')}
                            </span>
                        </span>
                        <button
                            type="button"
                            onClick={() => setPremove(null)}
                            className="px-2 py-0.5 bg-black/40 hover:bg-black/70 rounded text-xs font-sans text-rose-200 transition cursor-pointer"
                        >
                            {t('common.cancel')}
                        </button>
                    </div>
                )}

                {drawOfferStatus && (
                    <div
                        className="bg-amber-950/90 p-2 rounded-md border border-amber-600/50 text-xs text-amber-200 text-center flex flex-col gap-1.5 shrink-0">
                        <span>{renderStatus(drawOfferStatus, t)}</span>
                        {hasStatusKey(drawOfferStatus, 'status.drawOffered') && (
                            <div className="flex justify-center gap-2">
                                <button
                                    onClick={acceptDraw}
                                    className="px-3 py-1 bg-emerald-800 hover:bg-emerald-700 text-white rounded text-xs font-bold cursor-pointer"
                                >
                                    {t('common.accept')}
                                </button>
                                <button
                                    onClick={declineDraw}
                                    className="px-3 py-1 bg-red-800 hover:bg-red-700 text-white rounded text-xs font-bold cursor-pointer"
                                >
                                    {t('common.decline')}
                                </button>
                            </div>
                        )}
                    </div>
                )}

                {sideTabs.length > 1 && (
                    <SegmentedControl<SideTab> label={t('board.tabs.label')} value={shownTab} onChange={setSideTab}
                                              stretch testIdPrefix="side-tab"
                                              options={sideTabs.map((id) => {
                                                  const Icon = SIDE_TAB_ICONS[id];
                                                  return {
                                                      id, icon: <Icon size={14} aria-hidden/>,
                                                      label: id === 'chat' && chatUnread > 0
                                                          ? `${t('board.tabs.chat')} (${chatUnread})` : t(`board.tabs.${id}`),
                                                  };
                                              })}/>
                )}

                <div {...tabPanel('moves')}>
                {!spectatingGameId && (
                    <BlindfoldPanel inGame={liveGame}
                                    myTurn={liveGame && viewIndex === -1 && (currentGame.turn() === 'w' ? 'white' : 'black') === myColor}
                                    onMoveInput={(text) => {
                                        const move = parseMoveInput(game.moves({verbose: true}), text);
                                        if (!move) return false;
                                        executeMove(move.from, move.to, move.promotion as PromotionPiece | undefined);
                                        return true;
                                    }}/>
                )}
                {!(blind.hideMoves && blind.level > 0 && liveGame) && <MoveList
                    movePairs={movePairs}
                    activeMoveIndex={activeMoveIndex}
                    viewIndex={viewIndex}
                    historyLength={history.length}
                    hasActiveSession={Boolean(gameId || activeBot || spectatingGameId)}
                    scrollRef={notationScrollRef}
                    onSelectMove={handleSelectMoveFromList}
                    onReturnToLive={() => setViewIndex(-1)}
                />}

                <BoardNavigationControls
                    historyLength={history.length}
                    viewIndex={viewIndex}
                    onFirst={handleNavigateFirst}
                    onBack={handleNavigateBack}
                    onForward={handleNavigateForward}
                    onLast={handleNavigateLast}
                />

                {gameOverResult && tournamentBar}
                {!spectatingGameId && gameOverResult && controlsPanel}


                {activeBot && gameOverResult && savedBotGameId && (
                    <GameSummaryPanel
                        gameId={savedBotGameId}
                        playerColor={myColor}
                        recommendation={recommendationLabel}
                        onPlayRecommended={handlePlayRecommended}
                    />
                )}
                {/* Game result against a human: the review and "Club coach" cards after the game ends; a cancelled
                    game has no moves, and a spectator does not need the result. */}
                {gameId && gameOverResult && gameOverResult !== '*' && !spectatingGameId && (
                    <GameSummaryPanel gameId={gameId} playerColor={myColor} recommendation={null}/>
                )}



                {!gameOverResult && tournamentBar}
                {!spectatingGameId && !gameOverResult && controlsPanel}
                </div>

                <div {...tabPanel('chat')}>
                {(gameId || spectatingGameId) && (
                    <GameChatPanel
                        messages={chatMessages}
                        chatInput={chatInput}
                        onChatInputChange={setChatInput}
                        onSendMessage={handleSendChatMessage}
                        onSendPreset={handleSendChatPreset}
                        isSpectator={!!spectatingGameId}
                        onLeaveSpectate={handleLeaveSpectate}
                        myName={currentUsername}
                        gameId={gameId || spectatingGameId}
                    />
                )}
                </div>
                <div {...tabPanel('coach')}>
                {!gameId && !spectatingGameId && (
                    <CoachPanel
                        coach={coach}
                        locked={isRatedBotGame && !gameOverResult}
                        inBotGame={Boolean(activeBot) && !gameOverResult}
                        canAdvise={viewIndex === -1 && !gameOverResult && !game.isGameOver() && !coach.pending && (!activeBot || game.turn() === myColor[0])}
                        onAdvice={handleCoachAdvice}
                        onTakeBack={handleCoachTakeBack}
                        auxOpen={auxOpen}
                        onToggleAux={() => setAuxOpen((open) => !open)}
                    >
                        <AuxBoard key={auxOpen ? 'aux-open' : 'aux-closed'} fen={game.fen()} flipped={isBoardFlipped}
                                  lightColor={activeTheme.light} darkColor={activeTheme.dark}
                                  renderPiece={renderPieceSvg} onClose={() => setAuxOpen(false)}
                                  xrayModes={xrayAvailable ? xray.modes : undefined} xrayForOpponent={xray.forOpponent}/>
                    </CoachPanel>
                )}
                </div>
                <div {...tabPanel('xray')}>
                {xrayAvailable && <XrayPanel settings={xray} canSelect={!spectatingGameId}/>}
                </div>

            </div>

        </div>
    );
}

