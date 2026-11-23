// Catalog of masters of the past (task 28.5): the list, search and order, starting a single game with a master.

import {act, fireEvent, render, screen, within} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setLanguage, t} from '../../../i18n';
import {setToken} from '../../../services/authToken';
import {birthYear, matchesQuery, sortMasters} from '../../../services/masters';
import type {Master} from '../../../services/masters';
import {guestName} from '../../../services/timeMachine';
import {MastersPage} from '../MastersPage';

const CONFIG = {target_elo: 2400, aggression: 30};
const MASTERS: Master[] = [
    {id: 'kieseritzky', pgn_name: 'Kieseritzky, Lionel', era: '1806–1853', rating: 1950, events: ['london_1851'],
        openings: {white: ["King's Gambit Accepted: Kieseritzky Gambit"], black: []}},
    {id: 'keres', pgn_name: 'Keres, Paul', era: '1916–1975', rating: 2400, events: ['avro_1938'], openings: {white: [], black: []}},
    {id: 'mucklow', pgn_name: 'Mucklow, James R.', era: null, rating: 1600, events: ['london_1851'], openings: {white: [], black: []}},
];

type Handler = (url: string) => { status?: number; body: unknown } | unknown;

function stub(handler: Handler) {
    const fetchMock = vi.fn(async (url: string) => {
        const reply = handler(String(url));
        const {status = 200, body} = reply && typeof reply === 'object' && 'body' in reply
            ? reply as { status?: number; body: unknown } : {body: reply};
        return {ok: status < 400, status, json: async () => body} as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

/** A stub board: shows what route state it was opened with. */
function Home() {
    const location = useLocation();
    return <pre data-testid="home-state">{JSON.stringify(location.state)}</pre>;
}

function renderPage() {
    return render(
        <MemoryRouter initialEntries={['/masters']}>
            <Routes>
                <Route path="/masters" element={<MastersPage/>}/>
                <Route path="/" element={<Home/>}/>
                <Route path="/time-machine" element={<p data-testid="time-machine-opened"/>}/>
            </Routes>
        </MemoryRouter>,
    );
}

const order = () => screen.getAllByRole('listitem').map((item) => item.getAttribute('data-testid'));

beforeEach(() => setToken('jwt'));
afterEach(() => {
    setToken(null);
    setLanguage('en', {persist: false});
    vi.unstubAllGlobals();
});

describe('order and search', () => {
    const nameOf = (master: Master) => guestName(master.id, t);

    it('the birth year — from the years of life; without dates — null', () => {
        expect(MASTERS.map(birthYear)).toEqual([1806, 1916, null]);
    });

    it('by strength, by years of life (without dates — at the end) and by name', () => {
        expect(sortMasters(MASTERS, 'strength', nameOf, 'en').map((m) => m.id)).toEqual(['keres', 'kieseritzky', 'mucklow']);
        expect(sortMasters(MASTERS, 'years', nameOf, 'en').map((m) => m.id)).toEqual(['kieseritzky', 'keres', 'mucklow']);
        expect(sortMasters(MASTERS, 'name', nameOf, 'en').map((m) => nameOf(m)))
            .toEqual([...MASTERS.map(nameOf)].sort((a, b) => a.localeCompare(b, 'en')));
        // The original list does not change.
        expect(MASTERS[0].id).toBe('kieseritzky');
    });

    it('searches by the name in the player\'s language and by the Latin name from the PGN', () => {
        expect(matchesQuery(MASTERS[1], 'Paul Keres', 'keres')).toBe(true);
        expect(matchesQuery(MASTERS[1], 'Paul Keres', 'KERES')).toBe(true);
        expect(matchesQuery(MASTERS[1], 'Paul Keres', '  ')).toBe(true);
        expect(matchesQuery(MASTERS[1], 'Paul Keres', 'morphy')).toBe(false);
    });
});

describe('masters page', () => {
    it('shows everyone: the name, years, strength, tournaments and the signature opening', async () => {
        stub(() => ({guests: MASTERS}));
        renderPage();
        const keres = await screen.findByTestId('master-keres');
        expect(within(keres).getByRole('heading')).toHaveTextContent('Paul Keres');
        expect(keres).toHaveTextContent('1916–1975');
        expect(keres).toHaveTextContent('strength 2400');
        expect(keres).toHaveTextContent('AVRO 1938');
        expect(screen.queryByTestId('master-opening-keres')).toBeNull();
        expect(screen.getByTestId('master-opening-kieseritzky')).toHaveTextContent('Kieseritzky Gambit');
        expect(screen.getByTestId('master-mucklow')).toHaveTextContent('years of life unknown');
        expect(screen.getByTestId('masters-count')).toHaveTextContent('3 masters');
        // By default — by strength.
        expect(order()).toEqual(['master-keres', 'master-kieseritzky', 'master-mucklow']);
    });

    it('search, order and "only with a signature opening" change the list', async () => {
        stub(() => ({guests: MASTERS}));
        renderPage();
        await screen.findByTestId('master-keres');

        fireEvent.change(screen.getByTestId('masters-order'), {target: {value: 'years'}});
        expect(order()).toEqual(['master-kieseritzky', 'master-keres', 'master-mucklow']);

        fireEvent.change(screen.getByTestId('masters-search'), {target: {value: 'mucklow'}});
        expect(order()).toEqual(['master-mucklow']);
        fireEvent.change(screen.getByTestId('masters-search'), {target: {value: 'nobody'}});
        expect(screen.getByTestId('masters-empty')).toBeInTheDocument();
        fireEvent.change(screen.getByTestId('masters-search'), {target: {value: ''}});

        fireEvent.click(screen.getByTestId('masters-only-opening'));
        expect(order()).toEqual(['master-kieseritzky']);
        expect(screen.getByTestId('masters-count')).toHaveTextContent('1 master');
    });

    it('"Play as Black" takes the master\'s character and opens the board with the game', async () => {
        const fetchMock = stub((url) => url.endsWith('/guests/keres')
            ? {id: 'keres', pgn_name: 'Keres, Paul', rating: 2400, config: CONFIG} : {guests: MASTERS});
        renderPage();
        const button = await screen.findByTestId('play-keres-black');
        await act(async () => {
            fireEvent.click(button);
        });
        const state = JSON.parse((await screen.findByTestId('home-state')).textContent ?? 'null');
        // On the board — the name in the player's language, in the archive — the Latin name from the PGN.
        expect(state).toEqual({guestGame: {name: 'Paul Keres', savedName: 'Keres, Paul', config: CONFIG, color: 'black'}});
        expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/api/v1/bots/guests/keres'))).toBe(true);
    });

    it('a guest is offered to log in and the game does not start', async () => {
        setToken(null);
        const fetchMock = stub(() => ({guests: MASTERS}));
        renderPage();
        fireEvent.click(await screen.findByTestId('play-keres-white'));
        expect(screen.getByRole('alert')).toHaveTextContent('Sign in');
        expect(screen.queryByTestId('home-state')).toBeNull();
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it('server errors are shown: the list did not load, the character did not arrive', async () => {
        stub(() => ({status: 500, body: {}}));
        const {unmount} = renderPage();
        expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the masters');
        unmount();

        stub((url) => url.endsWith('/guests/keres')
            ? {status: 404, body: {detail: {code: 'guest_not_found', params: {}, message: 'x'}}} : {guests: MASTERS});
        renderPage();
        const button = await screen.findByTestId('play-keres-random');
        await act(async () => {
            fireEvent.click(button);
        });
        expect(await screen.findByRole('alert')).toHaveTextContent('There is no such master of the past');
        expect(screen.queryByTestId('home-state')).toBeNull();
    });

    it('in English and Ukrainian — their own names and labels', async () => {
        setLanguage('en', {persist: false});
        stub(() => ({guests: MASTERS}));
        const {unmount} = renderPage();
        const keres = await screen.findByTestId('master-keres');
        expect(keres).toHaveTextContent('Paul Keres');
        expect(keres).toHaveTextContent('strength 2400');
        unmount();
        setLanguage('uk', {persist: false});
        renderPage();
        expect(await screen.findByTestId('master-mucklow')).toHaveTextContent('роки життя невідомі');
    });
});

describe('a single master card (the "to the opponent" jump from a tournament)', () => {
    it('/masters?master=<id> shows only him and a link to everyone', async () => {
        stub(() => ({guests: MASTERS}));
        render(<MemoryRouter initialEntries={['/masters?master=keres']}>
            <Routes><Route path="/masters" element={<MastersPage/>}/></Routes>
        </MemoryRouter>);
        expect(await screen.findByTestId('master-keres')).toBeInTheDocument();
        expect(screen.queryByTestId('master-kieseritzky')).toBeNull();
        expect(screen.getByTestId('masters-all')).toHaveAttribute('href', '/masters');
    });
});
