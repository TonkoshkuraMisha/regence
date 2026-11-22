// Пауза партии с ботом (решение владельца 22.11): в товарищеской партии часы и бот стоят, позиция скрыта плашкой,
// ходы не принимаются; пауза переживает перезагрузку; в партии лестницы паузы нет (иначе можно думать без часов).

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import Chessboard from '../Chessboard';
import {mockFetchRouter} from '../../test/mocks';
import {resetBotCatalogCache} from '../../services/botCatalog';
import {setToken} from '../../services/authToken';
import {openBots} from '../../test/newGame';
import {loadBotGameSnapshot, saveBotGameSnapshot} from '../../services/botGameSnapshot';

vi.mock('../../services/gameSocket', () => ({
    gameSocket: {connect: vi.fn(), disconnect: vi.fn(), send: vi.fn(), on: vi.fn(), off: vi.fn()},
}));
vi.mock('../../services/soundEngine', async (importOriginal) => {
    const actual = await importOriginal<typeof import('../../services/soundEngine')>();
    return {...actual, soundEngine: {play: vi.fn(), isMuted: vi.fn(() => false), toggleMute: vi.fn(() => true)}};
});

const stubApi = () => vi.stubGlobal('fetch', mockFetchRouter({
    '/profile/me': () => ({id: 1, username: 'TestPlayer', blitz_rating: 1500}),
    '/profile/matchmaking/queue': () => [],
    '/profile/games/live': () => [],
    '/profile/games/my-active': () => ({active: false}),
    '/bots/move': () => new Promise(() => {}),   // бот «думает» бесконечно: ход ему не нужен
    '/bots/save-game': () => ({game_id: 1, status: 'finished', result: '1-0'}),
}));

const renderBoard = () => render(<MemoryRouter initialEntries={['/']}><Chessboard/></MemoryRouter>);
const square = (id: string) => document.querySelector(`[data-square="${id}"]`) as HTMLElement;
const hasPiece = (id: string) => square(id).querySelector('img,svg,[data-piece]') !== null;

const SNAPSHOT = {
    username: 'TestPlayer', botId: 'philidor', custom: null, color: 'white' as const, pgn: '1. e4 e5',
    whiteTimeMs: 200000, blackTimeMs: 250000, baseMinutes: 5, incrementSeconds: 0, odds: null,
    ladder: false, tournamentGameId: null, tournamentId: null,
};

beforeEach(() => {
    resetBotCatalogCache();
    setToken('test-token');
    vi.useFakeTimers({shouldAdvanceTime: true});
});
afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    localStorage.clear();
});

describe('пауза партии с ботом', () => {
    it('пауза скрывает позицию и не принимает ходы, продолжение возвращает игру', async () => {
        stubApi();
        renderBoard();
        await openBots();
        await act(async () => fireEvent.click(await screen.findByRole('button', {name: /Белыми/})));

        await act(async () => fireEvent.click(await screen.findByTestId('bot-pause')));
        expect(screen.getByTestId('bot-paused-overlay')).toBeInTheDocument();
        fireEvent.click(square('e2'));
        fireEvent.click(square('e4'));
        expect(hasPiece('e2')).toBe(true);
        expect(hasPiece('e4')).toBe(false);   // ход на паузе не сделан

        await act(async () => fireEvent.click(screen.getByTestId('bot-resume')));
        expect(screen.queryByTestId('bot-paused-overlay')).toBeNull();
        await act(async () => fireEvent.click(square('e2')));
        await act(async () => fireEvent.click(square('e4')));
        expect(hasPiece('e4')).toBe(true);
    });

    it('пауза переживает перезагрузку: снимок с паузой открывается с плашкой, а записанный снимок помнит паузу', async () => {
        stubApi();
        saveBotGameSnapshot({...SNAPSHOT, paused: true}, Date.now() - 3600_000);
        renderBoard();
        expect(await screen.findByTestId('bot-paused-overlay')).toBeInTheDocument();
        await waitFor(() => expect(loadBotGameSnapshot('TestPlayer')?.paused).toBe(true));
        await act(async () => fireEvent.click(screen.getByTestId('bot-resume')));
        await waitFor(() => expect(loadBotGameSnapshot('TestPlayer')?.paused).toBe(false));
    });

    it('в партии лестницы паузы нет', async () => {
        stubApi();
        saveBotGameSnapshot({...SNAPSHOT, ladder: true});
        renderBoard();
        await waitFor(() => expect(hasPiece('e4')).toBe(true));   // партия продолжена
        expect(screen.queryByTestId('bot-pause')).toBeNull();
    });
});
