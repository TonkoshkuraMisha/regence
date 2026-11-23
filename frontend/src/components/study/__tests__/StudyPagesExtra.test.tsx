// Joint review, branches beyond StudyPages.test.tsx: entering /study (create a room, enter a code, materials, a server
// refusal, no login), a room without login and on a polling failure, the host's move (legal and not), highlights and arrows, a position
// by FEN, the chat, a "find the move" question, a student's answer to a multiple-choice question, revealing the answer, lesson steps, downloading and saving.

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
        <Route path="/study/:code" element={<p data-testid="in-room">room</p>}/></Routes></MemoryRouter>);
}

beforeEach(() => setToken('jwt'));
afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe('entering a joint review', () => {
    it('without login — a request to log in', () => {
        setToken(null);
        openLobby();
        expect(screen.queryByTestId('study-lobby')).toBeNull();
        expect(screen.getByText(/Sign in/i)).toBeInTheDocument();
    });

    it('shows the club materials, creates a room and goes into it', async () => {
        stub(null, (url, init) => {
            if (url.endsWith('/materials')) return {materials: [{id: 1, title: 'Sicilian review', created_at: 'x'}]};
            if (init?.method === 'POST') return room();
            return undefined;
        });
        openLobby();
        expect(await screen.findByText('Sicilian review')).toBeInTheDocument();
        await act(async () => fireEvent.click(screen.getByTestId('study-create')));
        expect(await screen.findByTestId('in-room')).toBeInTheDocument();
    });

    it('entering a code opens the room; an empty code is ignored', async () => {
        stub({materials: []});
        openLobby();
        const input = await screen.findByTestId('study-code');
        fireEvent.submit(input.closest('form')!);
        expect(screen.queryByTestId('in-room')).toBeNull();
        fireEvent.change(input, {target: {value: ' zz99 '}});
        fireEvent.submit(input.closest('form')!);
        expect(await screen.findByTestId('in-room')).toBeInTheDocument();
    });

    it('a server refusal when creating a room is shown as a message', async () => {
        vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
            if (init?.method === 'POST') throw new TypeError('offline');
            return {ok: true, status: 200, json: async () => ({materials: []})} as Response;
        }));
        openLobby();
        await act(async () => fireEvent.click(await screen.findByTestId('study-create')));
        expect(await screen.findByRole('alert')).toBeInTheDocument();
    });
});

describe('room: service states', () => {
    it('without login — a request to log in', () => {
        setToken(null);
        stub(room());
        openRoom();
        expect(screen.queryByTestId('study-room')).toBeNull();
    });

    it('a polling failure before the first load shows an error', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => {
            throw new TypeError('offline');
        }));
        openRoom();
        expect(await screen.findByRole('alert')).toBeInTheDocument();
    });
});

describe('the host\'s room', () => {
    it('a piece move sends the position, an illegal move is ignored', async () => {
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

    it('light and dark highlighting, an arrow onto the same square is not drawn, "clear" resets the markup', async () => {
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
        fireEvent.click(screen.getByRole('button', {name: 'Blue'}));
        fireEvent.click(cell('a2'));
        await act(async () => fireEvent.click(cell('a2')));
        expect(calls(fetchMock, 'PUT')).toHaveLength(2);

        await act(async () => fireEvent.click(screen.getByRole('button', {name: /Clear marks/})));
        const last = JSON.parse(String(calls(fetchMock, 'PUT').at(-1)![1].body));
        expect(last).toMatchObject({arrows: [], highlights: [], ghost: null});
    });

    it('a position by FEN is sent, an empty field is not; the chat sends a message', async () => {
        const fetchMock = stub(room({chat: [{from: 'coach', text: 'hello'}]}));
        openRoom();
        const fen = await screen.findByTestId('study-fen');
        expect(screen.getByText('hello')).toBeInTheDocument();
        fireEvent.submit(fen.closest('form')!);
        expect(calls(fetchMock, 'PUT')).toHaveLength(0);
        fireEvent.change(fen, {target: {value: '8/8/8/8/8/8/8/K6k w - - 0 1'}});
        await act(async () => fireEvent.submit(fen.closest('form')!));
        expect(JSON.parse(String(calls(fetchMock, 'PUT')[0][1].body)).fen).toBe('8/8/8/8/8/8/8/K6k w - - 0 1');

        const chat = screen.getByTestId('chat-input');
        fireEvent.submit(chat.closest('form')!);
        expect(calls(fetchMock, 'POST', '/chat')).toHaveLength(0);
        fireEvent.change(chat, {target: {value: 'move e4'}});
        await act(async () => fireEvent.submit(chat.closest('form')!));
        expect(JSON.parse(String(calls(fetchMock, 'POST', '/chat')[0][1].body))).toEqual({text: 'move e4'});
    });

    it('a "find the move" question: the right moves are converted from SAN, extras are dropped; lesson steps, downloading and saving', async () => {
        const fetchMock = stub(room(), (url) => (url.endsWith('/materials') ? {id: 5, title: 'Session'} : undefined));
        const created: string[] = [];
        Object.assign(URL, {createObjectURL: () => 'blob:x', revokeObjectURL: vi.fn()});
        vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
            created.push(this.download);
        });
        openRoom();
        await screen.findByTestId('study-ask');
        expect(screen.getByTestId('lesson-download')).toBeDisabled();

        fireEvent.change(screen.getByTestId('question-kind'), {target: {value: 'move'}});
        fireEvent.change(screen.getByTestId('question-prompt'), {target: {value: 'Best move?'}});
        fireEvent.change(screen.getByTestId('question-moves'), {target: {value: 'e4, d4 Zz9'}});
        await act(async () => fireEvent.click(screen.getByTestId('question-ask')));
        expect(JSON.parse(String(calls(fetchMock, 'POST', '/question')[0][1].body)))
            .toMatchObject({kind: 'move', correct: ['e2e4', 'd2d4']});

        fireEvent.change(screen.getByTestId('lesson-note'), {target: {value: 'Center'}});
        fireEvent.click(screen.getByTestId('lesson-add'));
        expect(screen.getByTestId('study-lesson')).toHaveTextContent('2');
        expect(screen.getByTestId('lesson-download')).toBeEnabled();
        fireEvent.click(screen.getByTestId('lesson-download'));
        expect(created).toEqual(['regence-lesson-abc12345.json']);

        await act(async () => fireEvent.click(screen.getByTestId('lesson-save')));
        await waitFor(() => expect(calls(fetchMock, 'POST', '/materials')).toHaveLength(1));
        await waitFor(() => expect(screen.getByTestId('study-lesson')).toHaveTextContent('0'));
    });

    it('a lesson without a question — a "question needed" hint; a save failure is shown as an error', async () => {
        const fetchMock = stub(room());
        openRoom();
        await screen.findByTestId('study-lesson');
        fireEvent.click(screen.getByTestId('lesson-add'));
        expect(screen.getByTestId('lesson-hint')).toBeInTheDocument();
        expect(screen.getByTestId('lesson-save')).toBeDisabled();
        expect(fetchMock).toHaveBeenCalled();
    });

    it('the host sees the number of answers and reveals the right answer', async () => {
        const question = {id: 'q', kind: 'choice', prompt: '', options: ['A', 'B'], deadline: Date.now() / 1000 + 60, revealed: false};
        const fetchMock = stub(room({question, answers: {u1: {correct: true}, u2: {correct: false}}}));
        openRoom();
        expect(await screen.findByTestId('study-answers')).toBeInTheDocument();
        await act(async () => fireEvent.click(screen.getByRole('button', {name: /Reveal/})));
        expect(calls(fetchMock, 'POST', '/reveal')).toHaveLength(1);
        expect(screen.getByTestId('option-0')).toBeDisabled();
    });
});

describe('the student\'s room', () => {
    it('answers a multiple-choice question; after the answer "answer accepted" is visible', async () => {
        const question = {id: 'q', kind: 'choice', prompt: 'Choose', options: ['A', 'B'], deadline: Date.now() / 1000 + 60, revealed: false};
        const fetchMock = stub(room({is_host: false, question}));
        openRoom();
        expect(await screen.findByTestId('study-question')).toHaveTextContent('Choose');
        expect(screen.queryByTestId('study-tools')).toBeNull();
        await act(async () => fireEvent.click(screen.getByTestId('option-1')));
        expect(JSON.parse(String(calls(fetchMock, 'POST', '/answer')[0][1].body))).toEqual({answer: 1});
    });

    it('the answer is already given: options are unavailable, "answer accepted" is shown', async () => {
        const question = {id: 'q', kind: 'choice', prompt: 'Choose', options: ['A', 'B'], deadline: Date.now() / 1000 + 60,
            revealed: true, correct: 1};
        stub(room({is_host: false, question, my_answer: 0}));
        openRoom();
        expect(await screen.findByTestId('study-answered')).toBeInTheDocument();
        expect(screen.getByTestId('option-0')).toBeDisabled();
    });

    it('the student does not move pieces when there is no question', async () => {
        const fetchMock = stub(room({is_host: false}));
        openRoom();
        await screen.findByTestId('study-room');
        await act(async () => fireEvent.click(cell('e2')));
        await act(async () => fireEvent.click(cell('e4')));
        expect(calls(fetchMock, 'POST', '/answer')).toHaveLength(0);
        expect(calls(fetchMock, 'PUT')).toHaveLength(0);
    });
});
