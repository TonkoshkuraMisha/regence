// Game library (task 27.1): the collection tree, a collection's games with links to the viewer, paging, search.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {LibraryPage} from '../LibraryPage';
import {childrenOf, searchQuery, totalGames} from '../../../services/library';
import type {LibraryCollection} from '../../../services/library';

const COLLECTIONS: LibraryCollection[] = [
    {id: 1, parent_id: null, name: 'Pawn structures', visibility: 'public', games: 0},
    {id: 2, parent_id: 1, name: 'Isolated pawn', visibility: 'public', games: 10},
    {id: 3, parent_id: 1, name: 'Hedgehog', visibility: 'public', games: 16},
    {id: 4, parent_id: null, name: 'Personal', visibility: 'owner', games: 3},
];

const row = (id: number) => ({id, white: `W${id}`, black: `B${id}`, event: 'Hastings', site: '', date: '', year: 1934,
    result: '1-0', eco: 'D42', opening: '', plies: 40});

function stub() {
    const mock = vi.fn(async (url: string) => {
        const u = String(url);
        let body: unknown = {collections: COLLECTIONS};
        if (u.includes('/collections/2/games')) {
            const offset = Number(new URL(u, 'http://x').searchParams.get('offset'));
            body = {id: 2, name: 'Isolated pawn', total: 60, games: [row(offset + 1)]};
        } else if (u.includes('/games?')) body = {total: 1, games: [row(99)]};
        return {ok: true, json: async () => body} as Response;
    });
    vi.stubGlobal('fetch', mock);
    return mock;
}

afterEach(() => vi.unstubAllGlobals());

describe('game library', () => {
    it('tree: children, the sum of games with nested ones, search parameters', () => {
        expect(childrenOf(COLLECTIONS, null).map((c) => c.id)).toEqual([1, 4]);
        expect(totalGames(COLLECTIONS, 1)).toBe(26);
        expect(searchQuery({player: 'Tal', eco: '', year_from: 1950})).toBe('player=Tal&year_from=1950&limit=50');
    });

    it('a collection expands, games lead to the viewer, paging', async () => {
        const mock = stub();
        await act(async () => render(<MemoryRouter><LibraryPage/></MemoryRouter>));
        expect(screen.getByTestId('library-tree')).toHaveTextContent('Pawn structures');
        expect(screen.queryByTestId('library-collection-2')).toBeNull();
        await act(async () => fireEvent.click(screen.getByTestId('library-collection-1')));
        await act(async () => fireEvent.click(screen.getByTestId('library-collection-2')));
        expect(screen.getByTestId('library-game-1')).toHaveAttribute('href', '/library/game/1');
        expect(screen.getByTestId('library-games')).toHaveTextContent('Isolated pawn');
        await act(async () => fireEvent.click(screen.getByTestId('library-next')));
        expect(screen.getByTestId('library-game-51')).toBeInTheDocument();
        expect(mock.mock.calls.some(([u]) => String(u).includes('/collections/2/games?offset=50'))).toBe(true);
    });

    it('search by player', async () => {
        const mock = stub();
        await act(async () => render(<MemoryRouter><LibraryPage/></MemoryRouter>));
        fireEvent.change(screen.getByTestId('library-player'), {target: {value: 'Botvinnik'}});
        fireEvent.change(screen.getByTestId('library-structure'), {target: {value: 'isolated_pawn'}});
        await act(async () => fireEvent.click(screen.getByTestId('library-search-submit')));
        expect(screen.getByTestId('library-game-99')).toBeInTheDocument();
        expect(mock.mock.calls.some(([u]) => String(u).includes('/games?player=Botvinnik&structure=isolated_pawn'))).toBe(true);
    });

    it('the "miniature" tag (27.5): the checkbox goes into the search, unchecked — it does not', async () => {
        const mock = stub();
        await act(async () => render(<MemoryRouter><LibraryPage/></MemoryRouter>));
        fireEvent.click(screen.getByTestId('library-miniature'));
        await act(async () => fireEvent.click(screen.getByTestId('library-search-submit')));
        expect(mock.mock.calls.some(([u]) => String(u).includes('/games?miniature=true'))).toBe(true);
        fireEvent.click(screen.getByTestId('library-miniature'));
        mock.mockClear();
        await act(async () => fireEvent.click(screen.getByTestId('library-search-submit')));
        expect(mock.mock.calls.some(([u]) => String(u).includes('miniature'))).toBe(false);
    });

    it('the "beautiful" tag (27.5): the checkbox goes into the search', async () => {
        const mock = stub();
        await act(async () => render(<MemoryRouter><LibraryPage/></MemoryRouter>));
        fireEvent.click(screen.getByTestId('library-beautiful'));
        await act(async () => fireEvent.click(screen.getByTestId('library-search-submit')));
        expect(mock.mock.calls.some(([u]) => String(u).includes('/games?beautiful=true'))).toBe(true);
    });

    it('the "theme" tag (27.5): the chosen tactic goes into the search', async () => {
        const mock = stub();
        await act(async () => render(<MemoryRouter><LibraryPage/></MemoryRouter>));
        fireEvent.change(screen.getByTestId('library-theme'), {target: {value: 'fork'}});
        await act(async () => fireEvent.click(screen.getByTestId('library-search-submit')));
        expect(mock.mock.calls.some(([u]) => String(u).includes('/games?theme=fork'))).toBe(true);
    });

    it('a network error is shown', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => {
            throw new Error('offline');
        }));
        await act(async () => render(<MemoryRouter><LibraryPage/></MemoryRouter>));
        expect(screen.getByRole('alert')).toBeInTheDocument();
    });
});

describe('library: links from the course and the repertoire', () => {
    it('?moves= immediately searches for games with this start, ?structure= — with the structure', async () => {
        const mock = stub();
        await act(async () => render(<MemoryRouter initialEntries={['/library?moves=e2e4%20e7e5&structure=saw']}><LibraryPage/></MemoryRouter>));
        expect(mock.mock.calls.some(([u]) => String(u).includes('/games?structure=saw&moves=e2e4+e7e5'))).toBe(true);
        expect(screen.getByTestId('library-game-99')).toBeInTheDocument();
    });

    it('?theme= from the opening explorer searches for games with this tactic; an unknown code is ignored', async () => {
        const mock = stub();
        await act(async () => render(<MemoryRouter initialEntries={['/library?theme=fork']}><LibraryPage/></MemoryRouter>));
        expect(mock.mock.calls.some(([u]) => String(u).includes('/games?theme=fork'))).toBe(true);
        mock.mockClear();
        await act(async () => render(<MemoryRouter initialEntries={['/library?theme=nonsense']}><LibraryPage/></MemoryRouter>));
        expect(mock.mock.calls.some(([u]) => String(u).includes('theme='))).toBe(false);
    });
});
