// The tournament end screen, branches beyond TournamentCelebration.test.tsx: unavailable storage (the celebration is shown,
// the record is silently skipped), confetti on a canvas (volleys, rain, a window resize, stopping on close, a refusal on
// "reduce motion"), the tournament summary and downloading CSV from the results table.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {soundEngine} from '../../../services/soundEngine';
import {markCelebrated, shouldCelebrate, TournamentCelebration} from '../TournamentCelebration';

const ROWS = [
    {key: 1, place: 1, name: 'Morphy, Paul', rating: 2100, score: '2', mine: false, detail: '2/0/0'},
    {key: 2, place: 2, name: 'misha', rating: 1500, score: '1', mine: true},
];

function fakeContext() {
    return {
        clearRect: vi.fn(), save: vi.fn(), restore: vi.fn(), translate: vi.fn(), rotate: vi.fn(), beginPath: vi.fn(),
        arc: vi.fn(), fill: vi.fn(), fillRect: vi.fn(), fillStyle: '',
    };
}

beforeEach(() => {
    localStorage.clear();
    vi.spyOn(soundEngine, 'playFanfare').mockImplementation(() => undefined);
});
afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe('storage unavailable', () => {
    it('the celebration is shown, and the mark is not written and does not throw', () => {
        vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
            throw new Error('denied');
        });
        vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
            throw new Error('denied');
        });
        expect(shouldCelebrate(7)).toBe(true);
        expect(() => markCelebrated(7)).not.toThrow();
    });
});

describe('confetti', () => {
    it('draws volleys and rain, reacts to a window resize and stops on close', () => {
        const ctx = fakeContext();
        vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
        vi.stubGlobal('matchMedia', () => ({matches: false}));
        let tick: FrameRequestCallback = () => undefined;
        const raf = vi.fn((cb: FrameRequestCallback) => {
            tick = cb;
            return 1;
        });
        const cancel = vi.fn();
        vi.stubGlobal('requestAnimationFrame', raf);
        vi.stubGlobal('cancelAnimationFrame', cancel);
        vi.spyOn(Math, 'random').mockReturnValue(0.1);  // round pieces and rain

        const {unmount} = render(<TournamentCelebration place={1} title="Cup" size={4} onClose={vi.fn()}/>);
        expect(screen.getByTestId('celebration-confetti')).toBeInTheDocument();
        act(() => {
            window.dispatchEvent(new Event('resize'));
            tick(performance.now() + 100);
        });
        expect(ctx.clearRect).toHaveBeenCalled();
        expect(ctx.arc).toHaveBeenCalled();
        // Later the pieces drop below the window and are removed, and the frames stop when there is nothing left to fall.
        vi.spyOn(Math, 'random').mockReturnValue(0.9);
        act(() => {
            tick(performance.now() + 20000);
        });
        unmount();
        expect(cancel).toHaveBeenCalled();
    });

    it('strips (not round pieces) are drawn as rectangles', () => {
        const ctx = fakeContext();
        vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
        vi.stubGlobal('matchMedia', () => ({matches: false}));
        let tick: FrameRequestCallback = () => undefined;
        vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
            tick = cb;
            return 1;
        });
        vi.stubGlobal('cancelAnimationFrame', vi.fn());
        vi.spyOn(Math, 'random').mockReturnValue(0.9);
        render(<TournamentCelebration place={2} title="Cup" size={4} onClose={vi.fn()}/>);
        act(() => {
            tick(performance.now() + 50);
        });
        expect(ctx.fillRect).toHaveBeenCalled();
    });

    it('with "reduce motion" confetti is not drawn', () => {
        const ctx = fakeContext();
        vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
        vi.stubGlobal('matchMedia', () => ({matches: true}));
        const raf = vi.fn(() => 1);
        vi.stubGlobal('requestAnimationFrame', raf);
        render(<TournamentCelebration place={1} title="Cup" size={4} onClose={vi.fn()}/>);
        expect(raf).not.toHaveBeenCalled();
        expect(ctx.clearRect).not.toHaveBeenCalled();
    });
});

describe('results table', () => {
    it('the tournament summary, the detail label and downloading CSV', () => {
        const createUrl = vi.fn(() => 'blob:x');
        const revoke = vi.fn();
        Object.assign(URL, {createObjectURL: createUrl, revokeObjectURL: revoke});
        const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
        render(<TournamentCelebration place={2} title="Kyiv 1903" size={2} onClose={vi.fn()} rows={ROWS}
                                      summary={{games: 6, drawPercent: 33, whitePercent: 50}} detailLabel="perf."/>);
        expect(screen.getByTestId('celebration-summary')).toBeInTheDocument();
        expect(screen.getByTestId('celebration-detail-1')).toHaveTextContent('2/0/0');
        fireEvent.click(screen.getByTestId('celebration-csv'));
        expect(createUrl).toHaveBeenCalledTimes(1);
        expect(click).toHaveBeenCalledTimes(1);
        expect(revoke).toHaveBeenCalledWith('blob:x');
    });

    it('a browser without Blob/URL: the CSV button silently does nothing', () => {
        Object.assign(URL, {createObjectURL: () => {
            throw new Error('unsupported');
        }});
        render(<TournamentCelebration place={5} title="T" size={2} onClose={vi.fn()} rows={ROWS}/>);
        expect(() => fireEvent.click(screen.getByTestId('celebration-csv'))).not.toThrow();
    });
});
