// Arenas (task 17.2): the list, joining, a pair search with a retry and a move to the board, a table with "fire", the lobby announcement.

import {act, fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setToken} from '../../../services/authToken';
import {clock, controlLabel, secondsUntil} from '../../../services/arenas';
import {ArenaBanner, ArenaPage, ArenasPage, WAIT_POLL_MS} from '../ArenaPages';
import {notificationText} from '../../social/SocialHeader';
import {notificationLink} from '../../../services/social';
import type {AppNotification} from '../../../services/social';
import {makeI18n} from '../../../i18n';
import {soundEngine} from '../../../services/soundEngine';

const SOON = new Date(Date.now() + 40 * 60_000).toISOString();
const RUNNING = {id: 3, schedule_key: 'blitz-3+2', base_time_ms: 180000, increment_ms: 2000, starts_at: new Date().toISOString(),
    ends_at: SOON, status: 'running'};

function Probe() {
    const location = useLocation();
    return <pre data-testid="probe">{location.pathname}</pre>;
}

function routes(path: string) {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route path="/arenas" element={<ArenasPage/>}/>
                <Route path="/arenas/:arenaId" element={<ArenaPage/>}/>
                <Route path="/" element={<Probe/>}/>
            </Routes>
        </MemoryRouter>,
    );
}

beforeEach(() => {
    setToken('jwt');
    vi.useFakeTimers({shouldAdvanceTime: true});
});
afterEach(() => {
    setToken(null);
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

describe('arenas', () => {
    it('time and control', () => {
        expect(controlLabel({base_time_ms: 180000, increment_ms: 2000})).toBe('3+2');
        expect(clock(125)).toBe('2:05');
        expect(clock(3725)).toBe('1:02:05');
        expect(secondsUntil(new Date(1000).toISOString(), 5000)).toBe(0);
    });

    it('the arena list', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => ({arenas: [{...RUNNING, players: 12}]})} as Response)));
        routes('/arenas');
        expect(await screen.findByTestId('arena-3')).toHaveTextContent('Arena 3+2');
        expect(screen.getByTestId('arena-3')).toHaveTextContent('players: 12');
    });

    it('joining, a search with a retry and a move to the board when the game is created', async () => {
        let joined = false;
        let readyCalls = 0;
        const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
            const u = String(url);
            let body: unknown;
            if (u.endsWith('/join')) {
                joined = true;
                body = {joined: true};
            } else if (u.endsWith('/ready')) {
                readyCalls += 1;
                body = readyCalls < 2 ? {waiting: true} : {game_id: 77};
            } else {
                body = {...RUNNING, standings: [{place: 1, username: 'magnus', score: 6, games: 3, wins: 3, fire: true, rating: 2800}],
                    me: {joined, waiting: false, current_game_id: null}};
            }
            return {ok: true, status: 200, json: async () => body, method: init?.method} as unknown as Response;
        });
        vi.stubGlobal('fetch', fetchMock);
        routes('/arenas/3');
        expect(await screen.findByTestId('arena-standings')).toHaveTextContent('magnus');
        expect(screen.getByLabelText('On fire: points are doubled')).toBeInTheDocument();
        await act(async () => fireEvent.click(screen.getByTestId('arena-join')));
        fireEvent.click(await screen.findByTestId('arena-play'));
        expect(await screen.findByTestId('arena-searching')).toBeInTheDocument();
        await act(async () => {
            vi.advanceTimersByTime(WAIT_POLL_MS + 100);
        });
        expect(await screen.findByTestId('probe')).toHaveTextContent('/');
        expect(readyCalls).toBeGreaterThanOrEqual(2);
    });

    it('the lobby announcement', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => ({arena: RUNNING})} as Response)));
        render(<MemoryRouter><ArenaBanner/></MemoryRouter>);
        expect(await screen.findByTestId('arena-banner')).toHaveAttribute('href', '/arenas/3');
    });
});

describe('Swiss between people', () => {
    it('a name with rounds, "round N of M", no "Play" button — the game opens by itself', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => ({
            ...RUNNING, format: 'swiss', rounds: 5, current_round: 2, standings: [],
            me: {joined: true, waiting: false, current_game_id: null},
        })} as Response)));
        routes('/arenas/3');
        expect(await screen.findByText('Swiss 3+2, 5 rounds')).toBeInTheDocument();
        expect(screen.getByTestId('arena-timing')).toHaveTextContent('round 2 of 5');
        expect(screen.queryByTestId('arena-play')).toBeNull();
        expect(screen.getByTestId('swiss-waiting')).toBeInTheDocument();
    });
});

describe('fair end of the arena (33.1)', () => {
    it('before the last start — a countdown; after — finishing and no "Play" button; performance in the table', async () => {
        const lastStart = new Date(Date.now() + 10 * 60_000).toISOString();
        const standings = [{place: 1, username: 'misha', score: 4, games: 2, wins: 2, fire: true, rating: 1500, performance: 1900}];
        let current: Record<string, unknown> = {...RUNNING, last_start_at: lastStart, open_games: 0, standings,
            me: {joined: true, waiting: false, current_game_id: null}};
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => current} as Response)));
        const view = routes('/arenas/3');
        expect(await screen.findByTestId('arena-timing')).toHaveTextContent('last start in 10:0');
        expect(screen.getByTestId('arena-play')).toBeInTheDocument();
        expect(screen.getByTestId('arena-perf-misha')).toHaveTextContent('1900');
        view.unmount();

        current = {...current, status: 'closing', open_games: 2};
        routes('/arenas/3');
        expect(await screen.findByTestId('arena-timing')).toHaveTextContent('final games being played: 2');
        expect(screen.getByTestId('arena-closing')).toBeInTheDocument();
        expect(screen.queryByTestId('arena-play')).toBeNull();
    });
});

describe('berserk (33.3)', () => {
    it('the berserk rule is shown only where it is available', async () => {
        let current: Record<string, unknown> = {...RUNNING, berserk: true, open_games: 0, standings: [], me: null};
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => current} as Response)));
        const view = routes('/arenas/3');
        expect(await screen.findByTestId('arena-berserk-rule')).toHaveTextContent('Berserk');
        view.unmount();

        current = {...current, berserk: false};
        routes('/arenas/3');
        await screen.findByTestId('arena-timing');
        expect(screen.queryByTestId('arena-berserk-rule')).toBeNull();
    });
});

describe('conference schedule and reminders (33.4)', () => {
    const IN_TEN_MINUTES = new Date(Date.now() + 10 * 60_000).toISOString();
    const EVENING = {...RUNNING, id: 4, schedule_key: 'central:evening-5+3', base_time_ms: 300000, increment_ms: 3000,
        status: 'scheduled', starts_at: IN_TEN_MINUTES, conference: 'central', evening: true};

    it('the list shows the arena\'s conference and "evening"; an unknown conference does not get into the name', async () => {
        const arenas = [{...EVENING, players: 0}, {...RUNNING, conference: 'northern', players: 3},
            {...RUNNING, id: 5, conference: 'lunar', players: 0}];
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => ({arenas})} as Response)));
        routes('/arenas');
        expect(await screen.findByTestId('arena-4')).toHaveTextContent('Evening arena 5+3 · Central conference');
        expect(screen.getByTestId('arena-3')).toHaveTextContent('Arena 3+2 · Northern conference');
        expect(screen.getByTestId('arena-5')).toHaveTextContent(/^Arena 3\+2(?! ·)/);
        expect(screen.getByTestId('arenas-conference-note')).toHaveTextContent('five world conferences');
    });

    it('the lobby announcement: a short name and a timer to the start', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => ({arena: EVENING})} as Response)));
        render(<MemoryRouter><ArenaBanner/></MemoryRouter>);
        const banner = await screen.findByTestId('arena-banner');
        expect(banner).toHaveTextContent('Evening arena 5+3');
        expect(banner).not.toHaveTextContent('conference');
        expect(banner).toHaveTextContent(/starts in (10:00|9:5\d)/);
    });

    it('"remind" for a not yet started arena: a request, a mark and a cancellation', async () => {
        let reminder = false;
        const calls: string[] = [];
        vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
            const u = String(url);
            if (u.endsWith('/remind')) {
                calls.push(init?.method ?? 'GET');
                reminder = init?.method === 'POST';
                return {ok: true, status: 200, json: async () => ({reminder})} as Response;
            }
            return {ok: true, status: 200, json: async () => ({...EVENING, standings: [],
                me: {joined: false, waiting: false, current_game_id: null, reminder}})} as Response;
        }));
        routes('/arenas/4');
        const button = await screen.findByTestId('arena-remind');
        await act(async () => fireEvent.click(button));
        expect(await screen.findByTestId('arena-reminder-on')).toHaveTextContent('We will remind you before the start');
        expect(screen.queryByTestId('arena-remind')).toBeNull();
        await act(async () => fireEvent.click(screen.getByTestId('arena-reminder-off')));
        expect(await screen.findByTestId('arena-remind')).toBeInTheDocument();
        expect(calls).toEqual(['POST', 'DELETE']);
    });

    it('a running arena has no reminder; the notification leads to the arena page', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => ({...RUNNING, standings: [],
            me: {joined: true, waiting: false, current_game_id: null, reminder: false}})} as Response)));
        routes('/arenas/3');
        await screen.findByTestId('arena-play');
        expect(screen.queryByTestId('arena-remind')).toBeNull();

        const n = {id: 1, kind: 'arena_reminder', payload: {arena_id: 4, base_time_ms: 300000, increment_ms: 3000,
            starts_at: IN_TEN_MINUTES}, created_at: null, read: false} as AppNotification;
        expect(notificationLink(n)).toBe('/arenas/4');
        expect(notificationText(n, makeI18n('en').t)).toBe('Arena 5+3 is about to start');
        expect(notificationText(n, makeI18n('uk').t)).toBe('Арена 5+3 скоро почнеться');
        expect(notificationText(n, makeI18n('en').t)).toBe('Arena 5+3 is about to start');
    });

    it('a podium place (33.5): the text in both languages and a link to the arena', () => {
        const n = {id: 2, kind: 'arena_podium', payload: {arena_id: 9, place: 2, category: 'blitz'},
            created_at: null, read: false} as AppNotification;
        expect(notificationLink(n)).toBe('/arenas/9');
        expect(notificationText(n, makeI18n('en').t)).toBe('You took place 2 in the arena — congratulations!');
        expect(notificationText(n, makeI18n('uk').t)).toBe('Ви посіли 2 місце на арені — вітаємо!');
        expect(notificationText(n, makeI18n('en').t)).toBe('You took place 2 in the arena — congratulations!');
    });

    it('the legends week is open (26.1): the text with the event title in both languages and a link to the Time Machine', () => {
        const n = {id: 3, kind: 'legends_week', payload: {event_key: 'london_1851', starts_on: '2026-11-30'},
            created_at: null, read: false} as AppNotification;
        expect(notificationLink(n)).toBe('/time-machine');
        expect(notificationText(n, makeI18n('en').t)).toMatch(/^The legends week is open: .*1851/);
        expect(notificationText(n, makeI18n('uk').t)).toMatch(/^Тиждень легенд відкрито: .*1851/);
    });
});

describe('splits of an overfull arena (33.2)', () => {
    it('a name with a split; a player in another split — a move there', async () => {
        const fetchMock = vi.fn(async (url: string) => {
            const u = String(url);
            const body = u.endsWith('/arenas/3')
                ? {...RUNNING, division: 1, standings: [], me: {joined: false, waiting: false, current_game_id: null, division_arena_id: 9}}
                : {...RUNNING, id: 9, division: 2, parent_id: 3, standings: [],
                    me: {joined: true, waiting: false, current_game_id: null, division_arena_id: null}};
            return {ok: true, status: 200, json: async () => body} as Response;
        });
        vi.stubGlobal('fetch', fetchMock);
        render(
            <MemoryRouter initialEntries={['/arenas/3']}>
                <Routes><Route path="/arenas/:arenaId" element={<ArenaPage/>}/></Routes>
            </MemoryRouter>,
        );
        expect(await screen.findByRole('heading', {level: 1})).toHaveTextContent('Arena 3+2 · division 2');
        expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/arenas/9'))).toBe(true);
    });
});

describe('monthly arena league', () => {
    const row = (place: number, username: string, score: number) => ({place, username, score, best: score, arenas: 1});
    const league = (category: string) => ({
        season: '2026-11', category, categories: ['bullet', 'blitz'], players: 3,
        table: category === 'blitz' ? [row(1, 'magnus', 12), row(2, 'hikaru', 9)] : [],
        me: category === 'blitz' ? row(7, 'me', 2) : null,
    });

    it('the table by category, one\'s own row below the first places, and an empty league', async () => {
        const fetchMock = vi.fn(async (url: string) => {
            const match = /league\?category=(\w+)/.exec(url);
            const body = match ? league(match[1]) : {arenas: []};
            return {ok: true, status: 200, json: async () => body} as Response;
        });
        vi.stubGlobal('fetch', fetchMock);
        routes('/arenas');
        expect(await screen.findByTestId('league-row-1')).toHaveTextContent('magnus');
        expect(screen.getByTestId('league-me')).toHaveTextContent('7');
        expect(screen.getByTestId('arena-league')).toHaveTextContent('Season 2026-11');
        await act(async () => fireEvent.click(screen.getByTestId('league-category-bullet')));
        expect(await screen.findByText('No arena games this month yet')).toBeInTheDocument();
        expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/arenas/league?category=bullet'))).toBe(true);
    });
});

describe('podium celebration', () => {
    afterEach(() => localStorage.clear());

    it('the final-results podium player sees the celebration once', async () => {
        vi.spyOn(soundEngine, 'playFanfare').mockImplementation(() => undefined);
        const body = {...RUNNING, id: 9, status: 'finished',
            standings: [{place: 1, username: 'me', score: 8, games: 4, wins: 4, fire: false, rating: 1600},
                {place: 2, username: 'magnus', score: 6, games: 3, wins: 3, fire: false, rating: 2800}],
            me: {joined: true, waiting: false, current_game_id: null, podium_place: 1}};
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => body} as Response)));
        const view = routes('/arenas/9');
        expect(await screen.findByTestId('tournament-celebration')).toBeInTheDocument();
        expect(screen.getByText('Place 1 of 2')).toBeInTheDocument();
        await act(async () => fireEvent.click(screen.getByTestId('celebration-close')));
        expect(screen.queryByTestId('tournament-celebration')).not.toBeInTheDocument();
        view.unmount();
        routes('/arenas/9');
        expect(await screen.findByTestId('arena-standings')).toBeInTheDocument();
        expect(screen.queryByTestId('tournament-celebration')).not.toBeInTheDocument();
    });

    it('did not play a single game — no results screen', async () => {
        const body = {...RUNNING, id: 10, status: 'finished', standings: [],
            me: {username: 'me', joined: true, waiting: false, current_game_id: null, podium_place: null}};
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => body} as Response)));
        routes('/arenas/10');
        expect(await screen.findByTestId('arena-page')).toBeInTheDocument();
        expect(screen.queryByTestId('tournament-celebration')).not.toBeInTheDocument();
    });

    it('a player who played outside the top three sees the results: one\'s own row in the table, the performance and the overall standings', async () => {
        const standing = (place: number, username: string, games: number) => ({
            place, username, score: 10 - place, games, wins: 1, fire: false, rating: 1500 + place, performance: 1700,
        });
        const body = {...RUNNING, id: 11, status: 'finished',
            standings: [standing(1, 'a', 4), standing(2, 'b', 4), standing(3, 'c', 4), standing(4, 'me', 3)],
            me: {username: 'me', joined: true, waiting: false, current_game_id: null, podium_place: null}};
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => body} as Response)));
        routes('/arenas/11');
        expect(await screen.findByTestId('celebration-title')).toHaveTextContent('Tournament finished');
        expect(screen.getByTestId('celebration-row-me')).toHaveAttribute('aria-current', 'true');
        expect(screen.getByTestId('celebration-detail-me')).toHaveTextContent('perf. 1700');
        expect(screen.getByText('Place 4 of 4')).toBeInTheDocument();
    });
});
