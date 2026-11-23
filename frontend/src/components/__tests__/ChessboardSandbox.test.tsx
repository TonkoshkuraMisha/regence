// --- FILE: frontend/src/components/__tests__/ChessboardSandbox.test.tsx ---
// The free board (no game) in Chessboard.tsx: paging through moves with keys and buttons, pawn promotion (choice,
// cancel, Esc), dragging a piece (a move, a drop beside the board, by the frame coordinates), stretching the board by the corner
// and resetting by double click, saving the appearance in localStorage, parsing a position from the navigation state.
// The network is stubbed as in the neighbouring Chessboard*.test.tsx tests; a move is made by clicks through test/boardMoves.ts.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import Chessboard from '../Chessboard';
import {mockFetchRouter} from '../../test/mocks';
import {setToken} from '../../services/authToken';
import {boardCell, playMove} from '../../test/boardMoves';
import {soundEngine} from '../../services/soundEngine';

vi.mock('../../services/gameSocket', () => ({
    gameSocket: {connect: vi.fn(), disconnect: vi.fn(), send: vi.fn(), on: vi.fn(), off: vi.fn()},
}));

vi.mock('../../services/soundEngine', async (importOriginal) => {
    const actual = await importOriginal<typeof import('../../services/soundEngine')>();
    return {
        ...actual,
        soundEngine: {play: vi.fn(), isMuted: vi.fn(() => false), toggleMute: vi.fn(() => false)},
    };
});

const PROMO_FEN = '8/P6k/8/8/8/8/8/K7 w - - 0 1';

async function renderBoard(initialEntries: Array<string | { pathname: string; state: unknown }> = ['/']) {
    vi.stubGlobal('fetch', mockFetchRouter({
        '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
        '/profile/matchmaking/queue': () => [],
        '/profile/games/live': () => [],
        '/profile/games/my-active': () => ({active: false}),
    }));
    render(
        <MemoryRouter initialEntries={initialEntries}>
            <Chessboard/>
        </MemoryRouter>,
    );
    await screen.findByTestId('new-game-open');
}

const pieceAt = (square: string) => boardCell(square).querySelector('img')?.getAttribute('alt') ?? null;

async function key(k: string) {
    await act(async () => {
        fireEvent.keyDown(window, {key: k});
    });
}

async function loadFen(fen: string) {
    fireEvent.change(await screen.findByLabelText('Position in FEN'), {target: {value: fen}});
    await act(async () => {
        fireEvent.click(screen.getByRole('button', {name: /Set up/}));
    });
}

beforeEach(() => {
    setToken('test-token');
    vi.mocked(soundEngine.play).mockClear();
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
});

describe('paging through moves on the free board', () => {
    it('arrows and buttons rewind the position; the sound plays on every step', async () => {
        await renderBoard();
        await playMove('e2', 'e4');
        await playMove('e7', 'e5');
        expect(pieceAt('e5')).toBe('bp');

        await key('ArrowLeft');
        expect(pieceAt('e5')).toBeNull();
        expect(pieceAt('e4')).toBe('wp');
        await key('ArrowLeft');
        expect(pieceAt('e4')).toBeNull();
        await key('ArrowLeft');  // already at the start — nothing changes
        expect(pieceAt('e2')).toBe('wp');

        await key('ArrowRight');
        expect(pieceAt('e4')).toBe('wp');
        await key('ArrowRight');
        expect(pieceAt('e5')).toBe('bp');
        await key('ArrowRight');  // already the live position
        expect(pieceAt('e5')).toBe('bp');

        await key('ArrowUp');
        expect(pieceAt('e4')).toBeNull();
        await key('ArrowUp');  // a repeat — no changes
        await key('ArrowDown');
        expect(pieceAt('e5')).toBe('bp');
        await key('ArrowDown');

        fireEvent.click(screen.getByTitle(/To the start of the game/));
        expect(pieceAt('e4')).toBeNull();
        fireEvent.click(screen.getByTitle(/Move forward/));
        expect(pieceAt('e4')).toBe('wp');
        fireEvent.click(screen.getByTitle(/Move forward/));
        expect(pieceAt('e5')).toBe('bp');
        fireEvent.click(screen.getByTitle(/Move back/));
        expect(pieceAt('e5')).toBeNull();
        fireEvent.click(screen.getByTitle(/To the last move/));
        expect(pieceAt('e5')).toBe('bp');
        expect(vi.mocked(soundEngine.play)).toHaveBeenCalled();
    });

    it('keys in an input field do not page through the game, Esc clears the piece selection', async () => {
        await renderBoard();
        await playMove('e2', 'e4');
        const input = await screen.findByLabelText('Position in FEN');
        await act(async () => {
            fireEvent.keyDown(input, {key: 'ArrowLeft'});
        });
        expect(pieceAt('e4')).toBe('wp');

        await act(async () => {
            fireEvent.click(boardCell('e7'));
        });
        await key('Escape');
        await act(async () => {
            fireEvent.click(boardCell('e5'));
        });
        expect(pieceAt('e5')).toBeNull();  // there was no selection — a click on an empty square moves nothing
    });
});

describe('pawn promotion', () => {
    async function openPromotion() {
        await renderBoard();
        await loadFen(PROMO_FEN);
        await playMove('a7', 'a8');
    }

    it('choosing a piece in the window puts it on the promotion square', async () => {
        await openPromotion();
        expect(screen.getByText(/Pawn promotion \(a8\)/)).toBeInTheDocument();
        await act(async () => {
            fireEvent.click(screen.getByTitle('Rook'));
        });
        expect(pieceAt('a8')).toBe('wr');
    });

    it('cancelling with the cross, Esc and a click on the background close the window without a move', async () => {
        await openPromotion();
        fireEvent.click(screen.getByRole('button', {name: /Cancel/}));
        expect(screen.queryByText(/Pawn promotion/)).toBeNull();
        expect(pieceAt('a7')).toBe('wp');

        await playMove('a7', 'a8');
        await key('Escape');
        expect(screen.queryByText(/Pawn promotion/)).toBeNull();

        await playMove('a7', 'a8');
        await act(async () => {
            fireEvent.click(boardCell('b3'));  // a click on a square with the window open closes it
        });
        expect(screen.queryByText(/Pawn promotion/)).toBeNull();
        expect(pieceAt('a7')).toBe('wp');
    });
});

describe('dragging a piece', () => {
    function grab(square: string) {
        const piece = boardCell(square).querySelector('div.relative') as HTMLElement;
        fireEvent.pointerDown(piece, {button: 0, pointerType: 'mouse', clientX: 50, clientY: 50});
    }

    it('a drop over a square makes a move; the piece ghost follows the pointer', async () => {
        await renderBoard();
        grab('e2');
        expect(screen.getByTestId('drag-ghost')).toBeInTheDocument();
        fireEvent.pointerMove(window, {clientX: 80, clientY: 90});
        expect(screen.getByTestId('drag-ghost').style.left).toBe('80px');

        document.elementsFromPoint = vi.fn(() => [boardCell('e4')]);
        await act(async () => {
            fireEvent.pointerUp(window, {clientX: 80, clientY: 90});
        });
        expect(pieceAt('e4')).toBe('wp');
        expect(screen.queryByTestId('drag-ghost')).toBeNull();
    });

    it('if there is no square under the pointer, the cell is found by the board frame coordinates', async () => {
        await renderBoard();
        const frame = document.querySelector('[role="group"]')!.parentElement as HTMLElement;
        vi.spyOn(frame, 'getBoundingClientRect').mockReturnValue(
            {left: 0, top: 0, width: 820, height: 820, right: 820, bottom: 820, x: 0, y: 0, toJSON: () => ({})} as DOMRect,
        );
        grab('d2');
        document.elementsFromPoint = vi.fn(() => []);
        // The inner area is 800 px: column d — index 3 (x 300..400), row 4 — index 4 from the top (y 400..500).
        await act(async () => {
            fireEvent.pointerUp(window, {clientX: 10 + 350, clientY: 10 + 450});
        });
        expect(pieceAt('d4')).toBe('wp');
    });

    it('a drop beside the board makes no move and removes the ghost', async () => {
        await renderBoard();
        grab('e2');
        document.elementsFromPoint = vi.fn(() => []);
        await act(async () => {
            fireEvent.pointerUp(window, {clientX: -500, clientY: -500});
        });
        expect(pieceAt('e2')).toBe('wp');
        expect(screen.queryByTestId('drag-ghost')).toBeNull();
    });

    it('a piece of the other colour cannot be taken on the free board', async () => {
        await renderBoard();
        grab('e7');
        expect(screen.queryByTestId('drag-ghost')).toBeNull();
    });
});

describe('board size and appearance', () => {
    it('the corner stretches the board and remembers the size, a double click returns the original', async () => {
        await renderBoard();
        const handle = screen.getByTitle(/Drag to resize/);
        fireEvent.pointerDown(handle, {clientX: 100, clientY: 100});
        expect(document.body.style.cursor).toBe('nwse-resize');
        fireEvent.pointerMove(window, {clientX: 60, clientY: 60});
        expect(Number(localStorage.getItem('regence_board_size'))).toBeGreaterThan(0);
        fireEvent.pointerUp(window);
        expect(document.body.style.cursor).toBe('');

        fireEvent.doubleClick(handle);
        expect(Number(localStorage.getItem('regence_board_size'))).toBeGreaterThan(0);
    });

    it('a position from the navigation state (a puzzle review) is put on the board', async () => {
        await renderBoard([{pathname: '/', state: {analyzeFen: PROMO_FEN}}]);
        expect(pieceAt('a7')).toBe('wp');
        expect(pieceAt('e2')).toBeNull();
    });

    it('the choice of set and theme is saved in the browser, a click outside closes the window', async () => {
        await renderBoard();
        fireEvent.click(screen.getByTitle('Choose the piece set, theme and size of the board'));
        const sizeSlider = document.querySelector('input[type="range"]') as HTMLInputElement;
        expect(sizeSlider).not.toBeNull();
        fireEvent.change(sizeSlider, {target: {value: '400'}});
        expect(localStorage.getItem('regence_board_size')).toBe('400');
        fireEvent.click(screen.getByRole('button', {name: /Auto/}));

        // The set and theme buttons are in grids of five columns of the appearance window; the locked (disabled) ones are not touched.
        const grids = Array.from(document.querySelectorAll('.grid-cols-5'));
        expect(grids.length).toBeGreaterThanOrEqual(2);
        for (const grid of grids) {
            const option = grid.querySelectorAll<HTMLButtonElement>('button:not([disabled])');
            fireEvent.click(option[option.length - 1]);
        }
        expect(localStorage.getItem('regence_piece_set')).not.toBeNull();
        expect(localStorage.getItem('regence_board_theme')).not.toBeNull();

        fireEvent.mouseDown(document.body);
        expect(document.querySelector('input[type="range"]')).toBeNull();
    });
});
