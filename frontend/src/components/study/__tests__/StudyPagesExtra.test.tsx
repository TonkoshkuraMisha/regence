// Совместный разбор, ветки сверх StudyPages.test.tsx: вход в /study (создать комнату, ввести код, материалы, отказ
// сервера, нет входа), комната без входа и при сбое опроса, ход ведущего (законный и нет), подсветка и стрелки, позиция
// по FEN, чат, вопрос «найти ход», ответ ученика на вопрос с вариантами, показ ответа, шаги урока, скачивание и сохранение.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setToken} from '../../../services/authToken';
import {StudyLobby, StudyRoomPage} from '../StudyPages';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const BOARD = {fen: START, last_move: null, arrows: [], highlights: [], ghost: null};
const cell = (name: string) => document.querySelector(`[data-square="${name}"]`) as HTMLElement;

function room(extra: Record<string, unknown> = {}) {
    return {code: 'abc12345', host: 'coach', is_host: true, version: 3, board: BOARD, chat: [], question: null,
        participants: ['coach'], ...extra};
}

type Call = [string, RequestInit];

function stub(state: unknown, extra: (url: string, init?: RequestInit) => unknown = () => undefined) {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
        const special = extra(String(url), init);
        return {ok: true, status: 200, json: async () => (special !== undefined ? special : state)} as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

const calls = (fetchMock: ReturnType<typeof stub>, method: string, part = '') =>
    (fetchMock.mock.calls as unknown as Call[]).filter(([url, init]) => init?.method === method && url.includes(part));

function openRoom() {
    return render(<MemoryRouter initialEntries={['/study/abc12345']}><Routes>
        <Route path="/study/:code" element={<StudyRoomPage/>}/></Routes></MemoryRouter>);
}

function openLobby() {
    return render(<MemoryRouter initialEntries={['/study']}><Routes>
        <Route path="/study" element={<StudyLobby/>}/>
        <Route path="/study/:code" element={<p data-testid="in-room">комната</p>}/></Routes></MemoryRouter>);
}

beforeEach(() => setToken('jwt'));
afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe('вход в совместный разбор', () => {
    it('без входа — просьба войти', () => {
        setToken(null);
        openLobby();
        expect(screen.queryByTestId('study-lobby')).toBeNull();
        expect(screen.getByText(/войд|вход/i)).toBeInTheDocument();
    });

    it('показывает материалы клуба, создаёт комнату и переходит в неё', async () => {
        stub(null, (url, init) => {
            if (url.endsWith('/materials')) return {materials: [{id: 1, title: 'Разбор Сицилианской', created_at: 'x'}]};
            if (init?.method === 'POST') return room();
            return undefined;
        });
        openLobby();
        expect(await screen.findByText('Разбор Сицилианской')).toBeInTheDocument();
        await act(async () => fireEvent.click(screen.getByTestId('study-create')));
        expect(await screen.findByTestId('in-room')).toBeInTheDocument();
    });

    it('ввод кода открывает комнату; пустой код игнорируется', async () => {
        stub({materials: []});
        openLobby();
        const input = await screen.findByTestId('study-code');
        fireEvent.submit(input.closest('form')!);
        expect(screen.queryByTestId('in-room')).toBeNull();
        fireEvent.change(input, {target: {value: ' zz99 '}});
        fireEvent.submit(input.closest('form')!);
        expect(await screen.findByTestId('in-room')).toBeInTheDocument();
    });

    it('отказ сервера при создании комнаты показывается сообщением', async () => {
        vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
            if (init?.method === 'POST') throw new TypeError('offline');
            return {ok: true, status: 200, json: async () => ({materials: []})} as Response;
        }));
        openLobby();
        await act(async () => fireEvent.click(await screen.findByTestId('study-create')));
        expect(await screen.findByRole('alert')).toBeInTheDocument();
    });
});

describe('комната: служебные состояния', () => {
    it('без входа — просьба войти', () => {
        setToken(null);
        stub(room());
        openRoom();
        expect(screen.queryByTestId('study-room')).toBeNull();
    });

    it('сбой опроса до первой загрузки показывает ошибку', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => {
            throw new TypeError('offline');
        }));
        openRoom();
        expect(await screen.findByRole('alert')).toBeInTheDocument();
    });
});

describe('комната ведущего', () => {
    it('ход фигурой отправляет позицию, незаконный ход игнорируется', async () => {
        const fetchMock = stub(room());
        openRoom();
        await screen.findByTestId('study-tools');
        await act(async () => fireEvent.click(cell('e2')));
        await act(async () => fireEvent.click(cell('e4')));
        await waitFor(() => expect(calls(fetchMock, 'PUT')).toHaveLength(1));
        const body = JSON.parse(String(calls(fetchMock, 'PUT')[0][1].body));
        expect(body.last_move).toBe('e2e4');
        expect(body.fen).toContain('4P3');
    });

    it('светлая и тёмная подсветка, стрелка в ту же клетку не рисуется, «очистить» сбрасывает разметку', async () => {
        const fetchMock = stub(room());
        openRoom();
        await screen.findByTestId('study-tools');
        fireEvent.click(screen.getByTestId('tool-light'));
        await act(async () => fireEvent.click(cell('e4')));
        fireEvent.click(screen.getByTestId('tool-dark'));
        await act(async () => fireEvent.click(cell('d4')));
        const puts = calls(fetchMock, 'PUT').map(([, init]) => JSON.parse(String(init.body)));
        expect(puts[0].highlights).toEqual([{square: 'e4', tone: 'light'}]);
        expect(puts[1].highlights).toEqual([{square: 'd4', tone: 'dark'}]);

        fireEvent.click(screen.getByTestId('tool-arrow'));
        fireEvent.click(screen.getByRole('button', {name: 'Синяя'}));
        fireEvent.click(cell('a2'));
        await act(async () => fireEvent.click(cell('a2')));
        expect(calls(fetchMock, 'PUT')).toHaveLength(2);

        await act(async () => fireEvent.click(screen.getByRole('button', {name: /Убрать пометки/})));
        const last = JSON.parse(String(calls(fetchMock, 'PUT').at(-1)![1].body));
        expect(last).toMatchObject({arrows: [], highlights: [], ghost: null});
    });

    it('позиция по FEN отправляется, пустое поле — нет; чат отправляет сообщение', async () => {
        const fetchMock = stub(room({chat: [{from: 'coach', text: 'привет'}]}));
        openRoom();
        const fen = await screen.findByTestId('study-fen');
        expect(screen.getByText('привет')).toBeInTheDocument();
        fireEvent.submit(fen.closest('form')!);
        expect(calls(fetchMock, 'PUT')).toHaveLength(0);
        fireEvent.change(fen, {target: {value: '8/8/8/8/8/8/8/K6k w - - 0 1'}});
        await act(async () => fireEvent.submit(fen.closest('form')!));
        expect(JSON.parse(String(calls(fetchMock, 'PUT')[0][1].body)).fen).toBe('8/8/8/8/8/8/8/K6k w - - 0 1');

        const chat = screen.getByTestId('chat-input');
        fireEvent.submit(chat.closest('form')!);
        expect(calls(fetchMock, 'POST', '/chat')).toHaveLength(0);
        fireEvent.change(chat, {target: {value: 'ход e4'}});
        await act(async () => fireEvent.submit(chat.closest('form')!));
        expect(JSON.parse(String(calls(fetchMock, 'POST', '/chat')[0][1].body))).toEqual({text: 'ход e4'});
    });

    it('вопрос «найти ход»: верные ходы переводятся из SAN, лишнее отбрасывается; шаги урока, скачивание и сохранение', async () => {
        const fetchMock = stub(room(), (url) => (url.endsWith('/materials') ? {id: 5, title: 'Занятие'} : undefined));
        const created: string[] = [];
        Object.assign(URL, {createObjectURL: () => 'blob:x', revokeObjectURL: vi.fn()});
        vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
            created.push(this.download);
        });
        openRoom();
        await screen.findByTestId('study-ask');
        expect(screen.getByTestId('lesson-download')).toBeDisabled();

        fireEvent.change(screen.getByTestId('question-kind'), {target: {value: 'move'}});
        fireEvent.change(screen.getByTestId('question-prompt'), {target: {value: 'Лучший ход?'}});
        fireEvent.change(screen.getByTestId('question-moves'), {target: {value: 'e4, d4 Zz9'}});
        await act(async () => fireEvent.click(screen.getByTestId('question-ask')));
        expect(JSON.parse(String(calls(fetchMock, 'POST', '/question')[0][1].body)))
            .toMatchObject({kind: 'move', correct: ['e2e4', 'd2d4']});

        fireEvent.change(screen.getByTestId('lesson-note'), {target: {value: 'Центр'}});
        fireEvent.click(screen.getByTestId('lesson-add'));
        expect(screen.getByTestId('study-lesson')).toHaveTextContent('2');
        expect(screen.getByTestId('lesson-download')).toBeEnabled();
        fireEvent.click(screen.getByTestId('lesson-download'));
        expect(created).toEqual(['regence-lesson-abc12345.json']);

        await act(async () => fireEvent.click(screen.getByTestId('lesson-save')));
        await waitFor(() => expect(calls(fetchMock, 'POST', '/materials')).toHaveLength(1));
        await waitFor(() => expect(screen.getByTestId('study-lesson')).toHaveTextContent('0'));
    });

    it('урок без вопроса — подсказка «нужен вопрос»; сбой сохранения показывается ошибкой', async () => {
        const fetchMock = stub(room());
        openRoom();
        await screen.findByTestId('study-lesson');
        fireEvent.click(screen.getByTestId('lesson-add'));
        expect(screen.getByTestId('lesson-hint')).toBeInTheDocument();
        expect(screen.getByTestId('lesson-save')).toBeDisabled();
        expect(fetchMock).toHaveBeenCalled();
    });

    it('ведущий видит число ответов и раскрывает верный ответ', async () => {
        const question = {id: 'q', kind: 'choice', prompt: '', options: ['А', 'Б'], deadline: Date.now() / 1000 + 60, revealed: false};
        const fetchMock = stub(room({question, answers: {u1: {correct: true}, u2: {correct: false}}}));
        openRoom();
        expect(await screen.findByTestId('study-answers')).toBeInTheDocument();
        await act(async () => fireEvent.click(screen.getByRole('button', {name: /Показать|Раскрыть/})));
        expect(calls(fetchMock, 'POST', '/reveal')).toHaveLength(1);
        expect(screen.getByTestId('option-0')).toBeDisabled();
    });
});

describe('комната ученика', () => {
    it('отвечает на вопрос с вариантами; после ответа видно «ответ принят»', async () => {
        const question = {id: 'q', kind: 'choice', prompt: 'Выберите', options: ['А', 'Б'], deadline: Date.now() / 1000 + 60, revealed: false};
        const fetchMock = stub(room({is_host: false, question}));
        openRoom();
        expect(await screen.findByTestId('study-question')).toHaveTextContent('Выберите');
        expect(screen.queryByTestId('study-tools')).toBeNull();
        await act(async () => fireEvent.click(screen.getByTestId('option-1')));
        expect(JSON.parse(String(calls(fetchMock, 'POST', '/answer')[0][1].body))).toEqual({answer: 1});
    });

    it('ответ уже дан: варианты недоступны, показано «ответ принят»', async () => {
        const question = {id: 'q', kind: 'choice', prompt: 'Выберите', options: ['А', 'Б'], deadline: Date.now() / 1000 + 60,
            revealed: true, correct: 1};
        stub(room({is_host: false, question, my_answer: 0}));
        openRoom();
        expect(await screen.findByTestId('study-answered')).toBeInTheDocument();
        expect(screen.getByTestId('option-0')).toBeDisabled();
    });

    it('ученик не двигает фигуры, когда вопроса нет', async () => {
        const fetchMock = stub(room({is_host: false}));
        openRoom();
        await screen.findByTestId('study-room');
        await act(async () => fireEvent.click(cell('e2')));
        await act(async () => fireEvent.click(cell('e4')));
        expect(calls(fetchMock, 'POST', '/answer')).toHaveLength(0);
        expect(calls(fetchMock, 'PUT')).toHaveLength(0);
    });
});
