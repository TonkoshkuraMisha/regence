// The review studio (GameViewer): sound, the "View" panel (piece set and board theme), resizing the board
// by dragging and by double click, the "x-ray" over the board, a click on a move in the game record and the export of
// the annotated PGN. The network is replaced by a fetch stub, as in GameViewer.test.tsx.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import GameViewer from '../GameViewer';
import {soundEngine} from '../../services/soundEngine';

vi.mock('../../services/soundEngine', async (importOriginal) => {
    const actual = await importOriginal<typeof import('../../services/soundEngine')>();
    return {
        ...actual,
        soundEngine: {play: vi.fn(), isMuted: vi.fn(() => true), toggleMute: vi.fn(() => false)},
    };
});

const PGN = '[White "alice"]\n[Black "bob"]\n[Result "0-1"]\n\n1. f3 e5 2. g4 Qh4# 0-1';

const side = {accuracy: 80, best: 1, good: 0, inaccuracies: 0, mistakes: 0, blunders: 0, avg_cp_loss: 10};
const ANALYSIS = {
    game_id: 42, engine: 'Stockfish', white: side, black: side,
    moves: ['f3', 'e5', 'g4', 'Qh4#'].map((san, i) => ({
        ply: i + 1, move_number: Math.floor(i / 2) + 1, color: i % 2 ? 'black' : 'white', san, uci: '',
        eval_cp: 0, eval_display: '0.0', mate: null, best_move_uci: null,
        cp_loss: 0, classification: 'best', symbol: '',
    })),
};

function stubApi(withAnalysis: boolean) {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
        const url = input.toString();
        const reply = url.endsWith('/pgn') ? {ok: true, body: {}, text: PGN}
            : url.includes('/analysis/game/') && withAnalysis ? {ok: true, body: ANALYSIS, text: ''}
                : {ok: false, body: {}, text: ''};
        return {ok: reply.ok, status: reply.ok ? 200 : 404, json: async () => reply.body, text: async () => reply.text} as Response;
    }));
}

async function renderViewer() {
    const view = render(
        <MemoryRouter initialEntries={['/game/42']}>
            <Routes>
                <Route path="/game/:gameId" element={<GameViewer/>}/>
            </Routes>
        </MemoryRouter>,
    );
    await waitFor(() => expect(document.querySelector('[data-square="h4"] img')).not.toBeNull());
    return view;
}

beforeEach(() => {
    localStorage.clear();
    vi.mocked(soundEngine.play).mockClear();
    vi.stubGlobal('ResizeObserver', class {
        observe() {
        }

        unobserve() {
        }

        disconnect() {
        }
    });
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('GameViewer: sound and appearance', () => {
    it('turning the sound on plays a trial move', async () => {
        stubApi(false);
        await renderViewer();
        fireEvent.click(screen.getByTitle('Turn sound on'));
        expect(soundEngine.toggleMute).toHaveBeenCalled();
        expect(soundEngine.play).toHaveBeenCalledWith('move');
    });

    it('the "View" panel: the choice of piece set and board theme is remembered, it closes with the cross', async () => {
        stubApi(false);
        await renderViewer();
        fireEvent.click(screen.getByRole('button', {name: 'Look'}));
        const panel = await screen.findByTestId('viewer-appearance');
        const options = panel.querySelectorAll<HTMLButtonElement>('button:not([aria-label])');
        const enabled = Array.from(options).filter((b) => !b.disabled);
        expect(enabled.length).toBeGreaterThan(2);
        for (const option of enabled) fireEvent.click(option);
        expect(localStorage.getItem('regence_piece_set')).toBeTruthy();
        expect(localStorage.getItem('regence_board_theme')).toBeTruthy();
        fireEvent.click(screen.getByRole('button', {name: 'Close'}));
        expect(screen.queryByTestId('viewer-appearance')).toBeNull();
    });
});

describe('GameViewer: board size', () => {
    it('dragging the corner changes and remembers the size, the end of the gesture restores the cursor', async () => {
        stubApi(false);
        await renderViewer();
        const handle = screen.getByTitle(/Drag to resize the board/);
        fireEvent.pointerDown(handle, {clientX: 100, clientY: 100});
        expect(document.body.style.cursor).toBe('nwse-resize');
        act(() => {
            window.dispatchEvent(new PointerEvent('pointermove', {clientX: 40, clientY: 40}));
        });
        const shrunk = Number(localStorage.getItem('regence_board_size'));
        expect(shrunk).toBeGreaterThan(0);
        act(() => {
            window.dispatchEvent(new PointerEvent('pointerup'));
        });
        await waitFor(() => expect(document.body.style.cursor).not.toBe('nwse-resize'));
        // Movement after release does not touch the size.
        act(() => {
            window.dispatchEvent(new PointerEvent('pointermove', {clientX: 500, clientY: 500}));
        });
        expect(Number(localStorage.getItem('regence_board_size'))).toBe(shrunk);
    });

    it('a double click on the corner returns the size to fit the screen; narrowing the window does not let the board go beyond it', async () => {
        stubApi(false);
        await renderViewer();
        fireEvent.doubleClick(screen.getByTitle(/Drag to resize the board/));
        expect(Number(localStorage.getItem('regence_board_size'))).toBeGreaterThan(0);
        act(() => {
            window.dispatchEvent(new Event('resize'));
        });
        expect(document.querySelector('[data-square="a1"]')).not.toBeNull();
    });
});

describe('GameViewer: game review', () => {
    it('a click on a move in the record goes to the position and plays a sound', async () => {
        stubApi(true);
        await renderViewer();
        await screen.findAllByText(/80/);
        fireEvent.click(screen.getAllByText('e5')[0]);
        await waitFor(() => expect(document.querySelector('[data-square="e5"] img')).not.toBeNull());
        expect(document.querySelector('[data-square="h4"] img')).toBeNull();
        expect(soundEngine.play).toHaveBeenCalled();
    });

    it('the "x-ray" over the board is turned on from the review panel', async () => {
        stubApi(true);
        await renderViewer();
        fireEvent.click(await screen.findByTestId('xray-mode-control'));
        expect(JSON.parse(localStorage.getItem('regence_xray_modes') ?? '[]')).toContain('control');
        fireEvent.click(screen.getByTestId('xray-for-opponent'));
        expect(screen.getByTestId('xray-for-opponent')).toBeChecked();
    });

    it('the export button gives a PGN with the review markup', async () => {
        stubApi(true);
        const blobs: Blob[] = [];
        const createUrl = vi.fn((blob: Blob) => {
            blobs.push(blob);
            return 'blob:pgn';
        });
        vi.stubGlobal('URL', Object.assign(URL, {createObjectURL: createUrl, revokeObjectURL: vi.fn()}));
        const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
        await renderViewer();
        fireEvent.click(await screen.findByTestId('download-annotated'));
        expect(click).toHaveBeenCalled();
        expect(await blobs[0].text()).toContain('Qh4#');
        click.mockRestore();
    });
});
