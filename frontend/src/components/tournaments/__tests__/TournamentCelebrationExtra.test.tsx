// Экран окончания турнира, ветки сверх TournamentCelebration.test.tsx: недоступное хранилище (праздник показывается,
// запись молча пропускается), конфетти на canvas (залпы, дождь, смена размера окна, остановка при закрытии, отказ при
// «уменьшить движение»), сводка турнира и скачивание CSV из таблицы итогов.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {soundEngine} from '../../../services/soundEngine';
import {markCelebrated, shouldCelebrate, TournamentCelebration} from '../TournamentCelebration';

const ROWS = [
    {key: 1, place: 1, name: 'Морфи, Пол', rating: 2100, score: '2', mine: false, detail: '2/0/0'},
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

describe('хранилище недоступно', () => {
    it('праздник показывается, а отметка не пишется и не бросает ошибку', () => {
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

describe('конфетти', () => {
    it('рисует залпы и дождь, реагирует на смену размера окна и останавливается при закрытии', () => {
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
        vi.spyOn(Math, 'random').mockReturnValue(0.1);  // круглые кусочки и дождь

        const {unmount} = render(<TournamentCelebration place={1} title="Кубок" size={4} onClose={vi.fn()}/>);
        expect(screen.getByTestId('celebration-confetti')).toBeInTheDocument();
        act(() => {
            window.dispatchEvent(new Event('resize'));
            tick(performance.now() + 100);
        });
        expect(ctx.clearRect).toHaveBeenCalled();
        expect(ctx.arc).toHaveBeenCalled();
        // Позже кусочки опускаются ниже окна и удаляются, а кадры прекращаются, когда падать больше нечему.
        vi.spyOn(Math, 'random').mockReturnValue(0.9);
        act(() => {
            tick(performance.now() + 20000);
        });
        unmount();
        expect(cancel).toHaveBeenCalled();
    });

    it('полоски (не круглые кусочки) рисуются прямоугольниками', () => {
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
        render(<TournamentCelebration place={2} title="Кубок" size={4} onClose={vi.fn()}/>);
        act(() => {
            tick(performance.now() + 50);
        });
        expect(ctx.fillRect).toHaveBeenCalled();
    });

    it('при «уменьшить движение» конфетти не рисуется', () => {
        const ctx = fakeContext();
        vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
        vi.stubGlobal('matchMedia', () => ({matches: true}));
        const raf = vi.fn(() => 1);
        vi.stubGlobal('requestAnimationFrame', raf);
        render(<TournamentCelebration place={1} title="Кубок" size={4} onClose={vi.fn()}/>);
        expect(raf).not.toHaveBeenCalled();
        expect(ctx.clearRect).not.toHaveBeenCalled();
    });
});

describe('таблица итогов', () => {
    it('сводка турнира, подпись детали и скачивание CSV', () => {
        const createUrl = vi.fn(() => 'blob:x');
        const revoke = vi.fn();
        Object.assign(URL, {createObjectURL: createUrl, revokeObjectURL: revoke});
        const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
        render(<TournamentCelebration place={2} title="Киев 1903" size={2} onClose={vi.fn()} rows={ROWS}
                                      summary={{games: 6, drawPercent: 33, whitePercent: 50}} detailLabel="перф."/>);
        expect(screen.getByTestId('celebration-summary')).toBeInTheDocument();
        expect(screen.getByTestId('celebration-detail-1')).toHaveTextContent('2/0/0');
        fireEvent.click(screen.getByTestId('celebration-csv'));
        expect(createUrl).toHaveBeenCalledTimes(1);
        expect(click).toHaveBeenCalledTimes(1);
        expect(revoke).toHaveBeenCalledWith('blob:x');
    });

    it('браузер без Blob/URL: кнопка CSV молча ничего не делает', () => {
        Object.assign(URL, {createObjectURL: () => {
            throw new Error('unsupported');
        }});
        render(<TournamentCelebration place={5} title="Т" size={2} onClose={vi.fn()} rows={ROWS}/>);
        expect(() => fireEvent.click(screen.getByTestId('celebration-csv'))).not.toThrow();
    });
});
