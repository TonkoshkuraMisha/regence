// --- FILE: frontend/src/components/__tests__/ChampionGames.test.tsx ---
// The champion's game archive: the card, results from the champion's point of view (as White and as Black), dates from
// the PGN, going to the game review, downloading the PGN, pagination and errors.

import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation, useParams} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import ChampionGames, {isChampionName} from '../ChampionGames';

const game = (id: number, white: string, black: string, result: string, extra: Record<string, unknown> = {}) => ({
    game_id: id,
    white_username: white,
    white_rating: 2600,
    black_username: black,
    black_rating: 2600,
    status: 'COMPLETED',
    is_rated: false,
    result,
    pgn_date: '1960.05.07',
    site: 'Moscow',
    eco: 'B10',
    finished_at: null,
    ...extra,
});

const TAL_GAMES = [
    game(1, 'Tal, Mikhail', 'Botvinnik, Mikhail', '1-0'),                 // as White — a win
    game(2, 'Botvinnik, Mikhail', 'Tal, Mikhail', '1-0'),                 // as Black — a loss
    game(3, 'Tseshkovsky, Vitaly', 'Tal, Mikhail', '0-1'),                // as Black — a win ("Vitaly" ≠ Tal)
    game(4, 'TAL, M.', 'Smyslov, Vassily', '0-1', {pgn_date: '1860.??.??'}),  // as White — a loss
    game(5, 'Tal, Mikhail', 'Petrosian, Tigran', '1/2-1/2', {pgn_date: '????.??.??', finished_at: '2026-11-01T12:00:00Z'}),
    game(6, 'Spassky, Boris', 'Tal, Mikhail', '1/2-1/2', {pgn_date: null, site: null, eco: null}),
];

type Reply = { ok: boolean; status?: number; body?: unknown };

function stubGames(reply: (url: string) => Reply) {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
        const r = reply(input.toString());
        return {ok: r.ok, status: r.status ?? (r.ok ? 200 : 500), json: async () => r.body} as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

const okPage = (total: number, items = TAL_GAMES) => () => ({ok: true, body: {total, items}});
// Requests of the game archive (the request of the "Guess the move" buttons to /guess/games follows and is not needed here).
const urls = (fetchMock: ReturnType<typeof stubGames>) => fetchMock.mock.calls.map(([url]) => url.toString())
    .filter((url) => !url.includes('/guess/'));

function GameStub() {
    const {id} = useParams();
    const location = useLocation();
    return <div>Game {id} ({(location.state as any)?.game?.white_username})</div>;
}

function renderChampion(path = '/champions/Tal') {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route path="/champions/:championId" element={<ChampionGames/>}/>
                <Route path="/game/:id" element={<GameStub/>}/>
                <Route path="/" element={<div>Home</div>}/>
            </Routes>
        </MemoryRouter>,
    );
}

const rows = () => screen.getAllByRole('row').slice(1);

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('isChampionName', () => {
    it.each([
        ['Tal, Mikhail', true],
        ['TAL, M.', true],
        ['tal', true],
        ['Tseshkovsky, Vitaly', false],
        ['Natalia Pogonina', false],
        ['Botvinnik, Mikhail', false],
    ])('%s → %s', (username, expected) => {
        expect(isChampionName(username, 'Tal')).toBe(expected);
    });

    it('works with non-Latin letters and compound surnames', () => {
        expect(isChampionName('Świercz, Dariusz', 'Świercz')).toBe(true);
        expect(isChampionName('Ding Liren', 'Ding')).toBe(true);
    });
});

describe('ChampionGames', () => {
    it('shows the champion card and the number of games in the database', async () => {
        stubGames(okPage(130));
        renderChampion();

        expect(screen.getByRole('heading', {name: 'Mikhail Tal'})).toBeInTheDocument();
        expect(screen.getByText('1960–1961')).toBeInTheDocument();
        await waitFor(() => expect(screen.getByText(/Games in the database/).textContent).toContain('130'));
    });

    it('counts the result from the champion\'s point of view — as White and as Black, case-insensitive', async () => {
        stubGames(okPage(6));
        renderChampion();
        await screen.findByText('Tseshkovsky, Vitaly');

        const results = rows().map((row) => within(row).getAllByRole('cell')[3].textContent);
        expect(results).toEqual([
            'Win (1-0)', 'Loss (1-0)', 'Win (0-1)', 'Loss (0-1)', 'Draw (1/2-1/2)', 'Draw (1/2-1/2)',
        ]);
    });

    it('formats the PGN dates: unknown parts are dropped, otherwise — the finish date or a dash', async () => {
        stubGames(okPage(6));
        renderChampion();
        await screen.findByText('Tseshkovsky, Vitaly');

        const dates = rows().map((row) => within(row).getAllByRole('cell')[6].textContent);
        expect(dates).toEqual(['1960.05.07', '1960.05.07', '1960.05.07', '1860', '1 Nov 2026', '—']);
        expect(within(rows()[5]).getAllByRole('cell')[4].textContent).toBe('—');  // no opening code
    });

    it('a click on a row opens the game review and passes its data', async () => {
        stubGames(okPage(6));
        renderChampion();

        fireEvent.click(await screen.findByText('Tseshkovsky, Vitaly'));

        expect(await screen.findByText('Game 3 (Tseshkovsky, Vitaly)')).toBeInTheDocument();
    });

    it('the "Guess the master\'s move" button — only for games with selected moments (14.3)', async () => {
        const fetchMock = stubGames((url) => url.includes('/guess/games')
            ? {ok: true, body: {games: {'3': 77}}} : {ok: true, body: {total: 6, items: TAL_GAMES}});
        renderChampion();
        const link = await screen.findByTestId('champion-guess-3');
        expect(link.getAttribute('href')).toBe('/guess/77?whole=1');  // the whole game
        expect(screen.queryByTestId('champion-guess-1')).not.toBeInTheDocument();
        const guessCall = fetchMock.mock.calls.map(([url]) => url.toString()).find((url) => url.includes('/guess/games'));
        expect(guessCall).toMatch(/ids=1,2,3,4,5,6$/);
    });

    it('downloading the PGN does not open the game review', async () => {
        stubGames(okPage(6));
        renderChampion();
        const links = await screen.findAllByTitle('Download PGN');
        expect(links[0].getAttribute('href')).toMatch(/\/api\/v1\/profile\/games\/1\/pgn$/);

        // A real file download is not needed in jsdom — we cancel the navigation by the link before the browser.
        const cancelNavigation = (e: Event) => e.preventDefault();
        window.addEventListener('click', cancelNavigation, true);
        fireEvent.click(links[0]);
        window.removeEventListener('click', cancelNavigation, true);

        expect(screen.queryByText(/^Game 1/)).not.toBeInTheDocument();
        expect(screen.getByRole('heading', {name: 'Mikhail Tal'})).toBeInTheDocument();
    });

    it('pagination: neighbouring pages, the start and the end, row numbering', async () => {
        const fetchMock = stubGames(okPage(130));
        renderChampion();
        await screen.findByText('Tseshkovsky, Vitaly');

        expect(urls(fetchMock).at(-1)).toMatch(/\/profile\/Tal\/games\?limit=25&offset=0&sort=asc$/);
        expect(screen.getByRole('button', {name: 'First page'})).toBeDisabled();
        expect(screen.getByRole('button', {name: 'Previous page'})).toBeDisabled();

        fireEvent.click(screen.getByRole('button', {name: 'Next page'}));
        await waitFor(() => expect(urls(fetchMock).at(-1)).toContain('limit=25&offset=25'));
        expect(screen.getByRole('button', {name: '2'})).toHaveAttribute('aria-current', 'page');
        await waitFor(() => expect(within(rows()[0]).getAllByRole('cell')[0].textContent).toBe('26'));

        fireEvent.click(screen.getByRole('button', {name: 'Last page'}));
        await waitFor(() => expect(urls(fetchMock).at(-1)).toContain('offset=125'));
        expect(screen.getByRole('button', {name: 'Next page'})).toBeDisabled();
        expect(screen.getByRole('button', {name: '6'})).toHaveAttribute('aria-current', 'page');

        fireEvent.click(screen.getByRole('button', {name: '4'}));
        await waitFor(() => expect(urls(fetchMock).at(-1)).toContain('offset=75'));

        fireEvent.click(screen.getByRole('button', {name: 'First page'}));
        await waitFor(() => expect(urls(fetchMock).at(-1)).toContain('offset=0'));
    });

    it('changing the page size to 50 returns to the first page', async () => {
        const fetchMock = stubGames(okPage(130));
        renderChampion();
        await screen.findByText('Tseshkovsky, Vitaly');
        fireEvent.click(screen.getByRole('button', {name: 'Last page'}));
        await waitFor(() => expect(urls(fetchMock).at(-1)).toContain('offset=125'));

        fireEvent.change(screen.getByLabelText('Games per page'), {target: {value: '50'}});

        await waitFor(() => expect(urls(fetchMock).at(-1)).toContain('limit=50&offset=0'));
        expect(screen.getByRole('button', {name: '1'})).toHaveAttribute('aria-current', 'page');
        expect(screen.getByRole('button', {name: '3'})).toBeInTheDocument();
        expect(screen.queryByRole('button', {name: '4'})).not.toBeInTheDocument();
    });

    it('an empty archive page', async () => {
        stubGames(okPage(0, []));
        renderChampion();
        expect(await screen.findByText('There are no records on this page of the archive.')).toBeInTheDocument();
        expect(screen.queryByRole('button', {name: 'Last page'})).not.toBeInTheDocument();
    });

    it('an unknown champion — an error and a link to the home page', async () => {
        stubGames(okPage(0, []));
        renderChampion('/champions/Nobody');

        expect(screen.getByText(/No player with the id Nobody/)).toBeInTheDocument();
        fireEvent.click(screen.getByRole('link', {name: 'Home'}));
        expect(await screen.findByText('Home')).toBeInTheDocument();
    });

    it('a server error shows its text', async () => {
        stubGames(() => ({ok: false, status: 503, body: {detail: 'The games database is temporarily unavailable'}}));
        renderChampion();

        expect(await screen.findByText('Loading error')).toBeInTheDocument();
        expect(screen.getByText('The games database is temporarily unavailable')).toBeInTheDocument();
    });

    it('a validation error with a detail list does not crash the page', async () => {
        stubGames(() => ({
            ok: false, status: 422,
            body: {detail: [{type: 'less_than_equal', loc: ['query', 'limit'], msg: '…', params: {le: 100}}]},
        }));
        renderChampion();

        expect(await screen.findByText('limit: must be at most 100')).toBeInTheDocument();
    });

    it('a response without a body — the default text', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({
            ok: false, status: 500, json: async () => {
                throw new Error('not json');
            },
        }) as unknown as Response));
        renderChampion();

        expect(await screen.findByText('Could not load the games from the database')).toBeInTheDocument();
    });
});
