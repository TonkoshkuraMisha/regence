// --- FILE: frontend/src/components/GameViewer.tsx ---
// Game viewing and review (/game/:id, /library/game/:id, /import/game/:id): a board with move paging, a full review
// by the engine (side accuracy, move classification, evaluation bar and graph), coach comments, the game summary,
// the openings reference, a board x-ray, arrows and right-button marks, deviations from one's own repertoire, PGN export.
// The review is computed by the server (/analysis/game/{id}) and stored; a library game has no engine review, and
// an imported one has its own (/imports).
//
// Where the data comes from. Moves and headers are the game PGN: GET /profile/games/{id}/pgn, /library/games/{id}/pgn or
// /imports/games/{id}/pgn (the last one only for the owner, with a token). A ready review is a GET at the review address on
// open; the page does not start a new review by itself, only on a button (POST; the server limits the number of
// reviews). Names, ratings, result and date come from the route state if the game was opened from a list, otherwise from the PGN
// headers. The coach text is assembled from coach.* catalog keys; the library game annotation is the annotation field of the
// GET /library/games/{id} response; "Guess the move" is GET /guess/game/{id}; one's own mistake puzzles are GET
// /puzzles/personal/game/{id} or the puzzle_plies field of an imported game (GET /imports/games/{id}). While there is
// no review, the evaluation bar shows a rough material count
// on the client (not the engine). Styling is the review theme from the settings or, if not set, the game theme.
// Paging here works differently from the main board: viewIndex is the index of the shown ply, -1 is the starting
// position; there is no "live" position.

import {useState, useEffect, useRef, useMemo, useCallback} from 'react';
import {useParams, useLocation, useNavigate, Link} from 'react-router-dom';
import {Chess} from 'chess.js';
import {ArrowLeft, Download, Loader2, Sword, Palette, Cpu, Sparkles, Volume2, VolumeX, Crown, Share2} from 'lucide-react';
import {gameDisplayDate} from '../services/gameDates';
import {
    BOARD_THEMES,
    MIN_BOARD_SIZE,
    getMaxViewportBoardSize,
    getDefaultBoardSize
} from './Chessboard';
import {errorMessage} from '../services/apiErrors';
import {analysisApi} from '../services/analysis';
import {positionWords, squareLabel} from '../services/a11y/speech';
import type {Translate} from '../services/a11y/speech';
import type {GameSource} from '../services/analysis';
import {soundEngine, resolveMoveSound} from '../services/soundEngine';
import {customStartFen, pairHalfMoves} from './chessboard/boardUtils';
import type {SoundEventType} from '../services/soundEngine';
import {
    getAnalysisBoardThemeKey,
    getAnalysisPieceSetKey,
    hasAnalysisAppearance,
    setAnalysisAppearance,
    getPieceSvgUrl,
    getHarmoniousPieceStyle,
    lastMoveColor
} from '../config/boardAppearance';
import {BoardTextureLayer} from './chessboard/BoardTextureLayer';
import {renderUiMessage, uiMessage, useI18n} from '../i18n';
import type {UiMessage} from '../i18n';
import {displayPlayerName} from '../config/players';
import {coachArrows, coachHighlights, coachText} from '../services/coach';
import type {CoachArrowKind} from '../services/coach';
import {AnnotationsOverlay, useBoardAnnotations} from './chessboard/annotations';
import {isSummaryKind} from '../services/gameSummary';
import {XrayOverlay} from './xray/XrayOverlay';
import {puzzlesApi} from '../services/puzzles';
import {guessApi} from '../services/guess';
import {OpeningExplorer} from './OpeningExplorer';
import {AddToRepertoire} from './repertoire/AddToRepertoire';
import {RepertoireDeviations} from './repertoire/RepertoireDeviations';
import {buildPgn, downloadText} from '../services/pgnExport';
import {XrayPanel} from './xray/XrayPanel';
import {useXraySettings} from './xray/useXraySettings';
import {getToken} from '../services/authToken';
import {libraryApi} from '../services/library';
import {importApi} from '../services/gameImport';
import type {LibraryAnnotation} from '../services/library';
import {LibraryAnnotationPanel} from './library/LibraryAnnotationPanel';

import {
    COACH_ARROW_COLORS, FILES, RANKS, annotatedMoves, chartPoints, computeStaticWhiteEvalCp, evalCpToWhitePercentage,
} from './gameViewer/viewerModel';
import type {FullGameAnalysisReport} from './gameViewer/viewerModel';
import {CoachCommentBox, CriticalMoments, EvalChart, SideStatsCard} from './gameViewer/AnalysisSummary';
import {MoveList} from './gameViewer/MoveList';
import {scrollMoveIntoList} from './chessboard/scrollMove';
import {NavigationControls} from './gameViewer/NavigationControls';
import {ViewerAppearancePanel} from './gameViewer/ViewerAppearancePanel';
import {useKidMode} from '../services/kidMode';

/**
 * library is a library game (task 27.1): PGN from /library, no engine review, no "Guess the move" and no own mistakes,
 * as they are tied to games of players and bots.
 * imported is a game of a player from another site (task 24.1): PGN and review from /imports (only for the owner, with a token),
 * "a puzzle was made from this move" badges; no "Guess the move" and no repertoire deviations for site games.
 */
export default function GameViewer({library = false, imported = false}: { library?: boolean; imported?: boolean }) {
    const {t, dateLocale} = useI18n();
    // Kid mode (task 23.1): no sharing to the feed.
    const kidMode = useKidMode();
    const {gameId} = useParams<{ gameId: string }>();
    const location = useLocation();
    const navigate = useNavigate();
    const gameDataFromState = location.state?.game;

    const [history, setHistory] = useState<any[]>([]);
    const [pgnHeaders, setPgnHeaders] = useState<Record<string, string>>({});
    // The game may have started from a non-standard setup (a FEN header in the PGN): then positions
    // are restored from it.
    const [startFen, setStartFen] = useState<string | null>(null);
    const [viewIndex, setViewIndex] = useState<number>(-1);
    const [libraryAnnotation, setLibraryAnnotation] = useState<LibraryAnnotation | null>(null);
    const [isFlipped, setIsFlipped] = useState(false);
    const [showAppearancePanel, setShowAppearancePanel] = useState(false);
    const [isSoundMuted, setIsSoundMuted] = useState<boolean>(() => soundEngine.isMuted());

    const [analysisReport, setAnalysisReport] = useState<FullGameAnalysisReport | null>(null);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [analysisError, setAnalysisError] = useState<UiMessage | null>(null);

    // Right-button marks are a shared layer of the boards (task B.1). In review they survive move paging (a plan several
    // moves ahead) and are cleared by changing the game, a left click on the board or Escape.
    const notes = useBoardAnnotations(library ? `library-${gameId ?? ''}` : imported ? `imported-${gameId ?? ''}` : gameId ?? '');
    // Where the game comes from: the PGN and review addresses depend on it (services/analysis.ts).
    const source: GameSource = library ? 'library' : imported ? 'imported' : 'played';
    const pgnUrl = analysisApi.pgnUrl(source, gameId ?? '');
    // Games from other sites are seen only by the owner: requests carry a token.
    const clearNotes = notes.clear;

    // Review theme (task 18.3): one's own if set in the settings, otherwise as in the game.
    const [boardThemeKey, setBoardThemeKey] = useState<string>(() => getAnalysisBoardThemeKey());
    const [pieceSetKey, setPieceSetKey] = useState<string>(() => getAnalysisPieceSetKey());

    const [boardSize, setBoardSize] = useState<number>(() => {
        const maxFit = getMaxViewportBoardSize();
        const savedSize = localStorage.getItem('regence_board_size');
        if (savedSize) {
            const parsed = Number(savedSize);
            if (!Number.isNaN(parsed) && parsed >= MIN_BOARD_SIZE) {
                return Math.min(parsed, maxFit);
            }
        }
        return getDefaultBoardSize();
    });
    const [isResizing, setIsResizing] = useState(false);
    const resizeStartRef = useRef<{ startX: number; startY: number; startSize: number } | null>(null);

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<UiMessage | null>(null);

    const notationScrollRef = useRef<HTMLDivElement>(null);

    const activeTheme = BOARD_THEMES[boardThemeKey] || BOARD_THEMES.walnut;

    const playAudio = useCallback((type: SoundEventType) => {
        soundEngine.play(type);
    }, []);

    const handleToggleSound = () => {
        const nextMuted = soundEngine.toggleMute();
        setIsSoundMuted(nextMuted);
        if (!nextMuted) {
            soundEngine.play('move');
        }
    };

    useEffect(() => {
        const handleWindowResize = () => {
            const maxFit = getMaxViewportBoardSize();
            setBoardSize(prev => Math.min(prev, maxFit));
        };
        window.addEventListener('resize', handleWindowResize);
        return () => window.removeEventListener('resize', handleWindowResize);
    }, []);

    const handleThemeChange = (themeId: string) => {
        setBoardThemeKey(themeId);
        if (hasAnalysisAppearance()) setAnalysisAppearance(themeId, pieceSetKey);
        else localStorage.setItem('regence_board_theme', themeId);
    };

    const handlePieceSetChange = (setId: string) => {
        setPieceSetKey(setId);
        if (hasAnalysisAppearance()) setAnalysisAppearance(boardThemeKey, setId);
        else localStorage.setItem('regence_piece_set', setId);
    };

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

    useEffect(() => {
        const loadGame = async () => {
            setLoading(true);
            setError(null);
            setAnalysisReport(null);
            try {
                const [pgnText, cachedData] = await Promise.all([
                    analysisApi.pgn(source, gameId ?? ''),
                    library ? Promise.resolve(null) : analysisApi.cached(source, gameId ?? ''),
                ]);
                // A Fischer random game: the client chess library has no 960 rules, the 960 viewer gets the positions from the server.
                if (source !== 'library' && pgnText.includes('[Variant "Chess960"]')) {
                    navigate(source === 'imported' ? `/import/game/${gameId}/960` : `/play/960/game/${gameId}`, {replace: true});
                    return;
                }
                const newGame = new Chess();
                newGame.loadPgn(pgnText);

                const newHistory = newGame.history({verbose: true});
                setPgnHeaders(newGame.header());
                setStartFen(customStartFen(newGame));
                setHistory(newHistory);
                // By default we show the final position of the game, not the starting one:
                // this is a review of a game just played (or an archived one), not an empty board.
                setViewIndex(newHistory.length - 1);

                // An empty report for a game with moves is not an analysis but a PGN parsing failure on the server:
                // showing "100 %" without a graph is wrong, let the player run the analysis again.
                if (cachedData && Array.isArray(cachedData.moves)
                    && (cachedData.moves.length > 0 || newHistory.length === 0)) {
                    setAnalysisReport(cachedData);
                }
            } catch {
                setError(uiMessage('viewer.loadFailed'));
            } finally {
                setLoading(false);
            }
        };

        if (gameId) loadGame();
        setLibraryAnnotation(null);
        if (gameId && library) libraryApi.annotation(gameId).then(setLibraryAnnotation).catch(() => undefined);
    }, [gameId, library, imported]); // eslint-disable-line react-hooks/exhaustive-deps

    const handleRunFullAnalysis = async () => {
        if (!gameId || isAnalyzing) return;
        setIsAnalyzing(true);
        setAnalysisError(null);
        try {
            // With a token (if the player is signed in) the request limit is counted per user, not per shared IP.
            const data = await analysisApi.run(source, gameId);
            if (!Array.isArray(data.moves) || (data.moves.length === 0 && history.length > 0)) {
                setAnalysisError(uiMessage('viewer.analysisEmpty'));
                return;
            }
            setAnalysisReport(data);
            playAudio('start');
        } catch (err) {
            setAnalysisError(errorMessage(err, 'viewer.analysisUnavailable'));
        } finally {
            setIsAnalyzing(false);
        }
    };

    // The key handler hangs on window and outlives renders. It reads the history and the current move through a ref
    // updated on every render, not from the effect closure: the effect is re-registered only after
    // rendering, and a key press right after the game loaded saw an empty history and was silently lost.
    const navigationRef = useRef({history, viewIndex});
    navigationRef.current = {history, viewIndex};

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                clearNotes();
                setShowAppearancePanel(false);
                return;
            }
            // setViewIndex takes a ready value, not an updater function: React StrictMode
            // in development calls such a function twice, and the sound from a side effect inside it
            // would play twice in a row (out of sync, on different Audio ticks).
            const {history: moves, viewIndex: current} = navigationRef.current;
            if (e.key === 'ArrowLeft') {
                e.preventDefault();
                const nextIdx = Math.max(-1, current - 1);
                if (nextIdx === current) return;
                setViewIndex(nextIdx);
                playAudio(nextIdx >= 0 ? resolveMoveSound(moves[nextIdx].san) : 'move');
            } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                const nextIdx = Math.min(moves.length - 1, current + 1);
                if (nextIdx === current) return;
                setViewIndex(nextIdx);
                playAudio(resolveMoveSound(moves[nextIdx].san));
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (current === -1) return;
                setViewIndex(-1);
                playAudio('move');
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                const lastIdx = moves.length - 1;
                if (current === lastIdx) return;
                setViewIndex(lastIdx);
                if (lastIdx >= 0) playAudio(resolveMoveSound(moves[lastIdx].san));
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [playAudio, clearNotes]);

    useEffect(() => {
        // Only the move list window scrolls: the page and the board stay in place (scrollMove.ts).
        const list = notationScrollRef.current;
        if (!list) return;
        const activeElement = list.querySelector<HTMLElement>('.active-move');
        if (activeElement) scrollMoveIntoList(list, activeElement);
        else if (viewIndex === -1) list.scrollTop = 0;
    }, [viewIndex]);

    const currentGame = useMemo(() => {
        const cg = startFen ? new Chess(startFen) : new Chess();
        for (let i = 0; i <= viewIndex; i++) {
            if (history[i]) cg.move(history[i]);
        }
        return cg;
    }, [history, viewIndex, startFen]);

    const boardState = currentGame.board();

    const currentEval = useMemo(() => {
        if (viewIndex < 0) {
            return {cp: 20, display: '+0.2', bestMoveUci: null as string | null};
        }
        if (analysisReport && analysisReport.moves[viewIndex]) {
            const m = analysisReport.moves[viewIndex];
            return {
                cp: m.eval_cp,
                display: m.eval_display,
                bestMoveUci: m.best_move_uci
            };
        }
        const fallback = computeStaticWhiteEvalCp(currentGame);
        return {cp: fallback.cp, display: fallback.display, bestMoveUci: null as string | null};
    }, [viewIndex, analysisReport, currentGame]);

    const whiteBarPercent = evalCpToWhitePercentage(currentEval.cp);

    // The coach for the current move: the text, arrows (best move, threat, idea) and highlighted targets.
    const [showCoachArrows, setShowCoachArrows] = useState(true);
    // Board x-ray (task 12.1): in review, for the side that is to move in the shown position.
    const xray = useXraySettings();
    // Selected moments for "Guess the master's move" (task 14.3): if present, the button leads to the first.
    const [guessFirstId, setGuessFirstId] = useState<number | null>(null);
    // Openings reference for the shown position (task 16.2): opens on a button, the request only then.
    const [showExplorer, setShowExplorer] = useState(false);
    useEffect(() => {
        if (!gameId || library || imported) return;
        guessApi.ofGame(Number(gameId))
            .then((r) => setGuessFirstId(r.positions[0]?.id ?? null))
            .catch(() => setGuessFirstId(null));
    }, [gameId]);
    // Moves of this game from which "Your mistakes" puzzles were made (task 13.5): only one's own, only with a token.
    const [personalPlies, setPersonalPlies] = useState<Set<number>>(new Set());
    useEffect(() => {
        if (!gameId || library || !getToken()) return;
        const plies = imported
            ? importApi.game(gameId).then((body) => body.puzzle_plies)
            : puzzlesApi.personalPlies(Number(gameId)).then((body) => body.plies);
        plies.then((list) => setPersonalPlies(new Set(list))).catch(() => undefined);
    }, [gameId]);
    const currentCoach = viewIndex >= 0 ? analysisReport?.moves[viewIndex]?.coach ?? null : null;
    const currentCoachText = coachText(currentCoach, t);
    const visibleCoachArrows = showCoachArrows ? coachArrows(currentCoach) : [];
    const coachTargets = showCoachArrows ? coachHighlights(currentCoach) : new Set<string>();

    const chartData = useMemo(() => chartPoints(analysisReport), [analysisReport]);

    const renderPieceSvg = (piece: { type: string; color: string }) => {
        const styleProps = getHarmoniousPieceStyle(pieceSetKey, boardThemeKey, piece.color);
        return (
            <div className="relative w-full h-full pointer-events-none flex items-center justify-center">
                <img
                    src={getPieceSvgUrl(pieceSetKey, piece.color, piece.type)}
                    className="object-contain select-none"
                    style={styleProps}
                    draggable={false}
                    alt={`${piece.color} ${piece.type}`}
                />
            </div>
        );
    };

    // Names of bots and archetypes from the archive are in the player's language; PGN headers are as recorded.
    const whiteName = displayPlayerName(gameDataFromState?.white_username, t) || pgnHeaders.White || t('common.white');
    const whiteRating = gameDataFromState?.white_rating || pgnHeaders.WhiteElo || '?';
    const blackName = displayPlayerName(gameDataFromState?.black_username, t) || pgnHeaders.Black || t('common.black');
    const blackRating = gameDataFromState?.black_rating || pgnHeaders.BlackElo || '?';
    const resultStr = gameDataFromState?.result || pgnHeaders.Result || '*';

    const displayedRanks = isFlipped ? [...RANKS].reverse() : RANKS;
    const displayedFiles = isFlipped ? [...FILES].reverse() : FILES;

    const topName = isFlipped ? whiteName : blackName;
    const topRating = isFlipped ? whiteRating : blackRating;
    const bottomName = isFlipped ? blackName : whiteName;
    const bottomRating = isFlipped ? blackRating : whiteRating;

    const TopIcon = isFlipped ? '♙' : '♟';
    const BottomIcon = isFlipped ? '♟' : '♙';

    const topIconBg = isFlipped ? 'bg-boxwood text-acacia-dark' : 'bg-acacia text-amber-200';
    const bottomIconBg = isFlipped ? 'bg-acacia text-amber-200' : 'bg-boxwood text-acacia-dark';

    const displayDate = gameDisplayDate(gameDataFromState?.pgn_date || pgnHeaders.Date, gameDataFromState?.finished_at,
        dateLocale) ?? t('viewer.archivedGame');

    const squareToSvgCoords = (sq: string): { x: number; y: number } | null => {
        if (!sq || sq.length < 2) return null;
        const fIdx = displayedFiles.indexOf(sq[0]);
        const rIdx = displayedRanks.indexOf(sq[1]);
        if (fIdx === -1 || rIdx === -1) return null;
        return {
            x: (fIdx + 0.5) * 12.5,
            y: (rIdx + 0.5) * 12.5
        };
    };

    if (loading) {
        return (
            <div className="my-auto flex flex-col items-center justify-center w-full text-boxwood-light">
                <Loader2 className="animate-spin text-amber-500 mb-3" size={40}/>
                <div className="text-base font-bold">{t('viewer.loading')}</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="my-auto bg-red-950/80 border border-red-800 p-6 rounded-lg text-red-200 text-center">
                <h2 className="text-xl font-bold mb-2">{t('common.error')}</h2>
                <p>{renderUiMessage(error, t)}</p>
                <button
                    onClick={() => window.history.back()}
                    className="mt-4 inline-block px-4 py-2 bg-black/40 rounded hover:bg-black/60 transition text-amber-400 border border-amber-900/50 cursor-pointer"
                >
                    {t('viewer.backButton')}
                </button>
            </div>
        );
    }

    const movePairs = pairHalfMoves(history, startFen).map((pair) => ({
        moveNumber: pair.moveNumber,
        white: pair.whiteSan ?? '…',
        black: pair.blackSan ?? '',
        whiteIndex: pair.whiteIdx,
        blackIndex: pair.blackIdx ?? -1,
    }));

    const responsiveBoardPx = typeof window !== 'undefined' ? Math.min(boardSize, window.innerWidth - 56) : boardSize;

    return (
        <div
            className="w-full max-w-[1800px] h-full flex flex-col xl:flex-row items-center xl:items-stretch justify-center gap-5 px-2 xl:overflow-hidden relative">

            <div className="flex items-center justify-center gap-2.5 sm:gap-3 shrink-0 my-auto">

                <div
                    style={{height: `${responsiveBoardPx}px`}}
                    className={`w-6 sm:w-7 rounded-md overflow-hidden border-2 border-amber-950/90 shadow-heavy flex flex-col relative select-none shrink-0 ${
                        isFlipped ? 'flex-col-reverse' : 'flex-col'
                    }`}
                    title={t('viewer.evaluation', {value: currentEval.display})}
                >
                    <div
                        style={{height: `${100 - whiteBarPercent}%`}}
                        className="w-full bg-[#1E1916] transition-all duration-300"
                    />
                    <div
                        style={{height: `${whiteBarPercent}%`}}
                        className="w-full bg-[#EBE1CE] transition-all duration-300"
                    />
                    <span
                        className={`absolute left-0 right-0 text-center font-mono text-[10px] font-extrabold tracking-tighter px-0.5 ${
                            currentEval.cp >= 0
                                ? (isFlipped ? 'top-1.5 text-[#1E1916]' : 'bottom-1.5 text-[#1E1916]')
                                : (isFlipped ? 'bottom-1.5 text-[#EBE1CE]' : 'top-1.5 text-[#EBE1CE]')
                        }`}
                    >
                        {currentEval.display}
                    </span>
                </div>

                <div className="flex flex-col items-center gap-2.5">
                    <div
                        style={{width: `${responsiveBoardPx}px`}}
                        className="bg-acacia-dark px-3.5 py-2 rounded-lg shadow-heavy border-2 border-amber-900/50 flex justify-between items-center text-boxwood-light"
                    >
                        <div className="flex items-center gap-3 min-w-0">
                            <div
                                className={`w-9 h-9 rounded-md flex items-center justify-center border border-amber-600/30 font-bold text-lg shrink-0 ${topIconBg}`}>
                                {TopIcon}
                            </div>
                            <div className="font-bold text-base flex items-center gap-2 truncate">
                                <Link to={`/profile/${encodeURIComponent(topName)}`} className="hover:underline text-amber-200 truncate">
                                    {topName}
                                </Link>
                                <span
                                    className="text-xs px-2 py-0.5 rounded bg-black/45 text-amber-400 border border-amber-600/25 font-mono">
                                    {topRating}
                                </span>
                            </div>
                        </div>

                        {analysisReport && (
                            <div
                                className="text-xs font-mono font-bold px-2.5 py-1 rounded bg-black/50 border border-amber-700/40 text-emerald-300">
                                {t('viewer.accuracy', {value: isFlipped ? analysisReport.white.accuracy : analysisReport.black.accuracy})}
                            </div>
                        )}
                    </div>

                    <div
                        onContextMenu={(e) => e.preventDefault()}
                        onPointerDown={notes.handlers.onPointerDown}
                        onPointerUp={notes.handlers.onPointerUp}
                        style={{
                            width: `${responsiveBoardPx}px`,
                            height: `${responsiveBoardPx}px`,
                            backgroundColor: activeTheme.border
                        }}
                        className={`p-3 rounded-lg shadow-heavy border-2 border-amber-950/80 relative select-none touch-none group/board ${isResizing ? 'transition-none ring-2 ring-amber-500/60' : 'transition-colors'}`}
                    >
                        <BoardTextureLayer theme={activeTheme} where="frame"/>

                        <div
                            role="group" aria-label={positionWords(boardState, t as Translate)}
                            className="grid grid-cols-8 grid-rows-8 w-full h-full border border-black/60 relative z-10 shadow-inner-board rounded-xs overflow-hidden">
                            {displayedRanks.map((rank) =>
                                displayedFiles.map((file) => {
                                    const rIdx = RANKS.indexOf(rank);
                                    const fIdx = FILES.indexOf(file);
                                    const isDark = (rIdx + fIdx) % 2 !== 0;
                                    const squareId = `${file}${rank}`;
                                    const piece = boardState[rIdx][fIdx];

                                    const lastMove = viewIndex >= 0 ? history[viewIndex] : null;
                                    const isLastMoveSquare = lastMove && (lastMove.from === squareId || lastMove.to === squareId);
                                    const isNoted = squareId in notes.squares;
                                    const isCoachTarget = coachTargets.has(squareId);

                                    return (
                                        <div
                                            key={squareId}
                                            data-square={squareId}
                                            aria-label={squareLabel(squareId, piece, t as Translate)}
                                            style={{
                                                backgroundColor: isDark ? activeTheme.dark : activeTheme.light
                                            }}
                                            className="w-full h-full flex items-center justify-center relative"
                                        >
                                            <BoardTextureLayer theme={activeTheme} where="square" isDark={isDark}/>

                                            {isLastMoveSquare && (
                                                <div
                                                    className="absolute inset-0 z-10 pointer-events-none" style={{backgroundColor: lastMoveColor(activeTheme)}}/>
                                            )}

                                            {isCoachTarget && !isNoted && (
                                                <div
                                                    data-testid="coach-target"
                                                    className="absolute inset-0 ring-[3px] ring-inset ring-rose-400/90 z-10 pointer-events-none"/>
                                            )}

                                            {piece && (
                                                <div
                                                    className="relative w-full h-full p-[1.5%] z-20 pointer-events-none">
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

                            {xray.modes.size > 0 && (
                                <XrayOverlay fen={currentGame.fen()} flipped={isFlipped} modes={xray.modes}
                                             side={xray.forOpponent ? (currentGame.turn() === 'w' ? 'b' : 'w') : currentGame.turn()}/>
                            )}
                            {visibleCoachArrows.length > 0 && (
                                <svg
                                    viewBox="0 0 100 100"
                                    className="absolute inset-0 w-full h-full z-30 pointer-events-none"
                                >
                                    <defs>
                                        {(Object.keys(COACH_ARROW_COLORS) as CoachArrowKind[]).map((kind) => (
                                            <marker key={kind} id={`coach-arrowhead-${kind}`} markerWidth="3.5"
                                                    markerHeight="3.5" refX="2.3" refY="1.75" orient="auto">
                                                <polygon points="0 0, 3.5 1.75, 0 3.5" fill={COACH_ARROW_COLORS[kind]}/>
                                            </marker>
                                        ))}
                                    </defs>
                                    {visibleCoachArrows.map((arr, idx) => {
                                        const start = squareToSvgCoords(arr.from);
                                        const end = squareToSvgCoords(arr.to);
                                        if (!start || !end) return null;
                                        return (
                                            <line
                                                key={`coach-${arr.kind}-${arr.from}-${arr.to}-${idx}`}
                                                data-testid={`coach-arrow-${arr.kind}`}
                                                x1={start.x}
                                                y1={start.y}
                                                x2={end.x}
                                                y2={end.y}
                                                stroke={COACH_ARROW_COLORS[arr.kind]}
                                                strokeWidth="2.1"
                                                strokeLinecap="round"
                                                markerEnd={`url(#coach-arrowhead-${arr.kind})`}
                                            />
                                        );
                                    })}
                                </svg>
                            )}
                            <AnnotationsOverlay arrows={notes.arrows} squares={notes.squares} flipped={isFlipped}
                                                idPrefix="viewer-notes"/>
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
                            title={t('viewer.resizeHint')}
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

                    <div
                        style={{width: `${responsiveBoardPx}px`}}
                        className="bg-acacia-dark px-3.5 py-2 rounded-lg shadow-heavy border-2 border-amber-900/50 flex justify-between items-center text-boxwood-light"
                    >
                        <div className="flex items-center gap-3 min-w-0">
                            <div
                                className={`w-9 h-9 rounded-md flex items-center justify-center border border-amber-600/30 font-bold text-lg shrink-0 ${bottomIconBg}`}>
                                {BottomIcon}
                            </div>
                            <div className="font-bold text-base flex items-center gap-2 truncate">
                                <Link to={`/profile/${encodeURIComponent(bottomName)}`} className="hover:underline text-amber-200 truncate">
                                    {bottomName}
                                </Link>
                                <span
                                    className="text-xs px-2 py-0.5 rounded bg-black/45 text-amber-400 border border-amber-600/25 font-mono">
                                    {bottomRating}
                                </span>
                            </div>
                        </div>

                        {analysisReport && (
                            <div
                                className="text-xs font-mono font-bold px-2.5 py-1 rounded bg-black/50 border border-amber-700/40 text-emerald-300">
                                {t('viewer.accuracy', {value: isFlipped ? analysisReport.black.accuracy : analysisReport.white.accuracy})}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <div
                className="w-full xl:w-110 2xl:w-120 xl:h-full bg-acacia p-3.5 rounded-lg shadow-heavy border-2 border-acacia-dark flex flex-col gap-2.5 text-boxwood-light shrink-0 xl:overflow-hidden">

                <div className="flex items-center justify-between gap-2 border-b border-acacia-light pb-2.5 shrink-0">
                    <div className="flex items-center gap-2.5 min-w-0">
                        <button
                            onClick={() => window.history.back()}
                            className="p-1.5 bg-black/25 hover:bg-black/45 rounded-md transition border border-amber-900/50 cursor-pointer shrink-0"
                            title={t('common.back')}
                            aria-label={t('common.back')}
                        >
                            <ArrowLeft size={16} className="text-amber-400"/>
                        </button>
                        <div className="min-w-0">
                            <div
                                className="text-xs tracking-wider uppercase text-boxwood/75 font-bold flex items-center gap-1.5">
                                <Sword size={13} className="text-amber-400"/> {t('viewer.studio')}
                            </div>
                            <div className="text-xs text-amber-300 mt-0.5 font-mono truncate">
                                {displayDate} {pgnHeaders.ECO ? `• ECO ${pgnHeaders.ECO}` : ''}
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                        <button
                            type="button"
                            onClick={handleToggleSound}
                            className={`p-1.5 rounded-md border transition cursor-pointer shadow-sm ${
                                isSoundMuted
                                    ? 'bg-red-950/60 border-red-800/60 text-red-300 hover:bg-red-900/60'
                                    : 'bg-acacia-dark hover:bg-black/45 border-amber-800/50 text-amber-300'
                            }`}
                            title={t(isSoundMuted ? 'common.soundOn' : 'common.soundOff')}
                        >
                            {isSoundMuted ? <VolumeX size={15}/> : <Volume2 size={15}/>}
                        </button>
                        <button
                            type="button"
                            onClick={() => setShowAppearancePanel(prev => !prev)}
                            className={`px-2.5 py-1.5 rounded-md border text-xs font-bold flex items-center gap-1.5 transition cursor-pointer ${
                                showAppearancePanel
                                    ? 'bg-amber-700 text-white border-amber-400'
                                    : 'bg-acacia-dark hover:bg-black/45 text-amber-200 border-amber-800/50'
                            }`}
                        >
                            <Palette size={14} className="text-amber-400"/> {t('viewer.look')}
                        </button>
                        <span
                            className="bg-acacia-dark px-2.5 py-1 rounded-md border border-amber-700/50 text-amber-400 font-mono text-xs font-bold">
                            {resultStr}
                        </span>
                    </div>
                </div>

                {showAppearancePanel && (
                    <ViewerAppearancePanel pieceSetKey={pieceSetKey} themeKey={activeTheme.id} onPieceSetChange={handlePieceSetChange}
                                           onThemeChange={handleThemeChange} onClose={() => setShowAppearancePanel(false)}/>
                )}

                <div
                    className="bg-acacia-dark p-3 rounded-md border border-amber-800/50 flex flex-col gap-2.5 xl:shrink xl:min-h-0 xl:overflow-y-auto shrink-0 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:bg-amber-900/50">
                    {library ? (libraryAnnotation && (
                        <LibraryAnnotationPanel annotation={libraryAnnotation} viewIndex={viewIndex} onSelect={setViewIndex}/>
                    )) : !analysisReport ? (
                        <div className="flex items-center justify-between gap-3">
                            <div className="text-xs text-boxwood/85 leading-snug">
                                <div className="font-bold text-amber-200 flex items-center gap-1.5">
                                    <Cpu size={14} className="text-amber-400"/> {t('viewer.engineTitle')}
                                </div>
                                <div className="text-boxwood/65 mt-0.5">
                                    {t('viewer.engineSubtitle')}
                                </div>
                            </div>
                            <button
                                type="button"
                                disabled={isAnalyzing || history.length === 0}
                                onClick={handleRunFullAnalysis}
                                className="px-3.5 py-2 rounded-md bg-boxwood hover:bg-boxwood-light disabled:opacity-50 text-acacia-dark font-bold text-xs flex items-center gap-1.5 shrink-0 shadow cursor-pointer transition"
                            >
                                {isAnalyzing ? <Loader2 size={15} className="animate-spin"/> : <Sparkles size={15}/>}
                                {t(isAnalyzing ? 'viewer.analyzing' : 'viewer.runAnalysis')}
                            </button>
                        </div>
                    ) : (
                        <>
                            {analysisReport.summary && isSummaryKind(analysisReport.summary.kind) && (
                                <div className="text-xs p-2 rounded bg-black/40 border border-amber-900/40" data-testid="viewer-summary">
                                    <span className="font-bold text-amber-200">
                                        {t(`summary.kinds.${analysisReport.summary.kind}.name`)}
                                    </span>
                                    {' — '}
                                    <span className="text-boxwood/80">{t(`summary.kinds.${analysisReport.summary.kind}.text`)}</span>
                                </div>
                            )}
                            <CriticalMoments report={analysisReport} viewIndex={viewIndex} onSelect={setViewIndex}/>
                            <div className="grid grid-cols-2 gap-2 text-xs">
                                <SideStatsCard symbol="♔" name={whiteName} stats={analysisReport.white} side="white"/>
                                <SideStatsCard symbol="♚" name={blackName} stats={analysisReport.black} side="black"/>
                            </div>

                            <EvalChart data={chartData} onSelect={(idx) => {
                                if (idx === viewIndex) return;
                                setViewIndex(idx);
                                const san = analysisReport?.moves[idx]?.san;
                                playAudio(san ? resolveMoveSound(san) : 'move');
                            }}/>
                        </>
                    )}

                    {analysisError && (
                        <div
                            className="text-xs text-rose-300 bg-rose-950/60 border border-rose-700/50 rounded px-2.5 py-1.5">
                            {renderUiMessage(analysisError, t)}
                        </div>
                    )}

                    <XrayPanel settings={xray} canSelect={false}/>

                    {currentCoachText && (
                        <CoachCommentBox text={currentCoachText} hasArrows={coachArrows(currentCoach).length > 0}
                                         showArrows={showCoachArrows} onShowArrowsChange={setShowCoachArrows}/>
                    )}
                </div>

                <MoveList pairs={movePairs} viewIndex={viewIndex} moves={analysisReport?.moves} personalPlies={personalPlies}
                          scrollRef={notationScrollRef} onSelect={(index, san) => {
                              setViewIndex(index);
                              playAudio(resolveMoveSound(san));
                          }}/>

                <div className="flex flex-col gap-2 shrink-0">
                    <NavigationControls viewIndex={viewIndex} total={history.length} onFlip={() => setIsFlipped(!isFlipped)}
                                        onGo={(index) => {
                                            setViewIndex(index);
                                            playAudio(index >= 0 ? resolveMoveSound(history[index].san) : 'move');
                                        }}/>

                    {!library && !imported && !startFen && gameId && <RepertoireDeviations gameId={gameId}/>}
                    {!startFen && (
                        <button type="button" onClick={() => setShowExplorer((v) => !v)} aria-expanded={showExplorer}
                                data-testid="explorer-toggle"
                                className="flex items-center justify-center gap-2 w-full px-4 py-2 bg-room-dark text-amber-300 font-bold text-sm rounded-md hover:bg-black transition shadow border border-amber-800/60">
                            {t('explorer.title')}
                        </button>
                    )}
                    {showExplorer && !startFen && (
                        <>
                            <OpeningExplorer moves={history.slice(0, viewIndex + 1).map((m) => `${m.from}${m.to}${m.promotion ?? ''}`)}/>
                            {viewIndex >= 0 && (
                                <AddToRepertoire moves={history.slice(0, Math.min(viewIndex + 1, 40)).map((m) => `${m.from}${m.to}${m.promotion ?? ''}`)}/>
                            )}
                        </>
                    )}
                    {analysisReport && history.length > 0 && (
                        <button type="button" data-testid="download-annotated"
                                onClick={() => downloadText(`regence-${gameId}-annotated.pgn`, buildPgn({
                                    headers: pgnHeaders, startFen, result: pgnHeaders.Result,
                                    moves: annotatedMoves(history, analysisReport, (coach) => coachText(coach, t)),
                                }))}
                                className="flex items-center justify-center gap-2 w-full px-4 py-2 bg-room-dark text-amber-400 font-bold text-sm rounded-md hover:bg-black transition shadow border border-amber-800/60">
                            <Download size={16}/> {t('tools.exportAnnotated')}
                        </button>
                    )}
                    {guessFirstId !== null && (
                        <Link to={`/guess/${guessFirstId}?whole=1`} data-testid="guess-from-game"
                              className="flex items-center justify-center gap-2 w-full px-4 py-2 bg-amber-800 text-white font-bold text-sm rounded-md hover:bg-amber-700 transition shadow border border-amber-500/60">
                            <Crown size={16}/> {t('guess.openFromGame')}
                        </Link>
                    )}
                    <a
                        href={pgnUrl}
                        download
                        className="flex items-center justify-center gap-2 w-full px-4 py-2 bg-room-dark text-amber-400 font-bold text-sm rounded-md hover:bg-black transition shadow border border-amber-800/60"
                    >
                        <Download size={16}/> {t('viewer.downloadPgnFile')}
                    </a>
                    {/* Share to the feed (task 30.2): one's own or someone else's portal game, a library game; imported ones are private. */}
                    {!imported && gameId && getToken() && !kidMode && (
                        <Link to="/feed" state={{attach: {kind: library ? 'library' : 'game', ref: gameId}}} data-testid="share-to-feed"
                              className="flex items-center justify-center gap-2 w-full px-4 py-2 bg-room-dark text-amber-400 font-bold text-sm rounded-md hover:bg-black transition shadow border border-amber-800/60">
                            <Share2 size={16}/> {t('feed.share')}
                        </Link>
                    )}
                </div>

            </div>
        </div>
    );
}