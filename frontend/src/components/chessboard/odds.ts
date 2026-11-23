// --- FILE: frontend/src/components/chessboard/odds.ts ---
// Games with odds (task 21.1): ready odds for a game with a bot and with a person by link. Material odds - the starting
// position without a piece of the odds giver (queen's knight or rook, queen, f-pawn; castling with the removed rook
// is lost); time odds - the giver has a third of the time; "hourglass" - the time spent by one is added to
// the other. The game starts from a position (task 9.6) and does not change the rating. In a game with a bot the client builds the position and clocks
// (useBotGame); in a game with a person the client only passes the odds kind and who gives it (inviteOddsFields), while the position,
// time and the "hourglass" move are computed by the server (src/services/odds.py, game_state.py), the client only shows them.

/** Odds kinds (with a bot and with a person); labels - catalog odds.kinds.*. */
export const ODDS = ['none', 'knight', 'rook', 'queen', 'pawn', 'time', 'tempo', 'hourglass'] as const;
export type OddsKind = typeof ODDS[number];
export type OddsGiver = 'me' | 'opponent';

/** The player's choice: odds kind and who gives it (for "hourglass" there is no giver - it is common). */
export interface OddsChoice {
    kind: OddsKind;
    giver: OddsGiver;
}

// "Two moves in a row": the rules have no pass, so the position where the receiver has already played e4+d4 (e5+d5);
// the key is the giver's colour (src/services/odds.py, TEMPO_FEN).
const TEMPO_FEN = {
    white: 'rnbqkbnr/ppp2ppp/8/3pp3/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    black: 'rnbqkbnr/pppppppp/8/8/3PP3/8/PPP2PPP/RNBQKBNR b KQkq - 0 1',
} as const;
const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
// The square of the removed piece: [white, black].
const REMOVED: Partial<Record<OddsKind, [string, string]>> = {
    knight: ['b1', 'b8'],
    rook: ['a1', 'a8'],
    queen: ['d1', 'd8'],
    pawn: ['f2', 'f7'],
};

/** Starting position with material odds; null - the odds are not material. */
export function oddsFen(kind: OddsKind, giver: 'white' | 'black'): string | null {
    if (kind === 'tempo') return TEMPO_FEN[giver];
    const squares = REMOVED[kind];
    if (!squares) return null;
    const square = squares[giver === 'white' ? 0 : 1];
    const [placement, , , ...rest] = START.split(' ');
    const rows = placement.split('/').map((row) => row.replace(/\d/g, (n) => '1'.repeat(Number(n))).split(''));
    const file = square.charCodeAt(0) - 97;
    const rank = Number(square[1]);
    rows[8 - rank][file] = '1';
    const packed = rows.map((row) => row.join('').replace(/1+/g, (ones) => String(ones.length))).join('/');
    let castling = 'KQkq';
    if (kind === 'rook') castling = castling.replace(giver === 'white' ? 'Q' : 'q', '');
    return [packed, 'w', castling || '-', ...rest].join(' ');
}

/** Starting time of the sides with time odds: the giver has a third (at least a minute). */
export function oddsTimes(kind: OddsKind, giver: 'white' | 'black', whiteMs: number, blackMs: number): { white: number; black: number } {
    if (kind !== 'time') return {white: whiteMs, black: blackMs};
    const cut = (ms: number) => Math.max(60_000, Math.round(ms / 3));
    return giver === 'white' ? {white: cut(whiteMs), black: blackMs} : {white: whiteMs, black: cut(blackMs)};
}

/** Whether the odds have a giver: none for "no odds" and for "hourglass" (common) - the "who gives" choice is not shown. */
export function hasGiver(kind: OddsKind): boolean {
    return kind !== 'none' && kind !== 'hourglass';
}

/**
 * Invitation fields for the server (WebSocket action create_invite): giver "me" - the link creator gives the odds.
 * An empty odds_kind - no odds.
 */
export function inviteOddsFields(odds: OddsChoice): { odds_kind: string; odds_giver: 'creator' | 'acceptor' } {
    return {odds_kind: odds.kind === 'none' ? '' : odds.kind,
        odds_giver: odds.giver === 'me' ? 'creator' : 'acceptor'};
}

/** Who gives the odds by colour: "me" - my colour, "opponent" - the opposite one. */
export function giverColor(giver: OddsGiver, myColor: 'white' | 'black'): 'white' | 'black' {
    if (giver === 'me') return myColor;
    return myColor === 'white' ? 'black' : 'white';
}
