// The puzzle board: every way to make a move — by dragging and by two clicks; special moves (castling, en passant,
// promotion with a piece choice, with a capture), prohibitions (an opponent's piece, a pin, check, not your turn, a non-interactive
// board), cancelling and re-selecting, a position change mid-move, Black's orientation, the square-pick mode (13.6).

import {act, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {PuzzleBoard} from '../PuzzleBoard';
import {setLanguage} from '../../../i18n';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const CASTLING = 'r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1';
const EN_PASSANT = 'rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3';
const PROMOTION = '1r2k3/P7/8/8/8/8/8/4K3 w - - 0 1';
const CAPTURE = 'rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2';
const PINNED = '4k3/4r3/8/8/8/8/4B3/4K3 w - - 0 1';
const IN_CHECK = '4k3/8/8/8/8/8/8/r3K2N w - - 0 1';
const BLACK_TO_MOVE = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1';

function setup(props: Partial<Parameters<typeof PuzzleBoard>[0]> = {}) {
    const onMove = vi.fn();
    const utils = render(<PuzzleBoard fen={START} orientation="white" interactive onMove={onMove} {...props}/>);
    return {onMove, ...utils};
}

function cell(name: string): HTMLElement {
    const el = document.querySelector(`[data-square="${name}"]`);
    if (!(el instanceof HTMLElement)) throw new Error(`no square ${name}`);
    return el;
}

const click = (name: string) => act(() => {
    fireEvent.click(cell(name));
});

/** Dragging: press on square from, pointer movement, release over square to (or off the board — null). */
function drag(from: string, to: string | null, {button = 0, pointerType = 'mouse', cancel = false} = {}) {
    const target = to ? cell(to) : null;
    document.elementsFromPoint = vi.fn(() => (target ? [target.firstElementChild ?? target, target] : [document.body]));
    act(() => {
        fireEvent.pointerDown(cell(from), {button, pointerType, clientX: 10, clientY: 10});
    });
    act(() => {
        fireEvent.pointerMove(window, {clientX: 40, clientY: 40});
    });
    act(() => {
        if (cancel) fireEvent.pointerCancel(window);
        else fireEvent.pointerUp(window, {clientX: 80, clientY: 80});
    });
}

const targets = () => Array.from(document.querySelectorAll('[data-testid^="puzzle-target-"]'))
    .map((el) => el.getAttribute('data-testid')!.replace('puzzle-target-', '')).sort();

afterEach(() => {
    vi.restoreAllMocks();
});

describe('move by two clicks', () => {
    it('a piece, then a square', () => {
        const {onMove} = setup();
        click('e2');
        expect(targets()).toEqual(['e3', 'e4']);
        click('e4');
        expect(onMove).toHaveBeenCalledWith('e2e4');
        expect(targets()).toEqual([]);
    });

    it('knight: two squares in the starting position', () => {
        const {onMove} = setup();
        click('g1');
        expect(targets()).toEqual(['f3', 'h3']);
        click('h3');
        expect(onMove).toHaveBeenCalledWith('g1h3');
    });

    it('another own piece — the selection switches; an empty square — clears the selection', () => {
        const {onMove} = setup();
        click('e2');
        click('d2');
        expect(targets()).toEqual(['d3', 'd4']);
        click('a5');
        expect(targets()).toEqual([]);
        expect(onMove).not.toHaveBeenCalled();
    });

    it('an opponent\'s piece is not selected', () => {
        setup();
        click('e7');
        expect(targets()).toEqual([]);
    });

    it('an illegal square neither moves nor clears anything extra: the selection disappears', () => {
        const {onMove} = setup();
        click('e2');
        click('e5');
        expect(onMove).not.toHaveBeenCalled();
    });

    it('capture by click', () => {
        const {onMove} = setup({fen: CAPTURE});
        click('e4');
        expect(targets()).toEqual(['d5', 'e5']);
        click('d5');
        expect(onMove).toHaveBeenCalledWith('e4d5');
    });
});

describe('move by dragging', () => {
    it('a pawn two squares', () => {
        const {onMove} = setup();
        drag('e2', 'e4');
        expect(onMove).toHaveBeenCalledWith('e2e4');
    });

    it('knight and a capture', () => {
        const {onMove} = setup({fen: CAPTURE});
        drag('g1', 'f3');
        expect(onMove).toHaveBeenLastCalledWith('g1f3');
        drag('e4', 'd5');
        expect(onMove).toHaveBeenLastCalledWith('e4d5');
    });

    it('touch and pen work the same as the mouse', () => {
        const {onMove} = setup();
        drag('e2', 'e4', {pointerType: 'touch'});
        drag('d2', 'd4', {pointerType: 'pen'});
        expect(onMove.mock.calls).toEqual([['e2e4'], ['d2d4']]);
    });

    it('released on the same square — the piece is selected, the move is finished by a click', () => {
        const {onMove} = setup();
        drag('e2', 'e2');
        expect(onMove).not.toHaveBeenCalled();
        expect(targets()).toEqual(['e3', 'e4']);
        click('e3');
        expect(onMove).toHaveBeenCalledWith('e2e3');
    });

    it('onto an illegal square — no move', () => {
        const {onMove} = setup();
        drag('e2', 'e5');
        drag('g1', 'g3');
        expect(onMove).not.toHaveBeenCalled();
    });

    it('off the board and cancelling the gesture — no move', () => {
        const {onMove} = setup();
        drag('e2', null);
        drag('e2', 'e4', {cancel: true});
        expect(onMove).not.toHaveBeenCalled();
    });

    it('the right mouse button and an opponent\'s piece do not start dragging', () => {
        const {onMove} = setup();
        drag('e2', 'e4', {button: 2});
        drag('e7', 'e5');
        drag('e4', 'e5');  // an empty square
        expect(onMove).not.toHaveBeenCalled();
    });

    it('the piece "sticks" to the pointer, the source square is dimmed; after the move — it disappears', () => {
        setup();
        document.elementsFromPoint = vi.fn(() => [cell('e4')]);
        act(() => {
            fireEvent.pointerDown(cell('e2'), {button: 0, pointerType: 'mouse', clientX: 10, clientY: 10});
        });
        expect(screen.queryByTestId('puzzle-drag-piece')).toBeNull();  // not moved yet — it may be a click
        act(() => {
            fireEvent.pointerMove(window, {clientX: 60, clientY: 70});
        });
        const ghost = screen.getByTestId('puzzle-drag-piece');
        expect(ghost.style.left).toBe('60px');
        expect(ghost.style.top).toBe('70px');
        expect(cell('e2').querySelector('img')!.className).toContain('opacity-30');
        act(() => {
            fireEvent.pointerUp(window, {clientX: 60, clientY: 70});
        });
        expect(screen.queryByTestId('puzzle-drag-piece')).toBeNull();
    });
});

describe('special moves', () => {
    it.each([
        ['e1', 'g1', 'e1g1'],
        ['e1', 'c1', 'e1c1'],
    ])('castling %s→%s by clicks and by dragging', (from, to, uci) => {
        const {onMove, unmount} = setup({fen: CASTLING});
        click(from);
        expect(targets()).toContain(to);
        click(to);
        expect(onMove).toHaveBeenLastCalledWith(uci);
        unmount();
        const second = setup({fen: CASTLING});
        drag(from, to);
        expect(second.onMove).toHaveBeenLastCalledWith(uci);
    });

    it('en passant', () => {
        const {onMove} = setup({fen: EN_PASSANT});
        click('e5');
        expect(targets()).toEqual(['d6', 'e6']);
        drag('e5', 'd6');
        expect(onMove).toHaveBeenCalledWith('e5d6');
    });

    it.each(['q', 'r', 'b', 'n'])('promotion by clicks: piece choice %s', (piece) => {
        const {onMove} = setup({fen: PROMOTION});
        click('a7');
        click('a8');
        expect(onMove).not.toHaveBeenCalled();  // first — the piece choice
        expect(screen.getByRole('dialog')).toBeTruthy();
        act(() => {
            fireEvent.click(screen.getByTestId(`puzzle-promote-${piece}`));
        });
        expect(onMove).toHaveBeenCalledWith(`a7a8${piece}`);
        expect(screen.queryByRole('dialog')).toBeNull();
    });

    it('promotion with a capture by dragging', () => {
        const {onMove} = setup({fen: PROMOTION});
        drag('a7', 'b8');
        act(() => {
            fireEvent.click(screen.getByTestId('puzzle-promote-n'));
        });
        expect(onMove).toHaveBeenCalledWith('a7b8n');
    });

    it('while the piece choice is open, the board accepts no other moves', () => {
        const {onMove} = setup({fen: PROMOTION});
        drag('a7', 'a8');
        click('e1');
        drag('e1', 'd1');
        expect(onMove).not.toHaveBeenCalled();
    });
});

describe('rules on the board', () => {
    it('a pinned piece moves only along the pin', () => {
        setup({fen: PINNED});
        click('e2');
        expect(targets()).toEqual([]);  // the bishop on e2 is pinned by the rook on e7 — no moves
    });

    it('in check — only moves that save from it', () => {
        const {onMove} = setup({fen: IN_CHECK});
        click('h1');
        expect(targets()).toEqual([]);  // the knight does not block the check
        drag('h1', 'g3');
        expect(onMove).not.toHaveBeenCalled();
        click('e1');
        expect(targets()).toEqual(['d2', 'e2', 'f2']);
    });

    it('a non-interactive board: no selection, no dragging', () => {
        const {onMove} = setup({interactive: false});
        click('e2');
        drag('e2', 'e4');
        expect(targets()).toEqual([]);
        expect(onMove).not.toHaveBeenCalled();
    });

    it('not your turn: pieces of the other colour do not move', () => {
        const {onMove} = setup({fen: BLACK_TO_MOVE});
        drag('d2', 'd4');
        expect(onMove).not.toHaveBeenCalled();
        drag('e7', 'e5');
        expect(onMove).toHaveBeenCalledWith('e7e5');
    });
});

describe('position change', () => {
    it('a selection from the previous position does not apply in the new one', () => {
        const {onMove, rerender} = setup();
        click('e2');
        rerender(<PuzzleBoard fen={BLACK_TO_MOVE} orientation="white" interactive onMove={onMove}/>);
        expect(targets()).toEqual([]);
        click('e3');
        expect(onMove).not.toHaveBeenCalled();
    });

    it('the position changed mid-drag — no move', () => {
        const {onMove, rerender} = setup();
        document.elementsFromPoint = vi.fn(() => [cell('e4')]);
        act(() => {
            fireEvent.pointerDown(cell('e2'), {button: 0, pointerType: 'mouse', clientX: 10, clientY: 10});
        });
        act(() => {
            fireEvent.pointerMove(window, {clientX: 50, clientY: 50});
        });
        rerender(<PuzzleBoard fen={BLACK_TO_MOVE} orientation="white" interactive onMove={onMove}/>);
        act(() => {
            fireEvent.pointerUp(window, {clientX: 50, clientY: 50});
        });
        expect(onMove).not.toHaveBeenCalled();
    });
});

describe('orientation and marks', () => {
    it('for Black the board is flipped, the move works', () => {
        const {onMove} = setup({fen: BLACK_TO_MOVE, orientation: 'black'});
        const order = Array.from(document.querySelectorAll('[data-square]')).map((el) => el.getAttribute('data-square'));
        expect(order[0]).toBe('h1');
        expect(order[63]).toBe('a8');
        drag('g8', 'f6');
        expect(onMove).toHaveBeenCalledWith('g8f6');
    });

    it('the last move, a hint and the ✓/✗ mark', () => {
        setup({lastMove: {from: 'e2', to: 'e4'}, hint: {from: 'g1', to: 'f3'}, mark: {square: 'f3', ok: false}});
        expect(screen.getByTestId('puzzle-hint-g1')).toBeTruthy();
        expect(screen.getByTestId('puzzle-hint-f3')).toBeTruthy();
        expect(screen.getByTestId('puzzle-mark-wrong')).toBeTruthy();
    });
});

describe('square pick (defence exercises)', () => {
    it('a click reports the square; no dragging and no moves', () => {
        const onSquare = vi.fn();
        const {onMove} = setup({onSquare});
        click('f2');
        click('e7');
        drag('e2', 'e4');
        // The drag gesture here is neither a move nor a square pick (the browser will send the click separately, if there was one).
        expect(onSquare.mock.calls.map((c) => c[0])).toEqual(['f2', 'e7']);
        expect(screen.queryByTestId('puzzle-drag-piece')).toBeNull();
        expect(onMove).not.toHaveBeenCalled();
        expect(targets()).toEqual([]);
    });
});

describe('PuzzleBoard: sounds', () => {
    it('a move from the previous position — a sound by notation, a new position without a move and an example without sound — silence', async () => {
        const {soundEngine} = await import('../../../services/soundEngine');
        const play = vi.spyOn(soundEngine, 'play').mockImplementation(() => undefined);
        const onMove = vi.fn();
        const {rerender} = render(<PuzzleBoard fen={START} orientation="white" interactive onMove={onMove}/>);
        const afterE4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1';
        rerender(<PuzzleBoard fen={afterE4} orientation="white" interactive onMove={onMove} lastMove={{from: 'e2', to: 'e4'}}/>);
        expect(play).toHaveBeenLastCalledWith('move');

        rerender(<PuzzleBoard fen="4k3/8/8/8/8/8/8/4K2R w K - 0 1" orientation="white" interactive onMove={onMove}
                              lastMove={{from: 'e2', to: 'e4'}}/>);
        expect(play).toHaveBeenCalledTimes(1);  // a different puzzle, not a move

        rerender(<PuzzleBoard fen="4k3/8/8/8/8/8/8/4K2R w K - 0 1" orientation="white" interactive onMove={onMove}
                              mark={{square: 'h1', ok: false}}/>);
        expect(play).toHaveBeenLastCalledWith('illegal');

        rerender(<PuzzleBoard fen="4k3/8/8/8/8/8/8/5RK1 b - - 1 1" orientation="white" interactive onMove={onMove}
                              lastMove={{from: 'e1', to: 'g1'}} sound={false}/>);
        expect(play).toHaveBeenCalledTimes(2);
        play.mockRestore();
    });
});

describe('board from the keyboard (task 26.3)', () => {
    it('squares are buttons with a label; Tab enters one square; arrows move the focus; Enter — like a click', () => {
        setLanguage('en', {persist: false});
        const {onMove} = setup();
        expect(cell('e2')).toHaveAttribute('role', 'button');
        expect(cell('e2')).toHaveAttribute('aria-label', 'e2, white pawn');
        expect(cell('e4')).toHaveAttribute('aria-label', 'e4, empty');
        // One square enters the Tab order — the top left one on screen (a8 for White).
        expect(document.querySelectorAll('[data-square][tabindex="0"]')).toHaveLength(1);
        expect(cell('a8')).toHaveAttribute('tabindex', '0');

        act(() => cell('e3').focus());
        fireEvent.keyDown(cell('e3'), {key: 'ArrowDown'});
        expect(document.activeElement).toBe(cell('e2'));
        fireEvent.keyDown(cell('e2'), {key: 'Enter'});
        expect(cell('e2')).toHaveAttribute('aria-pressed', 'true');
        fireEvent.keyDown(cell('e2'), {key: 'ArrowUp'});
        fireEvent.keyDown(cell('e3'), {key: 'ArrowUp'});
        fireEvent.keyDown(cell('e4'), {key: ' '});
        expect(onMove).toHaveBeenCalledWith('e2e4');
    });

    it('for Black: Tab enters the top-left square of the screen, arrows follow the screen', () => {
        setup({fen: BLACK_TO_MOVE, orientation: 'black'});
        expect(cell('h1')).toHaveAttribute('tabindex', '0');  // top left for a flipped board
        act(() => cell('e7').focus());
        fireEvent.keyDown(cell('e7'), {key: 'ArrowDown'});  // down the screen — towards the eighth rank
        expect(document.activeElement).toBe(cell('e8'));
    });

    it('a non-interactive board: labels are present, buttons and focus are not', () => {
        setup({interactive: false});
        expect(cell('e2')).toHaveAttribute('aria-label');
        expect(cell('e2')).not.toHaveAttribute('role');
        expect(document.querySelectorAll('[data-square][tabindex]')).toHaveLength(0);
    });
});
