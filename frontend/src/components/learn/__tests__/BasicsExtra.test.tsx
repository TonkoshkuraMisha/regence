// Alphabet course, extra paths: the "place the target" level (mate, a wrong move, reset), moving on to the next section
// and to the puzzles by theme, saving progress for a logged-in user, the finished "all done" section and unavailable rating storage.

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

describe('Alphabet: section list', () => {
    it('all sections are completed on the server — a link to the puzzle themes is shown', async () => {
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
        expect(screen.getAllByText(/done/).length).toBeGreaterThan(0);
    });

    it('corrupted ratings in storage do not prevent opening the list', () => {
        localStorage.setItem('regence.basics.ratings', '{not json');
        renderAt('/learn/basics');
        expect(screen.getAllByTestId(/^basics-section-/)).toHaveLength(8);
    });
});

describe('Alphabet: the "place the target" level', () => {
    it('a wrong but legal move — a hint and the position is restored; "restart" resets the level', async () => {
        renderAt('/learn/basics/checkMate');
        await playMove('a1', 'a2');
        expect(screen.getByTestId('basics-feedback')).toHaveTextContent('That move is legal, but the task is different');
        fireEvent.click(screen.getByRole('button', {name: 'Restart the level'}));
        expect(screen.queryByTestId('basics-feedback')).toBeNull();
    });

    it('mate completes the level; on the last level of a section — "Section complete" and a link to the next one', async () => {
        setToken('jwt');
        const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({ok: true, status: 200, json: async () => ({})} as Response));
        vi.stubGlobal('fetch', fetchMock);
        renderAt('/learn/basics/checkMate');
        // We go to the last level of the section (knight mate) by number; the earlier levels are not needed here.
        fireEvent.click(screen.getByRole('button', {name: '8'}));
        await playMove('g5', 'f7');
        expect(screen.getByTestId('basics-result')).toBeInTheDocument();
        expect(screen.getByText('Section complete!')).toBeInTheDocument();
        // Progress is recorded on the server: the section is finished.
        const put = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === 'PUT');
        expect(put).toBeTruthy();
        expect(JSON.parse(String((put![1] as RequestInit).body))).toMatchObject({completed: true});
        expect(JSON.parse(localStorage.getItem('regence.basics.ratings') ?? '{}')['checkMate:7']).toBe(3);

        fireEvent.click(screen.getByTestId('basics-next-section'));
        await waitFor(() => expect(screen.getByText('Level 1 of 8')).toBeInTheDocument());
    });

    it('the last section ends with a link to the puzzles by theme', async () => {
        renderAt('/learn/basics/special');
        fireEvent.click(screen.getByRole('button', {name: '8'}));
        // Queen h7 is mate, not stalemate: the right answer to the question on the last level.
        fireEvent.click(screen.getByTestId('basics-answer-mate'));
        const link = await screen.findByRole('link', {name: 'To puzzle themes'});
        fireEvent.click(link);
        expect(await screen.findByTestId('puzzles-page')).toBeInTheDocument();
    });

    it('unavailable storage does not prevent completing a level', async () => {
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
