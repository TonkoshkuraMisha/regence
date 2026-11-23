// // Fischer Random game against a human (task 21.3 / 21.1): /play/960/live. The 960 rules live only on the server (python-chess in
// 960, src/services/game_engine.py): // 960 mode, src/services/game_engine.py): the client chess library does not know 960 castling, so here the board only
// // draws the position and relays clicks, as in the game against a bot (Chess960Page). Castling is a click on the king, then on
// // one's own rook; a premove is placed the same way on the opponent's turn (it is sent as soon as it is our turn; the server rejects an impossible one).
// // State arrives over the shared WebSocket (services/gameSocket): match_found (at start and on every
// // reconnect), move_made, game_over, chat, draw and rematch offers (a rematch is the same setup with colours swapped,
// websockets.create_rematch_game). // websockets.create_rematch_game). The main board (useGameSocket.ts) itself redirects here
// // a game with variant chess960, passing the snapshot in location.state.match. These games are unrated.

import {useCallback, useEffect, useRef, useState} from 'react';
import {Link, useLocation} from 'react-router-dom';
import {ArrowLeft, Flag, Handshake, Shuffle, X} from 'lucide-react';
import {renderUiMessage, useI18n} from '../../i18n';
import {getToken} from '../../services/authToken';
import {GameChatPanel} from '../chessboard/GameChatPanel';
import {useGameChat} from '../chessboard/gameChat';
import {gameSocket} from '../../services/gameSocket';
import {describeGameOver} from '../chessboard/status';
import {PuzzleBoard} from '../puzzles/PuzzleBoard';
import {clickStep} from './Chess960Page';
import {numberedMoves} from '../../services/moveNumbers';

// // Game snapshot for rendering: clocks (ms) are values as of the last server message; the state version is needed for make_move.
interface LiveState {
    gameId: number;
    color: 'white' | 'black';
    white: string;
    black: string;
    whiteRating: number;
    blackRating: number;
    fen: string;
    pgn: string;
    version: number;
    whiteMs: number;
    blackMs: number;
    lastMove: string | null;
}

/** /** Position for a board without castling rights: the board draws pieces, the server validates 960 castling. */
export function displayFen(fen: string): string {
    const parts = fen.split(' ');
    if (parts.length > 2) parts[2] = '-';
    return parts.join(' ');
}

/** /** Game moves in SAN from the PGN: without headers, move numbers and result. */
export function sansOf(pgn: string): string[] {
    const movetext = pgn.split('\n').filter((line) => !line.startsWith('[')).join(' ');
    return movetext.split(/\s+/).filter((token) => token && !/^\d+\.(\.\.)?$/.test(token) && !/^\d+\.{1,3}\S/.test(token)
        && !['1-0', '0-1', '1/2-1/2', '*'].includes(token));
}

/**
 *  * Socket message about the game (match_found, move_made, game_over, draw_offered, draw_declined, rematch_offered,
 * rematch_declined — src/api/websockets.py):
 *  * server fields in snake_case; each message carries only its own, so all are optional.
 */
interface GameMessage {
    game_id?: number | string;
    variant?: string;
    color?: string;
    white_username?: string;
    black_username?: string;
    white_rating?: number;
    black_rating?: number;
    fen?: string;
    pgn?: string;
    state_version?: number;
    white_time_ms?: number;
    black_time_ms?: number;
    base_time_ms?: number;
    draw_offer_from?: number | null;
    opponent_id?: number;
    move?: string | null;
    result?: string;
    reason?: string;
}

/** /** Game snapshot from a match_found message (server snake_case fields -> component state). */
function fromSnapshot(data: GameMessage): LiveState {
    return {
        gameId: Number(data.game_id),
        color: data.color === 'black' ? 'black' : 'white',
        white: data.white_username || '',
        black: data.black_username || '',
        whiteRating: Number(data.white_rating || 0),
        blackRating: Number(data.black_rating || 0),
        fen: data.fen || '',
        pgn: data.pgn || '',
        version: Number(data.state_version || 0),
        whiteMs: Number(data.white_time_ms ?? data.base_time_ms ?? 0),
        blackMs: Number(data.black_time_ms ?? data.base_time_ms ?? 0),
        lastMove: null,
    };
}

// // Time "m:ss" rounded up to the second, as on the main board.
function clock(ms: number): string {
    const total = Math.max(0, Math.ceil(ms / 1000));
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

// // Unique move command identifier: the server uses it to drop a repeated submission of the same move.
function commandId(): string {
    return typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

/**
 *  * Human game page: subscribes to game WebSocket events, counts the clocks locally between server messages
 *  * (the difference from updatedAt) and sends moves with the make_move command. Without a game snapshot it shows a link to the lobby.
 */
export function Chess960LiveGame() {
    const {t} = useI18n();
    const location = useLocation();
    const initial = (location.state as { match?: GameMessage } | null)?.match;
    const [game, setGame] = useState<LiveState | null>(initial?.variant === 'chess960' ? fromSnapshot(initial) : null);
    const [result, setResult] = useState<{ result: string; reason?: string } | null>(null);
    const [from, setFrom] = useState<string | null>(null);
    //     // Premove (as on the main board): a move chosen on the opponent's turn is sent to the server as soon as it is our turn.
    //     // Only the server knows the 960 rules: it rejects an impossible premove, the position does not change.
    const [premove, setPremove] = useState<string | null>(null);
    const [drawOffer, setDrawOffer] = useState<'none' | 'incoming' | 'sent' | 'declined'>(
        initial && initial.draw_offer_from !== undefined && initial.draw_offer_from !== null
            && Number(initial.draw_offer_from) === Number(initial.opponent_id) ? 'incoming' : 'none');
    //     // Rematch after the game ends: the server starts a 960 game with the same setup, colours swap (create_rematch_game).
    const [rematch, setRematch] = useState<'none' | 'sent' | 'incoming' | 'declined'>('none');
    const [now, setNow] = useState(Date.now());
    //     // Game chat is the same as on the main board (gameChat.ts, GameChatPanel); switching games clears the feed.
    const chat = useGameChat(game?.gameId ?? null);
    const updatedAt = useRef(Date.now());
    const gameRef = useRef(game);
    gameRef.current = game;

    useEffect(() => {
        const token = getToken();
        if (token) gameSocket.connect(token);
        const own = (data: GameMessage) => gameRef.current !== null && Number(data.game_id) === gameRef.current.gameId;
        const onMatch = (data: GameMessage) => {
            if (data.variant !== 'chess960') return;
            setGame(fromSnapshot(data));
            setResult(null);
            setFrom(null);
            updatedAt.current = Date.now();
            const incoming = data.draw_offer_from !== undefined && data.draw_offer_from !== null
                && Number(data.draw_offer_from) === Number(data.opponent_id);
            setDrawOffer(incoming ? 'incoming' : 'none');
            setRematch('none');
        };
        const onMove = (data: GameMessage) => {
            if (!own(data)) return;
            setGame((prev) => prev && ({
                ...prev, fen: data.fen ?? prev.fen, pgn: data.pgn ?? prev.pgn, version: Number(data.state_version ?? prev.version),
                whiteMs: Number(data.white_time_ms ?? prev.whiteMs), blackMs: Number(data.black_time_ms ?? prev.blackMs),
                lastMove: data.move || null,
            }));
            updatedAt.current = Date.now();
            setDrawOffer((prev) => (prev === 'incoming' ? prev : 'none'));
        };
        const onOver = (data: GameMessage) => {
            if (!own(data)) return;
            setResult({result: data.result ?? '*', reason: data.reason});
            setGame((prev) => prev && ({
                ...prev, whiteMs: Number(data.white_time_ms ?? prev.whiteMs), blackMs: Number(data.black_time_ms ?? prev.blackMs),
            }));
        };
        const onDrawOffered = (data: GameMessage) => {
            if (own(data)) setDrawOffer('incoming');
        };
        const onDrawDeclined = (data: GameMessage) => {
            if (own(data)) setDrawOffer('declined');
        };
        const onRematchOffered = (data: GameMessage) => {
            if (own(data)) setRematch('incoming');
        };
        const onRematchDeclined = (data: GameMessage) => {
            if (own(data)) setRematch('declined');
        };
        gameSocket.on('match_found', onMatch);
        gameSocket.on('move_made', onMove);
        gameSocket.on('game_over', onOver);
        gameSocket.on('draw_offered', onDrawOffered);
        gameSocket.on('draw_declined', onDrawDeclined);
        gameSocket.on('rematch_offered', onRematchOffered);
        gameSocket.on('rematch_declined', onRematchDeclined);
        return () => {
            gameSocket.off('match_found', onMatch);
            gameSocket.off('move_made', onMove);
            gameSocket.off('game_over', onOver);
            gameSocket.off('draw_offered', onDrawOffered);
            gameSocket.off('draw_declined', onDrawDeclined);
            gameSocket.off('rematch_offered', onRematchOffered);
            gameSocket.off('rematch_declined', onRematchDeclined);
        };
    }, []);

    useEffect(() => {
        if (!game || result) return;
        const timer = setInterval(() => setNow(Date.now()), 250);
        return () => clearInterval(timer);
    }, [game, result]);

    const turn: 'white' | 'black' = game && game.fen.split(' ')[1] === 'b' ? 'black' : 'white';
    const sans = game ? sansOf(game.pgn) : [];
    const running = !!game && !result;  //     const running = !!game && !result;  // the clocks run from the start of the game, as on the server and on the main board
    const elapsed = running ? now - updatedAt.current : 0;
    const whiteMs = game ? game.whiteMs - (turn === 'white' ? elapsed : 0) : 0;
    const blackMs = game ? game.blackMs - (turn === 'black' ? elapsed : 0) : 0;
    const myTurn = !!game && !result && turn === game.color;

    const send = useCallback((move: string, isPremove = false) => {
        const current = gameRef.current;
        if (!current) return;
        gameSocket.send('make_move', {
            game_id: current.gameId, move, command_id: commandId(), state_version: current.version,
            time_taken_ms: Date.now() - updatedAt.current, window_blurred: document.hidden, is_premove: isPremove,
        });
    }, []);

    //     // It became our turn: send the premove (once); the end of the game or a new game cancels it.
    useEffect(() => {
        if (!premove) return;
        if (result || !game) {
            setPremove(null);
            return;
        }
        if (!myTurn) return;
        send(premove, true);
        setPremove(null);
    }, [myTurn, result, game?.gameId]); // eslint-disable-line react-hooks/exhaustive-deps

    const onSquare = (square: string) => {
        if (!game || result) return;
        const step = clickStep(game.fen, game.color, from, square);
        setFrom(step.from);
        if (!step.move) return;
        if (myTurn) send(step.move);
        else setPremove(step.move);
    };

    const action = (name: string) => game && gameSocket.send(name, {game_id: game.gameId});

    if (!game) {
        return (
            <div className="w-full max-w-3xl mx-auto p-3 flex flex-col gap-3 text-boxwood-light" data-testid="c960-live-empty">
                <h1 className="text-2xl font-bold text-amber-200 flex items-center gap-2"><Shuffle className="text-amber-400"/> {t('chess960.live.title')}</h1>
                <p>{t('chess960.live.noGame')}</p>
                <div className="flex flex-wrap gap-3 text-sm">
                    <Link to="/" className="text-amber-400 hover:underline">{t('chess960.live.toLobby')}</Link>
                    <Link to="/play/960" className="text-amber-400 hover:underline">{t('chess960.live.vsBot')}</Link>
                </div>
            </div>
        );
    }

    const over = result ? describeGameOver(result.result, result.reason) : null;
    const opponent = game.color === 'white' ? {name: game.black, rating: game.blackRating, ms: blackMs}
        : {name: game.white, rating: game.whiteRating, ms: whiteMs};
    const me = game.color === 'white' ? {name: game.white, rating: game.whiteRating, ms: whiteMs}
        : {name: game.black, rating: game.blackRating, ms: blackMs};
    const bar = (side: { name: string; rating: number; ms: number }, active: boolean, testId: string) => (
        <div className="flex items-center justify-between text-sm px-1" data-testid={testId}>
            <span className="font-bold">{side.name}{side.rating ? ` (${side.rating})` : ''}</span>
            <span className={`font-mono px-2 py-0.5 rounded ${active ? 'bg-amber-700 text-white' : 'bg-black/40'}`}>{clock(side.ms)}</span>
        </div>
    );
    const status = over ? renderUiMessage(over, t)
        : t(myTurn ? 'chess960.live.yourMove' : 'chess960.live.opponentMove');

    return (
        <div className="w-full max-w-5xl mx-auto p-3 flex flex-col gap-3 text-boxwood-light" data-testid="c960-live">
            <Link to="/" className="text-sm text-amber-400 hover:underline flex items-center gap-1"><ArrowLeft size={14}/> {t('chess960.live.toLobby')}</Link>
            <h1 className="text-2xl font-bold text-amber-200 flex items-center gap-2"><Shuffle className="text-amber-400"/> {t('chess960.live.title')}</h1>
            <div className="flex flex-col lg:flex-row gap-5 items-start">
                <div className="w-full max-w-[480px] flex flex-col gap-1.5">
                    {bar(opponent, !result && turn !== game.color, 'c960-live-opponent')}
                    <PuzzleBoard fen={displayFen(game.fen)} orientation={game.color} interactive={!result} onMove={() => undefined}
                                 onSquare={onSquare} highlights={from ? [from] : premove ? [premove.slice(0, 2), premove.slice(2, 4)] : []}
                                 lastMove={game.lastMove ? {from: game.lastMove.slice(0, 2), to: game.lastMove.slice(2, 4)} : null}/>
                    {bar(me, !result && turn === game.color, 'c960-live-me')}
                </div>
                <div className="flex-1 min-w-0 flex flex-col gap-2 text-sm">
                    <p className="font-bold" data-testid="c960-live-status">{status}</p>
                    <p className="text-xs text-boxwood/70">{t('chess960.castlingHint')} {t('chess960.live.unrated')}</p>
                    {sans.length > 0 && (
                        <p className="font-mono text-xs break-words" data-testid="c960-live-moves">
                            {numberedMoves(sans).join(' ')}
                        </p>
                    )}
                    {!result && premove && (
                        <p className="text-xs text-sky-300 flex items-center gap-2" data-testid="c960-live-premove">
                            {t('chess960.live.premoveSet', {move: `${premove.slice(0, 2)}–${premove.slice(2, 4)}`})}
                            <button type="button" onClick={() => setPremove(null)} className="underline" data-testid="c960-live-premove-cancel">
                                {t('chess960.live.cancelPremove')}
                            </button>
                        </p>
                    )}
                    {!result && drawOffer === 'incoming' && (
                        <div className="flex flex-wrap items-center gap-2" data-testid="c960-live-draw-offer">
                            <span>{t('chess960.live.drawOffered')}</span>
                            <button type="button" onClick={() => { action('accept_draw'); setDrawOffer('none'); }}
                                    className="px-2 py-1 rounded bg-emerald-800 text-white text-xs font-bold">{t('chess960.live.acceptDraw')}</button>
                            <button type="button" onClick={() => { action('decline_draw'); setDrawOffer('none'); }}
                                    className="px-2 py-1 rounded bg-black/40 border border-amber-900/50 text-xs">{t('chess960.live.declineDraw')}</button>
                        </div>
                    )}
                    {!result && drawOffer === 'sent' && <p className="text-xs text-amber-200">{t('chess960.live.drawSent')}</p>}
                    {!result && drawOffer === 'declined' && <p className="text-xs text-amber-200">{t('chess960.live.drawDeclined')}</p>}
                    {!result && (
                        <div className="flex flex-wrap gap-2">
                            {sans.length < 2 ? (
                                <button type="button" onClick={() => action('abort_game')} data-testid="c960-live-abort"
                                        className="flex items-center gap-1 px-3 py-1.5 rounded bg-black/40 border border-amber-900/50 hover:border-amber-500">
                                    <X size={14}/> {t('chess960.live.abort')}
                                </button>
                            ) : (
                                <>
                                    <button type="button" data-testid="c960-live-draw" disabled={drawOffer !== 'none' && drawOffer !== 'declined'}
                                            onClick={() => { action('offer_draw'); setDrawOffer('sent'); }}
                                            className="flex items-center gap-1 px-3 py-1.5 rounded bg-black/40 border border-amber-900/50 hover:border-amber-500 disabled:opacity-40">
                                        <Handshake size={14}/> {t('chess960.live.offerDraw')}
                                    </button>
                                    <button type="button" data-testid="c960-live-resign"
                                            onClick={() => { if (window.confirm(t('chess960.live.resignConfirm'))) action('resign'); }}
                                            className="flex items-center gap-1 px-3 py-1.5 rounded bg-black/40 border border-rose-900/60 hover:border-rose-500">
                                        <Flag size={14}/> {t('chess960.live.resign')}
                                    </button>
                                </>
                            )}
                        </div>
                    )}
                    {result && rematch === 'incoming' && (
                        <div className="flex flex-wrap items-center gap-2" data-testid="c960-live-rematch-offer">
                            <span>{t('chess960.live.rematchOffered')}</span>
                            <button type="button" onClick={() => { action('accept_rematch'); setRematch('none'); }} data-testid="c960-live-rematch-accept"
                                    className="px-2 py-1 rounded bg-emerald-800 text-white text-xs font-bold">{t('chess960.live.acceptDraw')}</button>
                            <button type="button" onClick={() => { action('decline_rematch'); setRematch('none'); }}
                                    className="px-2 py-1 rounded bg-black/40 border border-amber-900/50 text-xs">{t('chess960.live.declineDraw')}</button>
                        </div>
                    )}
                    {result && rematch === 'sent' && <p className="text-xs text-amber-200" data-testid="c960-live-rematch-sent">{t('chess960.live.rematchSent')}</p>}
                    {result && rematch === 'declined' && <p className="text-xs text-amber-200">{t('chess960.live.rematchDeclined')}</p>}
                    {result && (
                        <div className="flex flex-wrap gap-2">
                            {rematch !== 'incoming' && (
                                <button type="button" data-testid="c960-live-rematch" disabled={rematch === 'sent'}
                                        onClick={() => { action('offer_rematch'); setRematch('sent'); }}
                                        className="flex items-center gap-1 px-3 py-1.5 rounded bg-black/40 border border-amber-900/50 hover:border-amber-500 disabled:opacity-40">
                                    <Shuffle size={14}/> {t('chess960.live.rematch')}
                                </button>
                            )}
                            <Link to="/" className="px-3 py-1.5 rounded bg-amber-700 text-white font-bold" data-testid="c960-live-again">
                                {t('chess960.live.again')}
                            </Link>
                        </div>
                    )}
                    <GameChatPanel messages={chat.messages} chatInput={chat.input} onChatInputChange={chat.setInput}
                                   onSendMessage={chat.send} onSendPreset={chat.sendPreset} isSpectator={false}
                                   onLeaveSpectate={() => undefined} myName={game.color === 'white' ? game.white : game.black}
                                   gameId={game.gameId}/>
                </div>
            </div>
        </div>
    );
}
