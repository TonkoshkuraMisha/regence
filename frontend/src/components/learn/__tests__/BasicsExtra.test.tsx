// Азбука, дополнительные пути: уровень «поставь цель» (мат, неверный ход, сброс), переход к следующему разделу
// и к задачам по темам, сохранение прогресса вошедшим, готовый раздел «все пройдены» и недоступное хранилище оценок.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {BasicsPage, BasicsSectionPage} from '../BasicsPage';
import {BASICS, progressId} from '../../../content/basics/levels';
import {setToken} from '../../../services/authToken';
import {playMove} from '../../../test/boardMoves';

function renderAt(path: string) {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route path="/learn/basics" element={<BasicsPage/>}/>
                <Route path="/learn/basics/:sectionId" element={<BasicsSectionPage/>}/>
                <Route path="/puzzles" element={<div data-testid="puzzles-page"/>}/>
            </Routes>
        </MemoryRouter>,
    );
}

beforeEach(() => {
    localStorage.clear();
    setToken(null);
});

afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    setToken(null);
    localStorage.clear();
});

describe('Азбука: список разделов', () => {
    it('все разделы пройдены на сервере — показана ссылка к темам задач', async () => {
        setToken('jwt');
        vi.stubGlobal('fetch', vi.fn(async () => ({
            ok: true, status: 200,
            json: async () => BASICS.map((s) => ({
                lesson_id: progressId(s.id), step: s.levels.length - 1, steps_total: s.levels.length,
                completed: true, exam_score: null, exam_total: null,
            })),
        } as Response)));
        renderAt('/learn/basics');
        expect(await screen.findByTestId('basics-all-done')).toBeInTheDocument();
        expect(screen.getAllByText(/Пройдено|пройдено/).length).toBeGreaterThan(0);
    });

    it('повреждённые оценки в хранилище не мешают открыть список', () => {
        localStorage.setItem('regence.basics.ratings', '{не json');
        renderAt('/learn/basics');
        expect(screen.getAllByTestId(/^basics-section-/)).toHaveLength(8);
    });
});

describe('Азбука: уровень «поставь цель»', () => {
    it('неверный, но допустимый ход — подсказка и возврат позиции; «заново» сбрасывает уровень', async () => {
        renderAt('/learn/basics/checkMate');
        await playMove('a1', 'a2');
        expect(screen.getByTestId('basics-feedback')).toHaveTextContent('Ход возможен, но задание другое');
        fireEvent.click(screen.getByRole('button', {name: 'Начать уровень заново'}));
        expect(screen.queryByTestId('basics-feedback')).toBeNull();
    });

    it('мат ставит уровень; на последнем уровне раздела — «Раздел пройден» и ссылка на следующий', async () => {
        setToken('jwt');
        const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({ok: true, status: 200, json: async () => ({})} as Response));
        vi.stubGlobal('fetch', fetchMock);
        renderAt('/learn/basics/checkMate');
        // К последнему уровню раздела (мат конём) переходим по номеру; ранние уровни здесь не нужны.
        fireEvent.click(screen.getByRole('button', {name: '8'}));
        await playMove('g5', 'f7');
        expect(screen.getByTestId('basics-result')).toBeInTheDocument();
        expect(screen.getByText('Раздел пройден!')).toBeInTheDocument();
        // Прогресс записан на сервер: раздел завершён.
        const put = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === 'PUT');
        expect(put).toBeTruthy();
        expect(JSON.parse(String((put![1] as RequestInit).body))).toMatchObject({completed: true});
        expect(JSON.parse(localStorage.getItem('regence.basics.ratings') ?? '{}')['checkMate:7']).toBe(3);

        fireEvent.click(screen.getByTestId('basics-next-section'));
        await waitFor(() => expect(screen.getByText('Уровень 1 из 8')).toBeInTheDocument());
    });

    it('последний раздел заканчивается ссылкой к задачам по темам', async () => {
        renderAt('/learn/basics/special');
        fireEvent.click(screen.getByRole('button', {name: '8'}));
        // Ферзь h7 — мат, а не пат: верный ответ на вопрос в последнем уровне.
        fireEvent.click(screen.getByTestId('basics-answer-mate'));
        const link = await screen.findByRole('link', {name: 'К темам задач'});
        fireEvent.click(link);
        expect(await screen.findByTestId('puzzles-page')).toBeInTheDocument();
    });

    it('недоступное хранилище не мешает пройти уровень', async () => {
        vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
            throw new Error('quota');
        });
        renderAt('/learn/basics/special');
        fireEvent.click(screen.getByRole('button', {name: '7'}));
        await act(async () => {
            fireEvent.click(screen.getByTestId('basics-answer-stalemate'));
        });
        expect(screen.getByTestId('basics-result')).toBeInTheDocument();
    });
});
