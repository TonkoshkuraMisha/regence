// Board X-ray (task 12.1): the layer on the board and the mode panel.

import {act, fireEvent, render, renderHook, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';
import {XrayOverlay} from '../XrayOverlay';
import {XrayPanel} from '../XrayPanel';
import {useXraySettings} from '../useXraySettings';
import type {XrayMode} from '../useXraySettings';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

function overlay(fen: string, modes: XrayMode[], extra: { side?: 'w' | 'b'; selectedSquare?: string } = {}) {
    return render(<XrayOverlay fen={fen} side={extra.side ?? 'w'} modes={new Set(modes)} flipped={false}
                               selectedSquare={extra.selectedSquare}/>);
}

afterEach(() => localStorage.clear());

describe('XrayOverlay', () => {
    it('without modes — nothing', () => {
        const {container} = overlay(START, []);
        expect(container.querySelector('svg')).toBeNull();
    });

    it('control: the balance number on the squares, empty squares without a mark', () => {
        overlay(START, ['control']);
        expect(screen.getByTestId('xray-control-f3').textContent).toBe('+3');
        expect(screen.getByTestId('xray-control-f6').textContent).toBe('−3');
        expect(screen.queryByTestId('xray-control-e4')).toBeNull();
    });

    it('under attack and overload', () => {
        // The knight d4 and the bishop b1 are protected by the rook d1 — they do not hang, but the rook is overloaded.
        overlay('4k3/8/8/8/r2N4/8/8/rB1R2K1 w - - 0 1', ['hanging']);
        expect(screen.queryByTestId('xray-hanging-d4')).toBeNull();
        expect(screen.getByTestId('xray-overloaded-d1')).toBeTruthy();
        // An unprotected knight under a pawn — it hangs.
        overlay('4k3/8/4p3/3N4/8/8/8/4K3 w - - 0 1', ['hanging']);
        expect(screen.getByTestId('xray-hanging-d5')).toBeTruthy();
    });

    it('captures of different weight, check and mate', () => {
        overlay('6k1/5ppp/8/3n4/8/4N3/5PPP/R5K1 w - - 0 1', ['captures', 'checks']);
        expect(screen.getByTestId('xray-capture-winning').getAttribute('stroke-width')).toBe('2.4');
        expect(screen.getByTestId('xray-mate')).toBeTruthy();
    });

    it('pin, pawns and defences', () => {
        overlay('4k3/p7/2n5/3P4/B7/8/5PPP/4K3 w - - 0 1', ['lines', 'pawns', 'defenses']);
        expect(screen.getByTestId('xray-pin')).toBeTruthy();
        expect(screen.getByTestId('xray-pawn-isolated-d5')).toBeTruthy();
        expect(screen.getByTestId('xray-pawn-passed-h2')).toBeTruthy();
        expect(screen.getAllByTestId('xray-defense').length).toBeGreaterThan(0);
    });

    it('for the other side — its captures', () => {
        overlay('4k3/8/8/3n4/8/4N3/8/4K3 w - - 0 1', ['captures'], {side: 'b'});
        expect(screen.getByTestId('xray-capture-winning')).toBeTruthy();
    });

    it('safe and dangerous squares of the chosen piece', () => {
        overlay('4k3/8/8/8/3p4/8/8/4KN2 w - - 0 1', ['safety'], {selectedSquare: 'f1'});
        expect(screen.getByTestId('xray-danger-e3')).toBeTruthy();
        expect(screen.getByTestId('xray-safe-g3')).toBeTruthy();
    });

    it('all moves', () => {
        const {container} = overlay(START, ['moves']);
        expect(container.querySelectorAll('svg > line')).toHaveLength(20);
    });
});

describe('XrayPanel and settings', () => {
    it('modes are turned on one by one and remembered; the legend — at the enabled one', () => {
        const {result} = renderHook(() => useXraySettings());
        const {rerender} = render(<XrayPanel settings={result.current}/>);
        act(() => fireEvent.click(screen.getByTestId('xray-mode-control')));
        rerender(<XrayPanel settings={result.current}/>);
        expect(result.current.modes.has('control')).toBe(true);
        expect(JSON.parse(localStorage.getItem('regence_xray_modes') ?? '[]')).toEqual(['control']);
        expect(screen.getByText(/the number is the balance of attackers/)).toBeTruthy();

        act(() => fireEvent.click(screen.getByTestId('xray-for-opponent')));
        rerender(<XrayPanel settings={result.current}/>);
        expect(result.current.forOpponent).toBe(true);

        const again = renderHook(() => useXraySettings());
        expect(again.result.current.modes.has('control')).toBe(true);
    });

    it('without a piece choice there is no "safe squares" mode; corrupted settings — empty', () => {
        localStorage.setItem('regence_xray_modes', '{broken');
        const {result} = renderHook(() => useXraySettings());
        expect(result.current.modes.size).toBe(0);
        render(<XrayPanel settings={result.current} canSelect={false}/>);
        expect(screen.queryByTestId('xray-mode-safety')).toBeNull();
    });
});
