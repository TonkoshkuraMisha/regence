// // Fischer Random chess (task 21.3): /play/960 is a game against a bot from a random setup (or by number 0-959).
// // Rules and the bot's move are on the server (python-chess in 960 mode, Stockfish with UCI_Chess960, src/services/chess960.py):
// // the client chess library does not know the 960 rules, so the board only draws the position and relays clicks.
// // Castling is a click on the king, then on one's own rook. No rating. Data comes from /api/v1/chess960 (src/api/chess960.py):
// // the position and moves are sent in full each time (the server keeps no game state). Route is in App.tsx; the pure functions
// piecesOf/clickMove // piecesOf/clickMove are shared with the human game (Chess960LiveGame.tsx).

import {useCallback, useEffect, useState} from 'react';
import {Link} from 'react-router-dom';
import {ArrowLeft, Shuffle} from 'lucide-react';
import {renderUiMessage, useI18n} from '../../i18n';
import type {UiMessage} from '../../i18n';
import {errorMessage} from '../../services/apiErrors';
import {chess960Call} from '../../services/chess960';
import type {State960} from '../../services/chess960';
import {PuzzleBoard} from '../puzzles/PuzzleBoard';
import {numberedMoves} from '../../services/moveNumbers';

/** /** Server response for a game against a bot: setup number, position, moves (UCI and SAN), result and the bot's move. */
// // Bot levels 1-5 (the server maps each to an Elo and a time per move, chess960.LEVELS); names come from the chess960.levels catalog.
// // Termination reasons that have texts in the chess960.terminations catalog.
const LEVELS = [1, 2, 3, 4, 5] as const;
const TERMINATIONS = ['checkmate', 'stalemate', 'insufficient_material', 'threefold_repetition', 'fifty_moves',
    'fivefold_repetition', 'seventyfive_moves'] as const;

// // Requests to the server are in services/chess960.ts; the state type is re-exported for tests and the human game.
const call = chess960Call;
export type {State960};

/** /** Pieces of a position by square: "e1" -> "K" (white ones are uppercase). */
export function piecesOf(fen: string): Map<string, string> {
    const pieces = new Map<string, string>();
    fen.split(' ')[0].split('/').forEach((row, index) => {
        let file = 0;
        for (const char of row) {
            if (/\d/.test(char)) {
                file += Number(char);
                continue;
            }
            pieces.set(`${'abcdefgh'[file]}${8 - index}`, char);
            file += 1;
        }
    });
    return pieces;
}

/** /** Move by two clicks: king onto own rook is castling (UCI 960), pawn onto the last rank is a queen. */
export function clickMove(fen: string, from: string, to: string): string | null {
    const pieces = piecesOf(fen);
    const mover = pieces.get(from);
    const target = pieces.get(to);
    if (!mover) return null;
    const white = mover === mover.toUpperCase();
    const own = target !== undefined && (target === target.toUpperCase()) === white;
    if (own && !(mover.toLowerCase() === 'k' && target!.toLowerCase() === 'r')) return null;
    const promotion = mover.toLowerCase() === 'p' && (to[1] === '8' || to[1] === '1') ? 'q' : '';
    return `${from}${to}${promotion}`;
}

/** /** Outcome of a click on a square in two-click moves: the new selected square and the ready UCI move (null means no move yet). */
export interface ClickStep {
    from: string | null;
    move: string | null;
}

/**
 *  * Click on a square when color is to move: the first click selects one's own piece, a second click on it clears the selection,
 *  * a click on another square is a move (clickMove); an impossible move moves the selection to one's own piece or clears it.
 */
export function clickStep(fen: string, color: 'white' | 'black', from: string | null, square: string): ClickStep {
    const piece = piecesOf(fen).get(square);
    const mine = piece !== undefined && (piece === piece.toUpperCase()) === (color === 'white');
    if (!from) return {from: mine ? square : null, move: null};
    if (from === square) return {from: null, move: null};
    const move = clickMove(fen, from, square);
    if (move === null) return {from: mine ? square : null, move: null};
    return {from: null, move};
}

/**
 *  * Game page against a bot. Start and "New game" go through start(): when playing black the bot's move is requested immediately.
 *  * The player's move is assembled from two clicks (onSquare -> clickMove) and goes to the server together with all the game's moves.
 */
export function Chess960Page() {
    const {t} = useI18n();
    const [color, setColor] = useState<'white' | 'black'>('white');
    //     // Side of the current game: a choice in the list applies to the next new game.
    const [side, setSide] = useState<'white' | 'black'>('white');
    const [level, setLevel] = useState(2);
    const [numberText, setNumberText] = useState('');
    const [state, setState] = useState<State960 | null>(null);
    const [from, setFrom] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<UiMessage | null>(null);

    const run = useCallback(async (action: () => Promise<State960>) => {
        setBusy(true);
        setError(null);
        try {
            setState(await action());
        } catch (err) {
            setError(errorMessage(err, 'common.networkError'));
        } finally {
            setBusy(false);
        }
    }, []);

    const start = useCallback((mySide: 'white' | 'black', lvl: number, wanted: string) => {
        setFrom(null);
        setSide(mySide);
        const number = wanted.trim() === '' ? '' : `?number=${Number(wanted)}`;
        void run(async () => {
            const fresh = await call(`/new${number}`);
            return mySide === 'black' ? call('/bot-move', {number: fresh.number, moves: [], level: lvl}) : fresh;
        });
    }, [run]);
    useEffect(() => start('white', 2, ''), [start]);

    const turn = state ? (state.fen.split(' ')[1] === 'w' ? 'white' : 'black') : 'white';
    const myTurn = !!state && !state.result && !busy && turn === side;

    const onSquare = (square: string) => {
        if (!state || !myTurn) return;
        const step = clickStep(state.fen, side, from, square);
        setFrom(step.from);
        const move = step.move;
        if (move) void run(() => call('/move', {number: state.number, moves: state.moves, move, level}));
    };

    const last = state && state.moves.length ? state.moves[state.moves.length - 1] : null;
    const termination = state?.termination && (TERMINATIONS as readonly string[]).includes(state.termination)
        ? state.termination as typeof TERMINATIONS[number] : null;
    const status = !state ? t('chess960.loading')
        : state.result ? t(state.result === '1/2-1/2' ? 'chess960.draw' : state.result === '1-0' ? 'chess960.whiteWins' : 'chess960.blackWins',
            {reason: termination ? t(`chess960.terminations.${termination}`) : ''})
            : busy ? t('chess960.thinking') : t(myTurn ? 'chess960.yourMove' : 'chess960.botMove');

    return (
        <div className="w-full max-w-5xl mx-auto p-3 flex flex-col gap-4 text-boxwood-light" data-testid="chess960-page">
            <Link to="/train" className="text-sm text-amber-400 hover:underline flex items-center gap-1"><ArrowLeft size={14}/> {t('trainers.title')}</Link>
            <header className="flex items-center gap-2">
                <Shuffle className="text-amber-400"/>
                <h1 className="text-2xl font-bold text-amber-200">{t('chess960.title')}</h1>
            </header>
            <p className="text-boxwood/85">{t('chess960.intro')}</p>

            <div className="flex flex-wrap items-end gap-3 text-sm bg-black/30 rounded-lg p-3">
                <label className="flex flex-col gap-1">{t('chess960.color')}
                    <select value={color} onChange={(e) => setColor(e.target.value as 'white' | 'black')} data-testid="c960-color"
                            className="bg-black/40 rounded px-2 py-1">
                        <option value="white">{t('chess960.white')}</option>
                        <option value="black">{t('chess960.black')}</option>
                    </select>
                </label>
                <label className="flex flex-col gap-1">{t('chess960.level')}
                    <select value={level} onChange={(e) => setLevel(Number(e.target.value))} data-testid="c960-level"
                            className="bg-black/40 rounded px-2 py-1">
                        {LEVELS.map((l) => <option key={l} value={l}>{t(`chess960.levels.l${l}`)}</option>)}
                    </select>
                </label>
                <label className="flex flex-col gap-1">{t('chess960.position')}
                    <input type="number" min={0} max={959} value={numberText} onChange={(e) => setNumberText(e.target.value)}
                           placeholder={t('chess960.random')} data-testid="c960-number" className="bg-black/40 rounded px-2 py-1 w-28"/>
                </label>
                <button type="button" onClick={() => start(color, level, numberText)} disabled={busy} data-testid="c960-new"
                        className="px-3 py-1.5 rounded bg-amber-700 text-white font-bold disabled:opacity-50">{t('chess960.newGame')}</button>
            </div>

            {error && <p role="alert" className="text-sm text-rose-300">{renderUiMessage(error, t)}</p>}
            <div className="flex flex-col lg:flex-row gap-5 items-start">
                <div className="w-full max-w-[480px]">
                    {state && (
                        <PuzzleBoard fen={state.fen} orientation={side} interactive onMove={() => undefined} onSquare={onSquare}
                                     highlights={from ? [from] : []}
                                     lastMove={last ? {from: last.slice(0, 2), to: last.slice(2, 4)} : null}/>
                    )}
                </div>
                <div className="flex-1 min-w-0 flex flex-col gap-2 text-sm">
                    {state && <p className="text-amber-300" data-testid="c960-number-label">{t('chess960.positionNumber', {n: state.number})}</p>}
                    <p className="font-bold" data-testid="c960-status">{status}{state?.check && !state.result ? ` ${t('chess960.check')}` : ''}</p>
                    <p className="text-xs text-boxwood/70">{t('chess960.castlingHint')}</p>
                    {state && state.sans.length > 0 && <p className="font-mono text-xs break-words" data-testid="c960-moves">{numberedMoves(state.sans).join(' ')}</p>}
                </div>
            </div>
        </div>
    );
}
