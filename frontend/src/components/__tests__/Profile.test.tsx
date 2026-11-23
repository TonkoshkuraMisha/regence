// A player profile: ratings by category, game statistics, a history table with results
// from the profile owner's point of view, navigation and loading errors.

import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation, useParams} from 'react-router-dom';
import {afterEach, beforeAll, describe, expect, it, vi} from 'vitest';
import {cloneElement, type ReactElement} from 'react';
import Profile, {RatingDot, RatingTooltip, formatRatingDelta, toRatingChartPoint} from '../Profile';

// In jsdom the container has zero size and recharts does not draw the chart. We give the chart a fixed
// size — then the points appear in the DOM and can be clicked.
vi.mock('recharts', async (importOriginal) => {
    const actual = await importOriginal<typeof import('recharts')>();
    return {
        ...actual,
        ResponsiveContainer: ({children}: { children: ReactElement }) => (
            <div style={{width: 800, height: 300}}>
                {cloneElement(children as ReactElement<{ width: number; height: number }>, {width: 800, height: 300})}
            </div>
        ),
    };
});

const PROFILE = {
    id: 7,
    username: 'Alice',
    bullet_rating: 1401,
    blitz_rating: 1502,
    rapid_rating: 1603,
    classical_rating: 1704,
    created_at: '2026-03-15T10:00:00Z',
};

const game = (id: number, white: string, black: string, result: string, extra: Record<string, unknown> = {}) => ({
    game_id: id,
    white_username: white,
    white_rating: 1500,
    black_username: black,
    black_rating: 1500,
    status: 'COMPLETED',
    is_rated: true,
    result,
    pgn_date: null,
    site: null,
    eco: null,
    finished_at: '2026-11-01T12:00:00Z',
    ...extra,
});

const GAMES = [
    game(1, 'Alice', 'Bob', '1-0', {eco: 'C20', site: 'Regence', pgn_date: '2026.10.05'}),
    game(2, 'Bob', 'Alice', '1-0'),
    game(3, 'Alice', 'Carol', '1/2-1/2'),
    game(4, 'Dave', 'Alice', '0-1', {pgn_date: '????.??.??'}),
];

type Reply = { ok: boolean; body?: unknown };

const stats = (overrides: Record<string, unknown> = {}) => ({
    total: 0, wins: 0, draws: 0, losses: 0,
    rated_games: {bullet: 0, blitz: 0, rapid: 0, classical: 0},
    ...overrides,
});

const point = (id: number, rating: number, delta: number) => ({
    game_id: id, finished_at: `2026-11-0${id}T12:00:00Z`, rating, delta, color: 'white', result: '1-0',
});

function stubFetch(routes: {
    profile: Reply;
    games?: Reply | ((url: string) => Reply);
    stats?: Reply;
    history?: (url: string) => Reply;
}) {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
        const url = input.toString();
        let reply: Reply;
        if (url.includes('/games?')) {
            const games = routes.games ?? {ok: true, body: {items: []}};
            reply = typeof games === 'function' ? games(url) : games;
        } else if (url.endsWith('/stats')) {
            reply = routes.stats ?? {ok: false};
        } else if (url.includes('/rating-history')) {
            reply = routes.history ? routes.history(url) : {ok: true, body: {points: []}};
        } else {
            reply = routes.profile;
        }
        return {ok: reply.ok, status: reply.ok ? 200 : 404, json: async () => reply.body} as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

function GameStub() {
    const {id} = useParams();
    const location = useLocation();
    return <div>Game {id} ({(location.state as any)?.game?.result})</div>;
}

function renderProfile(path = '/profile/Alice') {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route path="/profile/:targetUsername" element={<Profile/>}/>
                <Route path="/game/:id" element={<GameStub/>}/>
            </Routes>
        </MemoryRouter>,
    );
}

beforeAll(() => {
    // recharts measures the container through ResizeObserver, which jsdom does not have.
    vi.stubGlobal('ResizeObserver', class {
        observe() {
        }

        unobserve() {
        }

        disconnect() {
        }
    });
});

afterEach(() => {
    vi.unstubAllGlobals();
    vi.stubGlobal('ResizeObserver', class {
        observe() {
        }

        unobserve() {
        }

        disconnect() {
        }
    });
});

describe('Profile', () => {
    it('shows four ratings and the registration date', async () => {
        stubFetch({profile: {ok: true, body: PROFILE}});
        renderProfile();

        expect(await screen.findByText('Alice')).toBeInTheDocument();
        for (const rating of ['1401', '1502', '1603', '1704']) {
            expect(screen.getByText(rating)).toBeInTheDocument();
        }
        expect(screen.getByText(/Member since March 15th, 2026/)).toBeInTheDocument();
        expect(screen.getByText('No games yet.')).toBeInTheDocument();
        expect(screen.getByText(/Not enough rated games in this category/)).toBeInTheDocument();
    });

    it('the club ladder is visible when games have been played in it', async () => {
        stubFetch({profile: {ok: true, body: {...PROFILE, ladder: {rating: 1088, games: 4, step: 3, total: 17}}}});
        renderProfile();
        const card = await screen.findByTestId('profile-ladder');
        expect(card).toHaveTextContent('Club ladder');
        expect(card).toHaveTextContent('3/17');
        expect(card).toHaveTextContent('1088');
    });

    it('arena trophies (33.5) — by places; without awards there is no row', async () => {
        stubFetch({profile: {ok: true, body: {...PROFILE, arena_trophies: {gold: 2, silver: 0, bronze: 1}}}});
        const {unmount} = renderProfile();
        const row = await screen.findByTestId('profile-arena-trophies');
        expect(row).toHaveTextContent('Arena trophies');
        expect(screen.getByTestId('profile-trophy-gold')).toHaveTextContent('2');
        expect(screen.getByTestId('profile-trophy-bronze')).toHaveTextContent('1');
        unmount();
        stubFetch({profile: {ok: true, body: {...PROFILE, arena_trophies: {gold: 0, silver: 0, bronze: 0}}}});
        renderProfile();
        await screen.findByText(PROFILE.username);
        expect(screen.queryByTestId('profile-arena-trophies')).toBeNull();
    });

    it('without ladder games there is no card', async () => {
        stubFetch({profile: {ok: true, body: {...PROFILE, ladder: {rating: 1000, games: 0, step: 0, total: 17}}}});
        renderProfile();
        await screen.findByText('Alice');
        expect(screen.queryByTestId('profile-ladder')).toBeNull();
    });

    it('counts wins, draws and losses from the profile owner\'s point of view', async () => {
        stubFetch({
            profile: {ok: true, body: PROFILE},
            games: {ok: true, body: {items: GAMES, total: 4}},
            stats: {ok: true, body: stats({total: 4, wins: 2, draws: 1, losses: 1})},
        });
        renderProfile();

        const rows = await screen.findAllByTitle('Click to view the game');
        expect(rows).toHaveLength(4);
        expect(within(rows[0]).getByText(/Win/)).toBeInTheDocument();     // as White, 1-0
        expect(within(rows[1]).getByText(/Loss/)).toBeInTheDocument();  // as Black, 1-0
        expect(within(rows[2]).getByText(/Draw/)).toBeInTheDocument();
        expect(within(rows[3]).getByText(/Win/)).toBeInTheDocument();     // as Black, 0-1

        // 2 wins out of 4 games.
        expect(screen.getByText('50%')).toBeInTheDocument();
        expect(within(rows[0]).getByText('C20')).toBeInTheDocument();
        expect(within(rows[0]).getByText('2026.10.05')).toBeInTheDocument();
        // An unknown PGN date — the game finish date is taken.
        expect(within(rows[3]).getByText('1 Nov 2026')).toBeInTheDocument();
    });

    it('the opponent\'s name opens their profile', async () => {
        const fetchMock = stubFetch({profile: {ok: true, body: PROFILE}, games: {ok: true, body: {items: GAMES}}});
        renderProfile();

        const rows = await screen.findAllByTitle('Click to view the game');
        fireEvent.click(within(rows[1]).getByText('Bob'));

        await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/api\/v1\/profile\/Bob$/), expect.anything()));
        // A click on the link must not bubble up to the row and open the game viewer.
        expect(screen.queryByText(/^Game 2/)).not.toBeInTheDocument();
    });

    it('a click on a game passes it to the viewer', async () => {
        stubFetch({profile: {ok: true, body: PROFILE}, games: {ok: true, body: {items: GAMES}}});
        renderProfile();

        const rows = await screen.findAllByTitle('Click to view the game');
        fireEvent.click(rows[2]);

        expect(await screen.findByText('Game 3 (1/2-1/2)')).toBeInTheDocument();
    });

    it('the PGN is downloaded by an API link', async () => {
        stubFetch({profile: {ok: true, body: PROFILE}, games: {ok: true, body: {items: GAMES}}});
        renderProfile();

        const links = await screen.findAllByTitle('Download PGN');
        expect(links[0].getAttribute('href')).toMatch(/\/api\/v1\/profile\/games\/1\/pgn$/);
    });

    it('a name with a space is escaped in API requests', async () => {
        const fetchMock = stubFetch({profile: {ok: true, body: {...PROFILE, username: 'Alice B'}}});
        renderProfile('/profile/Alice%20B');

        await screen.findByText('Alice B');
        const urls = fetchMock.mock.calls.map(([url]) => url.toString());
        expect(urls[0]).toMatch(/\/api\/v1\/profile\/Alice%20B$/);
        expect(urls).toContainEqual(expect.stringMatching(/\/profile\/Alice%20B\/games\?limit=30&offset=0$/));
        expect(urls).toContainEqual(expect.stringMatching(/\/profile\/Alice%20B\/stats$/));
        expect(urls.every((url) => !url.includes('Alice B'))).toBe(true);
    });

    it('a non-existent player — an error message', async () => {
        // The server answer for an unknown name (src/api/profile.py): the code user_not_found with the name.
        stubFetch({profile: {ok: false, body: {detail: {code: 'user_not_found', params: {username: 'Alice'}, message: 'User not found'}}}});
        renderProfile();

        expect(await screen.findByText('User Alice not found')).toBeInTheDocument();
    });

    it('a failure to load games does not break the profile', async () => {
        stubFetch({profile: {ok: true, body: PROFILE}, games: {ok: false}});
        renderProfile();

        expect(await screen.findByText('Alice')).toBeInTheDocument();
        expect(screen.getByText('No games yet.')).toBeInTheDocument();
    });
});

describe('Profile: totals and rating history', () => {
    it('totals come from the server for all games, not from the loaded page', async () => {
        stubFetch({
            profile: {ok: true, body: PROFILE},
            games: {ok: true, body: {items: GAMES, total: 120}},
            stats: {ok: true, body: stats({total: 120, wins: 90, draws: 10, losses: 20})},
        });
        renderProfile();

        await screen.findAllByTitle('Click to view the game');
        expect(screen.getByText('120')).toBeInTheDocument();
        expect(screen.getByText('75%')).toBeInTheDocument();
        expect(screen.getByText('90')).toBeInTheDocument();
        expect(screen.getByText('20')).toBeInTheDocument();
    });

    it('the chart of the category with the most games played is shown first', async () => {
        const fetchMock = stubFetch({
            profile: {ok: true, body: PROFILE},
            stats: {ok: true, body: stats({rated_games: {bullet: 3, blitz: 5, rapid: 40, classical: 0}})},
            history: () => ({ok: true, body: {points: [point(1, 1610, 10), point(2, 1603, -7)]}}),
        });
        renderProfile();

        expect(await screen.findByText('Rating trend — rapid')).toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Rapid'})).toHaveAttribute('aria-pressed', 'true');
        await waitFor(() => {
            const urls = fetchMock.mock.calls.map(([url]) => url.toString());
            expect(urls.some((url) => url.endsWith('/rating-history?category=rapid'))).toBe(true);
        });
        expect(screen.queryByText(/Not enough rated games/)).not.toBeInTheDocument();
    });

    it('switching the category requests its history', async () => {
        const fetchMock = stubFetch({
            profile: {ok: true, body: PROFILE},
            stats: {ok: true, body: stats()},
        });
        renderProfile();
        await screen.findByText('Rating trend — blitz');

        fireEvent.click(screen.getByRole('button', {name: 'Bullet'}));

        expect(await screen.findByText('Rating trend — bullet')).toBeInTheDocument();
        await waitFor(() => {
            const urls = fetchMock.mock.calls.map(([url]) => url.toString());
            expect(urls.some((url) => url.endsWith('/rating-history?category=bullet'))).toBe(true);
        });
    });

    it('the game history is paged', async () => {
        const fetchMock = stubFetch({
            profile: {ok: true, body: PROFILE},
            stats: {ok: true, body: stats({total: 65})},
            games: (url) => ({
                ok: true,
                body: {total: 65, items: [game(url.includes('offset=30') ? 31 : 1, 'Alice', 'Bob', '1-0')]},
            }),
        });
        renderProfile();

        expect(await screen.findByText(/Page 1 of 3 · 65 in total/)).toBeInTheDocument();
        expect(screen.getByRole('button', {name: /Newer/})).toBeDisabled();

        fireEvent.click(screen.getByRole('button', {name: /Older/}));

        expect(await screen.findByText(/Page 2 of 3/)).toBeInTheDocument();
        const urls = fetchMock.mock.calls.map(([url]) => url.toString());
        expect(urls.some((url) => url.endsWith('/games?limit=30&offset=30'))).toBe(true);
    });

    it('without totals from the server the page stays working', async () => {
        stubFetch({profile: {ok: true, body: PROFILE}, games: {ok: true, body: {items: GAMES, total: 4}}});
        renderProfile();

        await screen.findAllByTitle('Click to view the game');
        expect(screen.getByText('Rating trend — blitz')).toBeInTheDocument();
        expect(screen.queryByText(/Page \d/)).not.toBeInTheDocument();
    });
});

describe('Profile: rating chart', () => {
    it('a chart point holds the game, the date and time and the rating change', () => {
        const point = toRatingChartPoint({
            game_id: 12, finished_at: '2026-11-01T12:30:00Z', rating: 1512, delta: 12,
        });

        expect(point).toMatchObject({game_id: 12, rating: 1512, delta: 12, date: '1 Nov'});
        expect(point.fullDate).toMatch(/^November 1st, 2026, \d{2}:\d{2}$/);
    });

    it.each([[12, '+12'], [-10, '-10'], [0, '0']])('a change of %d is shown as %s', (delta, text) => {
        expect(formatRatingDelta(delta)).toBe(text);
    });

    it('the tooltip shows the date, the rating and the change per game', () => {
        const point = {game_id: 3, rating: 1490, delta: -10, date: '2 Nov', fullDate: '2 November 2026, 18:05'};
        render(<RatingTooltip active payload={[{payload: point}]}/>);

        expect(screen.getByText('2 November 2026, 18:05')).toBeInTheDocument();
        expect(screen.getByText(/1490/).textContent).toBe('1490 (-10)');
    });

    it('without an active point there is no tooltip', () => {
        const {container} = render(<RatingTooltip active={false} payload={[]}/>);
        expect(container).toBeEmptyDOMElement();
    });

    it('a click on a point reports the game id', () => {
        const onSelect = vi.fn();
        const point = {game_id: 42, rating: 1500, delta: 8, date: '1 Nov', fullDate: '1 November 2026, 12:00'};
        render(<svg><RatingDot cx={10} cy={20} payload={point} onSelect={onSelect}/></svg>);

        fireEvent.click(screen.getByRole('link', {name: /rating 1500/}));
        expect(onSelect).toHaveBeenCalledWith(42);
    });

    it('a click on a point on the profile page opens the review of that game', async () => {
        stubFetch({
            profile: {ok: true, body: PROFILE},
            stats: {ok: true, body: stats({rated_games: {bullet: 0, blitz: 2, rapid: 0, classical: 0}})},
            history: () => ({ok: true, body: {points: [point(1, 1510, 10), point(2, 1502, -8)]}}),
        });
        renderProfile();

        const dots = await screen.findAllByRole('link', {name: /^Game of /});
        expect(dots).toHaveLength(2);
        expect(dots[1]).toHaveAccessibleName(/rating 1502/);

        fireEvent.click(dots[1]);

        expect(await screen.findByText(/^Game 2/)).toBeInTheDocument();
    });
});

