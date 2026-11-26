// Weekly tournament against the legends (task 26.1): the card with the table, entering this week's event, the lobby announcement.

import {render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setLanguage} from '../../../i18n';
import {setToken} from '../../../services/authToken';
import {LegendsAnnouncement, LegendsSeason, LegendsWeek} from '../LegendsWeek';

const WEEK = {
    event_key: 'london_1851', starts_on: '2026-11-23', ends_on: '2026-11-30',
    rows: [{place: 1, username: 'Ada', tournament_place: 2, me: false}],
    me: {place: 7, username: 'Bob', tournament_place: 9, me: true},
};

function stubWeek(body: unknown) {
    vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, status: 200, json: async () => body}) as Response));
}

beforeEach(() => setToken('jwt'));
afterEach(() => {
    setToken(null);
    setLanguage('en', {persist: false});
    vi.unstubAllGlobals();
});

describe('LegendsWeek', () => {
    it('shows the table with the own row below the top and starts the announced event', async () => {
        stubWeek(WEEK);
        const onStart = vi.fn();
        render(<LegendsWeek busy={false} onStart={onStart}/>);
        expect(await screen.findAllByTestId('legends-row')).toHaveLength(2);
        expect(screen.getAllByTestId('legends-row')[1]).toHaveAttribute('aria-current', 'true');
        await userEvent.click(screen.getByTestId('legends-play'));
        expect(onStart).toHaveBeenCalledWith('london_1851');
    });

    it('invites to be first when nobody has finished', async () => {
        stubWeek({...WEEK, rows: [], me: null});
        render(<LegendsWeek busy={false} onStart={() => undefined}/>);
        expect(await screen.findByTestId('legends-empty')).toBeInTheDocument();
    });

    it('renders nothing for a reply of another shape', async () => {
        stubWeek([{key: 'x'}]);
        const {container} = render(<LegendsWeek busy={false} onStart={() => undefined}/>);
        await waitFor(() => expect(fetch).toHaveBeenCalled());
        expect(container).toBeEmptyDOMElement();
    });

    it('announces the event in the lobby with a link to the time machine', async () => {
        stubWeek(WEEK);
        render(<MemoryRouter><LegendsAnnouncement/></MemoryRouter>);
        expect(await screen.findByRole('link')).toHaveAttribute('href', '/time-machine');
    });
});

describe('LegendsSeason', () => {
    const SEASON = {
        season: '2026-11', weeks: ['2026-11-02', '2026-11-09'],
        rows: [{place: 1, username: 'Ada', points: 45, wins: 1, weeks: 2, me: false}],
        me: {place: 4, username: 'Bob', points: 1, wins: 0, weeks: 1, me: true},
    };

    it('shows the season, points and weeks from the server, with the own row below the top', async () => {
        stubWeek(SEASON);
        render(<LegendsSeason/>);
        expect(await screen.findByText('Legends season 2026-11')).toBeInTheDocument();
        const rows = screen.getAllByTestId('legends-season-row');
        expect(rows[0]).toHaveTextContent('Ada');
        expect(rows[0]).toHaveTextContent('45 points');
        expect(rows[0]).toHaveTextContent('2 weeks');
        expect(rows[1]).toHaveTextContent('Bob');
        expect(rows[1]).toHaveTextContent('1 point');
        expect(rows[1]).toHaveAttribute('aria-current', 'true');
    });

    it('an empty season says so; a reply of another shape leaves the card out', async () => {
        stubWeek({...SEASON, rows: [], me: null});
        const {unmount} = render(<LegendsSeason/>);
        expect(await screen.findByTestId('legends-season-empty')).toBeInTheDocument();
        unmount();
        stubWeek({detail: 'old server'});
        render(<LegendsSeason/>);
        await waitFor(() => expect(screen.queryByTestId('legends-season')).toBeNull());
    });

    it('is written in Ukrainian with the right plural forms', async () => {
        setLanguage('uk', {persist: false});
        stubWeek({...SEASON, rows: [{...SEASON.rows[0], points: 22, weeks: 5}], me: null});
        render(<LegendsSeason/>);
        expect(await screen.findByText('Сезон легенд 2026-11')).toBeInTheDocument();
        expect(screen.getByTestId('legends-season-row')).toHaveTextContent('22 очки');
        expect(screen.getByTestId('legends-season-row')).toHaveTextContent('5 тижнів');
    });
});
