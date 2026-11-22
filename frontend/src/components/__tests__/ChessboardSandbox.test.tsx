// --- FILE: frontend/src/components/__tests__/ChessboardSandbox.test.tsx ---
// Свободная доска (без партии) в Chessboard.tsx: листание ходов клавишами и кнопками, превращение пешки (выбор,
// отмена, Esc), перетаскивание фигуры (ход, отпускание мимо, по координатам рамки), растягивание доски за уголок
// и сброс двойным щелчком, сохранение оформления в localStorage, разбор позиции из состояния перехода.
// Сеть стабится как в соседних тестах Chessboard*.test.tsx; ход — щелчками через test/boardMoves.ts.

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
    fireEvent.change(await screen.findByLabelText('Позиция в записи FEN'), {target: {value: fen}});
    await act(async () => {
        fireEvent.click(screen.getByRole('button', {name: /Поставить/}));
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

describe('листание ходов на свободной доске', () => {
    it('стрелки и кнопки перематывают позицию; звук играет на каждом шаге', async () => {
        await renderBoard();
        await playMove('e2', 'e4');
        await playMove('e7', 'e5');
        expect(pieceAt('e5')).toBe('bp');

        await key('ArrowLeft');
        expect(pieceAt('e5')).toBeNull();
        expect(pieceAt('e4')).toBe('wp');
        await key('ArrowLeft');
        expect(pieceAt('e4')).toBeNull();
        await key('ArrowLeft');  // уже в начале — ничего не меняется
        expect(pieceAt('e2')).toBe('wp');

        await key('ArrowRight');
        expect(pieceAt('e4')).toBe('wp');
        await key('ArrowRight');
        expect(pieceAt('e5')).toBe('bp');
        await key('ArrowRight');  // уже живая позиция
        expect(pieceAt('e5')).toBe('bp');

        await key('ArrowUp');
        expect(pieceAt('e4')).toBeNull();
        await key('ArrowUp');  // повтор — без изменений
        await key('ArrowDown');
        expect(pieceAt('e5')).toBe('bp');
        await key('ArrowDown');

        fireEvent.click(screen.getByTitle(/В начало партии/));
        expect(pieceAt('e4')).toBeNull();
        fireEvent.click(screen.getByTitle(/Ход вперёд/));
        expect(pieceAt('e4')).toBe('wp');
        fireEvent.click(screen.getByTitle(/Ход вперёд/));
        expect(pieceAt('e5')).toBe('bp');
        fireEvent.click(screen.getByTitle(/Ход назад/));
        expect(pieceAt('e5')).toBeNull();
        fireEvent.click(screen.getByTitle(/К последнему ходу/));
        expect(pieceAt('e5')).toBe('bp');
        expect(vi.mocked(soundEngine.play)).toHaveBeenCalled();
    });

    it('клавиши в поле ввода не листают партию, Esc снимает выбор фигуры', async () => {
        await renderBoard();
        await playMove('e2', 'e4');
        const input = await screen.findByLabelText('Позиция в записи FEN');
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
        expect(pieceAt('e5')).toBeNull();  // выбора не было — щелчок по пустому полю ничего не двигает
    });
});

describe('превращение пешки', () => {
    async function openPromotion() {
        await renderBoard();
        await loadFen(PROMO_FEN);
        await playMove('a7', 'a8');
    }

    it('выбор фигуры в окне ставит её на поле превращения', async () => {
        await openPromotion();
        expect(screen.getByText(/Превращение пешки \(a8\)/)).toBeInTheDocument();
        await act(async () => {
            fireEvent.click(screen.getByTitle('Ладья'));
        });
        expect(pieceAt('a8')).toBe('wr');
    });

    it('отмена крестиком, Esc и щелчок по фону закрывают окно без хода', async () => {
        await openPromotion();
        fireEvent.click(screen.getByRole('button', {name: /Отмена/}));
        expect(screen.queryByText(/Превращение пешки/)).toBeNull();
        expect(pieceAt('a7')).toBe('wp');

        await playMove('a7', 'a8');
        await key('Escape');
        expect(screen.queryByText(/Превращение пешки/)).toBeNull();

        await playMove('a7', 'a8');
        await act(async () => {
            fireEvent.click(boardCell('b3'));  // щелчок по полю при открытом окне закрывает его
        });
        expect(screen.queryByText(/Превращение пешки/)).toBeNull();
        expect(pieceAt('a7')).toBe('wp');
    });
});

describe('перетаскивание фигуры', () => {
    function grab(square: string) {
        const piece = boardCell(square).querySelector('div.relative') as HTMLElement;
        fireEvent.pointerDown(piece, {button: 0, pointerType: 'mouse', clientX: 50, clientY: 50});
    }

    it('отпускание над полем делает ход; призрак фигуры следует за указателем', async () => {
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

    it('если под указателем нет поля, клетка ищется по координатам рамки доски', async () => {
        await renderBoard();
        const frame = document.querySelector('[role="group"]')!.parentElement as HTMLElement;
        vi.spyOn(frame, 'getBoundingClientRect').mockReturnValue(
            {left: 0, top: 0, width: 820, height: 820, right: 820, bottom: 820, x: 0, y: 0, toJSON: () => ({})} as DOMRect,
        );
        grab('d2');
        document.elementsFromPoint = vi.fn(() => []);
        // Внутренняя область 800 px: колонка d — индекс 3 (x 300..400), ряд 4 — индекс 4 сверху (y 400..500).
        await act(async () => {
            fireEvent.pointerUp(window, {clientX: 10 + 350, clientY: 10 + 450});
        });
        expect(pieceAt('d4')).toBe('wp');
    });

    it('отпускание мимо доски ход не делает и снимает призрак', async () => {
        await renderBoard();
        grab('e2');
        document.elementsFromPoint = vi.fn(() => []);
        await act(async () => {
            fireEvent.pointerUp(window, {clientX: -500, clientY: -500});
        });
        expect(pieceAt('e2')).toBe('wp');
        expect(screen.queryByTestId('drag-ghost')).toBeNull();
    });

    it('фигуру не своего цвета на свободной доске не взять', async () => {
        await renderBoard();
        grab('e7');
        expect(screen.queryByTestId('drag-ghost')).toBeNull();
    });
});

describe('размер и оформление доски', () => {
    it('уголок растягивает доску и запоминает размер, двойной щелчок возвращает исходный', async () => {
        await renderBoard();
        const handle = screen.getByTitle(/Потяните, чтобы изменить размер/);
        fireEvent.pointerDown(handle, {clientX: 100, clientY: 100});
        expect(document.body.style.cursor).toBe('nwse-resize');
        fireEvent.pointerMove(window, {clientX: 60, clientY: 60});
        expect(Number(localStorage.getItem('regence_board_size'))).toBeGreaterThan(0);
        fireEvent.pointerUp(window);
        expect(document.body.style.cursor).toBe('');

        fireEvent.doubleClick(handle);
        expect(Number(localStorage.getItem('regence_board_size'))).toBeGreaterThan(0);
    });

    it('позиция из состояния перехода (разбор задачи) ставится на доску', async () => {
        await renderBoard([{pathname: '/', state: {analyzeFen: PROMO_FEN}}]);
        expect(pieceAt('a7')).toBe('wp');
        expect(pieceAt('e2')).toBeNull();
    });

    it('выбор комплекта и темы сохраняется в браузере, щелчок мимо закрывает окно', async () => {
        await renderBoard();
        fireEvent.click(screen.getByTitle('Выбрать комплект фигур, тему и размер доски'));
        const sizeSlider = document.querySelector('input[type="range"]') as HTMLInputElement;
        expect(sizeSlider).not.toBeNull();
        fireEvent.change(sizeSlider, {target: {value: '400'}});
        expect(localStorage.getItem('regence_board_size')).toBe('400');
        fireEvent.click(screen.getByRole('button', {name: /Авто/}));

        // Кнопки наборов и тем — в сетках из пяти колонок окна оформления; запертые (disabled) не трогаем.
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
