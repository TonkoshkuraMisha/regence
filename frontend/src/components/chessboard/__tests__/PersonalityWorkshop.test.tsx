// The opponent workshop: archetypes, sliders, saving (guest browser / profile) and starting a game.

import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {PersonalityWorkshop} from '../PersonalityWorkshop';
import {resetBotCatalogCache} from '../../../services/botCatalog';
import {DEFAULT_CONFIG, readGuestPersonalities} from '../../../services/personalities';

function renderWorkshop(token: string | null, onPlay = vi.fn()) {
    render(
        <PersonalityWorkshop
            token={token}
            playDisabled={false}
            onPlay={onPlay}
            canStartFromPosition={false}
            startFromPosition={false}
            onStartFromPositionChange={vi.fn()}
        />,
    );
    return onPlay;
}

const slider = (label: string) => screen.getByRole('slider', {name: label}) as HTMLInputElement;

// The server sends only the archetype id; the name and description come from the catalogue in the player's language.
const archetype = (id: string, target_elo: number, extra: Record<string, unknown> = {}) => ({
    id, config: {...DEFAULT_CONFIG, target_elo, ...extra},
    declared_rating: target_elo, rating: target_elo, measured: false, games: 0, ci95: null,
});

const CATALOG = {
    calibration: {date: '2026-11-12', games: 680},
    historical: [],
    archetypes: [
        {...archetype('rusher', 700, {aggression: 70}), rating: 640, measured: true, games: 40, ci95: 90},
        archetype('combinator', 2200),
        archetype('archetype_from_the_future', 1500),  // the client does not know it yet — it is not shown
    ],
};

/** fetch: the catalogue — always; the rest — by the passed handler. */
function stubFetch(other?: (url: string, init?: RequestInit) => unknown) {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = input.toString();
        const body = url.endsWith('/bots/catalog') ? CATALOG : other?.(url, init);
        return {ok: true, status: 200, json: async () => body} as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

beforeEach(() => {
    localStorage.clear();
    resetBotCatalogCache();
    vi.stubGlobal('ResizeObserver', class {
        observe() {
        }

        unobserve() {
        }

        disconnect() {
        }
    });
});

afterEach(() => vi.unstubAllGlobals());

describe('guest', () => {
    it('archetypes come from the server, the measured strength is marked', async () => {
        stubFetch();
        renderWorkshop(null);
        expect(await screen.findByRole('button', {name: /Rusher 640 \(meas\.\)/})).toBeInTheDocument();
        expect(screen.getByRole('button', {name: /Combinator 2200$/})).toBeInTheDocument();
    });

    it('an archetype fills the constructor, a weak one — with an explanation about deliberate mistakes', async () => {
        stubFetch();
        renderWorkshop(null);
        fireEvent.click(await screen.findByRole('button', {name: /Rusher/}));

        expect((screen.getByPlaceholderText(/Gambiteer/) as HTMLInputElement).value).toBe('Rusher');
        expect(slider('Strength (Elo)').value).toBe('700');
        expect(screen.getByTestId('strength-note').textContent).toMatch(/deliberate/);
    });

    it('the slider changes the value and the strength explanation', () => {
        stubFetch();
        renderWorkshop(null);
        fireEvent.change(slider('Strength (Elo)'), {target: {value: '2000'}});
        expect(screen.getByTestId('strength-note').textContent).toMatch(/~2000.*no deliberate mistakes/);
    });

    it('saving — in the browser, the opponent appears in the list', async () => {
        stubFetch();
        renderWorkshop(null);
        fireEvent.change(screen.getByPlaceholderText(/Gambiteer/), {target: {value: 'Gambiteer'}});
        fireEvent.change(slider('Aggression'), {target: {value: '80'}});
        await act(async () => fireEvent.click(screen.getByRole('button', {name: /Save opponent/})));

        expect(readGuestPersonalities()[0]).toMatchObject({name: 'Gambiteer', config: {aggression: 80}});
        expect(screen.getByText(/Saved in this browser/)).toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Edit Gambiteer'})).toBeInTheDocument();
    });

    it('without a name it does not save', async () => {
        stubFetch();
        renderWorkshop(null);
        await act(async () => fireEvent.click(screen.getByRole('button', {name: /Save opponent/})));
        expect(screen.getByRole('alert').textContent).toMatch(/name/);
        expect(readGuestPersonalities()).toEqual([]);
    });

    it('"Play" hands over the name and the config from the constructor', async () => {
        stubFetch();
        const onPlay = renderWorkshop(null);
        fireEvent.click(await screen.findByRole('button', {name: /Combinator/}));
        fireEvent.click(screen.getByRole('button', {name: /Black/}));

        const [opponent, color] = onPlay.mock.calls[0];
        expect(color).toBe('black');
        expect(opponent.name).toBe('Combinator');
        expect(opponent.bio).toBe('Sees blows several moves ahead and almost never miscalculates.');
        expect(opponent.archetypeId).toBe('combinator');  // the archetype unchanged — into the archive by key
        expect(opponent.config.target_elo).toBe(2200);
        expect(opponent.personalityId).toBeUndefined();
    });
});

describe('a logged-in player', () => {
    const saved = {
        id: 5, name: 'Gambiteer', config: {...DEFAULT_CONFIG, aggression: 70},
        created_at: '2026-11-12T00:00:00Z', updated_at: '2026-11-12T00:00:00Z',
    };

    function stubServer() {
        return stubFetch((_url, init) => ((init?.method ?? 'GET') === 'GET'
            ? [saved]
            : {...saved, ...JSON.parse(String(init?.body ?? '{}'))}));
    }

    it('the list comes from the server; an unchanged opponent plays by its own id', async () => {
        stubServer();
        const onPlay = renderWorkshop('jwt');

        fireEvent.click(await screen.findByRole('button', {name: 'Edit Gambiteer'}));
        fireEvent.click(screen.getByRole('button', {name: /White/}));
        expect(onPlay.mock.calls[0][0]).toMatchObject({name: 'Gambiteer', personalityId: 5});

        // After editing a slider the current config is played, not the saved one.
        fireEvent.change(slider('Aggression'), {target: {value: '-50'}});
        fireEvent.click(screen.getByRole('button', {name: /White/}));
        expect(onPlay.mock.calls[1][0].personalityId).toBeUndefined();
        expect(onPlay.mock.calls[1][0].config.aggression).toBe(-50);
    });

    it('saving a changed opponent — a PUT to the profile', async () => {
        const fetchMock = stubServer();
        renderWorkshop('jwt');
        fireEvent.click(await screen.findByRole('button', {name: 'Edit Gambiteer'}));
        fireEvent.change(slider('Center'), {target: {value: '180'}});
        await act(async () => fireEvent.click(screen.getByRole('button', {name: /Save opponent/})));

        const put = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT');
        expect(put?.[0]).toMatch(/\/bots\/personalities\/5$/);
        expect(JSON.parse(String(put?.[1]?.body)).config.center_control).toBe(180);
        await waitFor(() => expect(screen.getByText('Saved to your profile')).toBeInTheDocument());
    });

    it('deletion asks for confirmation', async () => {
        const fetchMock = stubServer();
        vi.stubGlobal('confirm', vi.fn(() => true));
        renderWorkshop('jwt');
        const item = (await screen.findByText('Gambiteer')).closest('li') as HTMLElement;
        await act(async () => fireEvent.click(within(item).getByRole('button', {name: 'Delete Gambiteer'})));
        expect(fetchMock.mock.calls.some(([url, init]) => init?.method === 'DELETE' && String(url).endsWith('/5'))).toBe(true);
    });
});
