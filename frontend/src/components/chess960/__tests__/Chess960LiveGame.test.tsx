// A Fischer game with a person (21.3): moves over WebSocket, castling "king onto its own rook", a draw and the result.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {Chess960LiveGame, displayFen, sansOf} from '../Chess960LiveGame';
import {setToken} from '../../../services/authToken';

const handlers = new Map<string, (data: any) => void>();
vi.mock('../../../services/gameSocket', () => ({
    gameSocket: {
        connect: vi.fn(),
        send: vi.fn(),
        on: vi.fn((event: string, cb: (data: any) => void) => handlers.set(event, cb)),
        off: vi.fn((event: string) => handlers.delete(event)),
    },
}));
import {gameSocket} from '../../../services/gameSocket';

// The ordinary setup by the 960 rules after 1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5: White can castle (e1 → h1).
const FEN = 'r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w HAha - 6 4';
const PGN = '[Variant "Chess960"]\n[SetUp "1"]\n[FEN "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w HAha - 0 1"]\n\n'
    + '1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5';
const MATCH = {
    event: 'match_found', variant: 'chess960', game_id: 42, color: 'white', opponent_id: 2,
    white_username: 'alice', white_rating: 1500, black_username: 'bob', black_rating: 1480,
    white_time_ms: 180000, black_time_ms: 180000, base_time_ms: 180000, fen: FEN, pgn: PGN, state_version: 6,
};

const cell = (name: string) => document.querySelector(`[data-square="${name}"]`) as HTMLElement;
const click = (name: string) => fireEvent.click(cell(name));

function renderPage(match: object | null = MATCH) {
    return render(
        <MemoryRouter initialEntries={[{pathname: '/play/960/live', state: match ? {match} : null}]}>
            <Routes><Route path="/play/960/live" element={<Chess960LiveGame/>}/></Routes>
        </MemoryRouter>,
    );
}

beforeEach(() => setToken('jwt'));
afterEach(() => {
    setToken(null);
    handlers.clear();
    vi.mocked(gameSocket.send).mockClear();
});

describe('helpers', () => {
    it('moves from PGN and a position for the board without castling rights', () => {
        expect(sansOf(PGN)).toEqual(['e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Bc5']);
        expect(sansOf('[FEN "x"]\n\n1. e4 e5 2. O-O 1-0')).toEqual(['e4', 'e5', 'O-O']);
        expect(displayFen(FEN).split(' ')[2]).toBe('-');
    });
});

describe('a 960 game with a person', () => {
    it('castling by a click on the king and on its own rook, the server answer updates the board', async () => {
        renderPage();
        expect(screen.getByTestId('c960-live-status')).toHaveTextContent('Your move');
        expect(screen.getByTestId('c960-live-moves')).toHaveTextContent('1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5');
        fireEvent.click(cell('e1'));
        fireEvent.click(cell('h1'));
        expect(gameSocket.send).toHaveBeenCalledWith('make_move', expect.objectContaining({
            game_id: 42, move: 'e1h1', state_version: 6, is_premove: false,
        }));
        await act(async () => handlers.get('move_made')!({
            game_id: 42, move: 'e1h1', state_version: 7, white_time_ms: 175000, black_time_ms: 180000,
            fen: 'r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1 b ha - 7 4', pgn: `${PGN} 4. O-O`,
        }));
        expect(screen.getByTestId('c960-live-status')).toHaveTextContent('Opponent to move');
        expect(screen.getByTestId('c960-live-moves')).toHaveTextContent('4. O-O');
    });

    it('a draw: the opponent\'s offer, accept; the game result', async () => {
        renderPage();
        await act(async () => handlers.get('draw_offered')!({game_id: 42}));
        fireEvent.click(screen.getByText('Accept'));
        expect(gameSocket.send).toHaveBeenCalledWith('accept_draw', {game_id: 42});
        await act(async () => handlers.get('game_over')!({game_id: 42, result: '1/2-1/2', reason: 'agreement'}));
        expect(screen.getByTestId('c960-live-again')).toBeInTheDocument();
        expect(screen.queryByTestId('c960-live-resign')).toBeNull();
    });

    it('a rematch after the end of the game: offer; the opponent\'s offer — accept', async () => {
        renderPage();
        expect(screen.queryByTestId('c960-live-rematch')).toBeNull();  // while the game is on — there is no button
        await act(async () => handlers.get('game_over')!({event: 'game_over', game_id: 42, result: '0-1', reason: 'resignation'}));
        fireEvent.click(screen.getByTestId('c960-live-rematch'));
        expect(gameSocket.send).toHaveBeenCalledWith('offer_rematch', {game_id: 42});
        expect(screen.getByTestId('c960-live-rematch-sent')).toBeInTheDocument();
        expect(screen.getByTestId('c960-live-rematch')).toBeDisabled();

        await act(async () => handlers.get('rematch_offered')!({event: 'rematch_offered', game_id: 42, player_id: 2}));
        fireEvent.click(screen.getByTestId('c960-live-rematch-accept'));
        expect(gameSocket.send).toHaveBeenCalledWith('accept_rematch', {game_id: 42});
        // The server starts a rematch — match_found of a new 960 game: the board and the status update, no rematch buttons.
        await act(async () => handlers.get('match_found')!({...MATCH, game_id: 43, color: 'black'}));
        expect(screen.queryByTestId('c960-live-rematch')).toBeNull();
        expect(screen.queryByTestId('c960-live-rematch-offer')).toBeNull();
    });

    it('game chat: messages of one\'s own game are visible, of another — not; one\'s own message goes over the socket', async () => {
        renderPage();
        await act(async () => handlers.get('chat_message')!({event: 'chat_message', game_id: 42, sender: 'bob', text: 'Good luck!'}));
        await act(async () => handlers.get('chat_message')!({event: 'chat_message', game_id: 7, sender: 'eve', text: 'foreign'}));
        expect(screen.getByText('Good luck!')).toBeInTheDocument();
        expect(screen.queryByText('foreign')).toBeNull();
        fireEvent.change(screen.getByPlaceholderText('Write a message…'), {target: {value: '  And you!  '}});
        fireEvent.click(screen.getByRole('button', {name: 'Send'}));
        expect(gameSocket.send).toHaveBeenCalledWith('chat_message', {game_id: 42, text: 'And you!'});
        expect(screen.getByPlaceholderText('Write a message…')).toHaveValue('');
    });

    it('premove: selected on the opponent\'s move, sent as soon as it is our move; a cancelled one is not sent', async () => {
        renderPage({...MATCH, color: 'black'});  // White is to move in the position — it is the opponent's move now
        click('d7');
        click('d6');
        expect(gameSocket.send).not.toHaveBeenCalledWith('make_move', expect.anything());
        expect(screen.getByTestId('c960-live-premove')).toHaveTextContent('d7–d6');
        const AFTER_D3 = 'r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R b HAha - 0 4';
        await act(async () => handlers.get('move_made')!({game_id: 42, fen: AFTER_D3, pgn: PGN + ' 4. d3', state_version: 7, move: 'd2d3'}));
        expect(gameSocket.send).toHaveBeenCalledWith('make_move', expect.objectContaining({move: 'd7d6', is_premove: true, state_version: 7}));
        expect(screen.queryByTestId('c960-live-premove')).toBeNull();

        vi.mocked(gameSocket.send).mockClear();
        const AFTER_D6 = 'r1bqk1nr/ppp2ppp/2np4/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w HAha - 0 5';
        await act(async () => handlers.get('move_made')!({game_id: 42, fen: AFTER_D6, pgn: PGN + ' 4. d3 d6', state_version: 8, move: 'd7d6'}));
        click('h7');
        click('h6');
        fireEvent.click(screen.getByTestId('c960-live-premove-cancel'));
        await act(async () => handlers.get('move_made')!({game_id: 42, fen: AFTER_D3.replace(' b ', ' b '), pgn: PGN, state_version: 9, move: 'a2a3'}));
        expect(gameSocket.send).not.toHaveBeenCalledWith('make_move', expect.anything());
    });

    it('events of another game do not touch the board; without a game — a hint on how to start', async () => {
        renderPage();
        await act(async () => handlers.get('move_made')!({game_id: 99, fen: '8/8/8/8/8/8/8/K6k w - - 0 1', pgn: ''}));
        expect(screen.getByTestId('c960-live-moves')).toHaveTextContent('3. Bc4 Bc5');
        renderPage(null);
        expect(screen.getByTestId('c960-live-empty')).toHaveTextContent('No Chess960 game is running');
    });

    it('reconnect: match_found of a 960 game restores the board', async () => {
        renderPage(null);
        await act(async () => handlers.get('match_found')!(MATCH));
        expect(screen.getByTestId('c960-live')).toBeInTheDocument();
        expect(screen.getByTestId('c960-live-opponent')).toHaveTextContent('bob (1480)');
    });
});
