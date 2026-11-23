// --- FILE: frontend/src/components/trainers/MiniGameRoom.tsx ---
// A coach game with a human over the network (task 19.8): /train/games/room/:code - a room for two. The creator sends
// the link, the second player joins by it; moves by clicks "from" - "to", as in the game with a bot. The page learns about the opponent's
// move by polling the room every POLL_MS; after the end - "Again" (a new room, colours swap), and the
// opponent's page goes there by itself (next). Rules and state - on the server (services/miniGameRooms.ts).
// Wired in App.tsx.

import {useCallback, useEffect, useState} from 'react';
import {Link, useNavigate, useParams} from 'react-router-dom';
import {ArrowLeft, Copy, Flag, RotateCcw, Users} from 'lucide-react';
import {renderUiMessage, useI18n} from '../../i18n';
import type {UiMessage} from '../../i18n';
import {errorMessage} from '../../services/apiErrors';
import {getToken} from '../../services/authToken';
import {miniRoomsApi, roomLink} from '../../services/miniGameRooms';
import type {MiniRoom} from '../../services/miniGameRooms';
import {PuzzleBoard} from '../puzzles/PuzzleBoard';
import type {MiniGameId} from './MiniGames';
import {Button} from '../ui';

/** Room polling period (ms): this is how the page learns about the opponent's move, there is no separate channel for rooms. */
export const POLL_MS = 1000;

/** Room: a move goes with the version number (room.version) - the server rejects a stale move; the player's side is determined by room.you (null - not a participant: one can join a waiting room, otherwise only watch). */
export function MiniGameRoomPage() {
    const {t} = useI18n();
    const navigate = useNavigate();
    const {code = ''} = useParams<{ code: string }>();
    const [room, setRoom] = useState<MiniRoom | null>(null);
    const [from, setFrom] = useState<string | null>(null);
    const [error, setError] = useState<UiMessage | null>(null);
    const [copied, setCopied] = useState(false);
    const loggedIn = Boolean(getToken());

    // A "again" room (next) or a new room from the "Again" response - go there; otherwise - show.
    const show = useCallback((next: MiniRoom) => {
        const target = next.next ?? (next.code !== code ? next.code : null);
        if (target) {
            navigate(`/train/games/room/${target}`, {replace: true});
            return;
        }
        setRoom(next);
    }, [navigate, code]);

    useEffect(() => {
        setRoom(null);
        let alive = true;
        const load = () => miniRoomsApi.get(code).then((r) => alive && show(r))
            .catch((err) => alive && setError(errorMessage(err, 'common.networkError')));
        void load();
        const timer = window.setInterval(load, POLL_MS);
        return () => {
            alive = false;
            window.clearInterval(timer);
        };
    }, [code, show]);

    if (!room) return error ? <p role="alert" className="p-4 text-rose-300">{renderUiMessage(error, t)}</p> : null;

    const act = (request: Promise<MiniRoom>) => {
        setError(null);
        request.then(show).catch((err) => setError(errorMessage(err, 'common.networkError')));
    };
    // The game code from the server is one of MINI_GAMES (an unknown one the server will not create).
    const game = room.game_id as MiniGameId;
    const turn = room.fen.split(' ')[1] === 'w' ? 'white' : 'black';
    const myTurn = room.you !== null && !room.result && !room.waiting && turn === room.you;
    const lastUci = room.moves.at(-1);

    const onSquare = (square: string) => {
        if (!myTurn) return;
        if (!from || from === square) {
            setFrom(from === square ? null : square);
            return;
        }
        const move = `${from}${square}`;
        setFrom(null);
        act(miniRoomsApi.move(room.code, move, room.version));
    };

    const outcome = room.result === '1/2-1/2' ? t('miniGames.draw') : room.result
        ? t(room.result === '1-0' ? 'miniGames.whiteWins' : 'miniGames.blackWins') : null;
    const status = outcome
        ? `${outcome}${room.reason === 'resign' ? ` ${t('miniGames.room.byResignation')}` : ''}`
        : room.waiting ? t('miniGames.room.waitingOpponent')
            : room.you ? t(myTurn ? 'miniGames.room.yourMove' : 'miniGames.room.opponentMove')
                : t(turn === 'white' ? 'miniGames.whiteToMove' : 'miniGames.blackToMove');

    const copy = () => {
        void navigator.clipboard?.writeText(roomLink(room.code)).then(() => setCopied(true)).catch(() => undefined);
    };

    return (
        <div className="w-full max-w-5xl mx-auto p-3 flex flex-col gap-3 text-boxwood-light" data-testid="mini-room">
            <Link to={`/train/games/${room.game_id}`} className="text-sm text-amber-400 hover:underline flex items-center gap-1">
                <ArrowLeft size={14}/> {t(`miniGames.games.${game}.title`)}
            </Link>
            <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h1 className="text-2xl font-bold text-amber-200 flex items-center gap-2"><Users size={20}/> {t('miniGames.room.title')}</h1>
                <span className="text-sm" data-testid="mini-room-players">
                    {room.white ?? '…'} — {room.black ?? '…'}
                </span>
            </header>
            <p className="text-sm text-boxwood/80">{t(`miniGames.games.${game}.rules`)}</p>

            {room.waiting && room.you && (
                <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="mini-room-invite">
                    <span>{t('miniGames.room.invite')}</span>
                    <input readOnly value={roomLink(room.code)} className="bg-black/40 rounded px-2 py-1 font-mono text-xs flex-1 min-w-0"
                           onFocus={(e) => e.target.select()}/>
                    <Button size="sm" icon={<Copy size={14}/>} onClick={copy}>{t(copied ? 'miniGames.room.copied' : 'miniGames.room.copy')}</Button>
                </div>
            )}
            {room.waiting && !room.you && (loggedIn ? (
                <Button variant="primary" className="self-start" onClick={() => act(miniRoomsApi.join(room.code))}
                        data-testid="mini-room-join">{t('miniGames.room.join')}</Button>
            ) : <p className="text-sm">{t('miniGames.room.loginToJoin')}</p>)}

            <p className="font-bold" data-testid="mini-room-status" aria-live="polite">{status}</p>
            {error && <p role="alert" className="text-sm text-rose-300">{renderUiMessage(error, t)}</p>}
            <div className="w-full max-w-[480px]">
                <PuzzleBoard fen={room.fen} orientation={room.you === 'black' ? 'black' : 'white'} interactive={myTurn}
                             onMove={() => undefined} onSquare={onSquare} highlights={from ? [from] : []}
                             lastMove={lastUci ? {from: lastUci.slice(0, 2), to: lastUci.slice(2, 4)} : null}/>
            </div>
            {room.you && (
                <div className="flex flex-wrap gap-2">
                    {!room.result && !room.waiting && (
                        <Button size="sm" icon={<Flag size={14}/>} onClick={() => act(miniRoomsApi.resign(room.code))}
                                data-testid="mini-room-resign">{t('miniGames.room.resign')}</Button>
                    )}
                    {room.result && (
                        <Button variant="primary" size="sm" icon={<RotateCcw size={14}/>}
                                onClick={() => act(miniRoomsApi.rematch(room.code))} data-testid="mini-room-rematch">
                            {t('miniGames.room.rematch')}
                        </Button>
                    )}
                </div>
            )}
        </div>
    );
}
