// Проигрыватель урока, дополнительные пути: все виды действий показа (ход, стрелка, подсветка, призрак, постановка
// фигуры, очистка, пауза), «Показать ещё раз» и повторный просмотр урока после экзамена. Урок собран прямо в тесте,
// чтобы не зависеть от содержимого каталога уроков.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setLanguage} from '../../../i18n';
import type {Lesson, LocalizedText} from '../../../content/lessons/format';
import {LessonPlayer} from '../LessonPlayer';

const text = (value: string): LocalizedText => ({en: value, uk: value, ru: value});
const START = '4k3/8/8/8/8/8/4P3/4K3 w - - 0 1';

const LESSON: Lesson = {
    id: 'test-demo', course: 'test', order: 1, title: text('Demo lesson'), summary: text('Summary'),
    steps: [
        {
            type: 'demo', fen: START, text: text('Watch the demo'),
            actions: [
                {do: 'arrow', from: 'e2', to: 'e4', color: 'green'},
                {do: 'highlight', squares: ['e2']},
                {do: 'ghost', square: 'e5', piece: 'wN'},
                {do: 'pause', ms: 100},
                {do: 'place', square: 'e5', piece: 'wN'},
                {do: 'move', uci: 'e2e4'},
                {do: 'clear'},
            ],
        },
        {type: 'text', fen: START, text: text('Done')},
    ],
    exam: [{
        type: 'choice', fen: START, text: text('Pick the right one'),
        options: [{text: text('Right'), correct: true}, {text: text('Wrong')}],
    }],
};

const pieceOn = (sq: string) =>
    document.querySelector(`[data-square="${sq}"] img:not([aria-hidden])`)?.getAttribute('alt') ?? null;

async function tick(ms: number) {
    await act(async () => {
        await vi.advanceTimersByTimeAsync(ms);
    });
}

beforeEach(() => {
    setLanguage('en', {persist: false});
    vi.useFakeTimers({shouldAdvanceTime: true});
});

afterEach(() => {
    vi.useRealTimers();
    setLanguage('ru', {persist: false});
});

describe('LessonPlayer: показ', () => {
    it('действия показа применяются по очереди; «Показать ещё раз» начинает с исходной позиции', async () => {
        render(<LessonPlayer lesson={LESSON}/>);
        await tick(400);
        expect(screen.getByTestId('board-arrow-e2e4')).toBeInTheDocument();
        await tick(4000);
        // Конь поставлен на e5, пешка пошла e2-e4, оформление очищено.
        expect(pieceOn('e5')).toBe('wn');
        expect(pieceOn('e4')).toBe('wp');
        expect(screen.queryByTestId('board-arrow-e2e4')).toBeNull();

        fireEvent.click(screen.getByRole('button', {name: 'Show again'}));
        expect(pieceOn('e5')).toBeNull();
        expect(pieceOn('e2')).toBe('wp');
        await tick(4000);
        expect(pieceOn('e4')).toBe('wp');
    });
});

describe('LessonPlayer: экзамен и повторный просмотр', () => {
    it('после экзамена «Повторить урок» возвращает к первому шагу', async () => {
        const onFinish = vi.fn();
        render(<LessonPlayer lesson={LESSON} onFinish={onFinish}/>);
        await tick(4000);
        const advance = () => fireEvent.click(screen.getByRole('button', {name: /^(Next|Finish the lesson)$/}));
        advance();
        advance();
        fireEvent.click(screen.getByRole('button', {name: 'Start the exam'}));
        fireEvent.click(screen.getByRole('button', {name: 'Right'}));
        advance();
        expect(onFinish).toHaveBeenCalledWith({examScore: 1, examTotal: 1});
        expect(screen.getByTestId('lesson-done')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', {name: 'Go through again'}));
        expect(screen.getByTestId('lesson-counter')).toHaveTextContent('Step 1 of 2');
    });
});
