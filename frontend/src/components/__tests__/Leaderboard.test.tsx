// The leaderboard: loading by category, switching tabs, going to a profile, an empty
// list and a network error.

import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useParams} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import Leaderboard from '../Leaderboard';

const TOP_BY_CATEGORY: Record<string, Array<{ rank: number; username: string; rating: number }>> = {
    blitz: [
        {rank: 1, username: 'Magnus', rating: 2100},
        {rank: 2, username: 'Hikaru', rating: 2050},
        {rank: 3, username: 'Alice B', rating: 1900},
        {rank: 4, username: 'bob', rating: 1500},
    ],
    bullet: [{rank: 1, username: 'Speedy', rating: 2300}],
};

function stubLeaderboardFetch(response: (category: string) => Response | Promise<Response>) {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
        const url = new URL(input.toString(), 'http://test');
        return response(url.searchParams.get('category') ?? '');
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

const okJson = (data: unknown) => ({ok: true, status: 200, json: async () => data}) as Response;

function ProfileStub() {
    const {username} = useParams();
    return <div>Profile: {username}</div>;
}

function renderLeaderboard() {
    return render(
        <MemoryRouter initialEntries={['/leaderboard']}>
            <Routes>
                <Route path="/leaderboard" element={<Leaderboard/>}/>
                <Route path="/profile/:username" element={<ProfileStub/>}/>
                <Route path="/" element={<div>Home</div>}/>
            </Routes>
        </MemoryRouter>,
    );
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('Leaderboard', () => {
    it('by default shows blitz and all players with a rating', async () => {
        const fetchMock = stubLeaderboardFetch((category) => okJson(TOP_BY_CATEGORY[category] ?? []));
        renderLeaderboard();

        expect(await screen.findByText('Magnus')).toBeInTheDocument();
        expect(screen.getByText('2100')).toBeInTheDocument();
        expect(screen.getByText('bob')).toBeInTheDocument();
        // The 4th place — a number, not a medal.
        expect(screen.getByText('4')).toBeInTheDocument();
        expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('category=blitz'), expect.anything());
        expect(screen.getByText(/by Elo rating — blitz/)).toBeInTheDocument();
    });

    it('a category tab reloads the list', async () => {
        const fetchMock = stubLeaderboardFetch((category) => okJson(TOP_BY_CATEGORY[category] ?? []));
        renderLeaderboard();
        await screen.findByText('Magnus');

        fireEvent.click(screen.getByRole('button', {name: 'Bullet'}));

        expect(await screen.findByText('Speedy')).toBeInTheDocument();
        expect(screen.queryByText('Magnus')).not.toBeInTheDocument();
        expect(fetchMock).toHaveBeenLastCalledWith(expect.stringContaining('category=bullet'), expect.anything());
        expect(screen.getByText(/by Elo rating — bullet/)).toBeInTheDocument();
    });

    it('a click on a row opens the player profile with an escaped name', async () => {
        stubLeaderboardFetch((category) => okJson(TOP_BY_CATEGORY[category] ?? []));
        renderLeaderboard();

        fireEvent.click(await screen.findByText('Alice B'));

        expect(await screen.findByText('Profile: Alice B')).toBeInTheDocument();
    });

    it('the "To the board" button leads to the home page', async () => {
        stubLeaderboardFetch(() => okJson([]));
        renderLeaderboard();

        fireEvent.click(screen.getByRole('button', {name: /To the board/}));

        expect(await screen.findByText('Home')).toBeInTheDocument();
    });

    it('an empty answer — a message about an empty list', async () => {
        stubLeaderboardFetch(() => okJson([]));
        renderLeaderboard();

        expect(await screen.findByText('The leaderboard is empty so far.')).toBeInTheDocument();
    });

    it('a server error is shown to the user', async () => {
        stubLeaderboardFetch(() => ({ok: false, status: 500, json: async () => ({})}) as Response);
        renderLeaderboard();

        expect(await screen.findByText('Could not load the leaderboard')).toBeInTheDocument();
        await waitFor(() => expect(screen.getByText('The leaderboard is empty so far.')).toBeInTheDocument());
    });
});
