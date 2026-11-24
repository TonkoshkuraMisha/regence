// Weekly tournament against the legends (task 26.1): the card with the table, entering this week's event, the lobby announcement.

import {render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setLanguage} from '../../../i18n';
import {setToken} from '../../../services/authToken';
import {LegendsAnnouncement, LegendsWeek} from '../LegendsWeek';

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
