// Achievements and the club title in the profile (task 17.6).

import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {Achievements} from '../Achievements';

afterEach(() => vi.unstubAllGlobals());

describe('achievements', () => {
    it('the title, unlocked first, progress for locked ones', async () => {
        const fetchMock = vi.fn(async () => ({
            ok: true, json: async () => ({
                title: 'amateur',
                achievements: [
                    {code: 'wins_10', target: 10, progress: 3, earned_at: null, new: false},
                    {code: 'first_game', target: 1, progress: 1, earned_at: '2026-11-15T00:00:00Z', new: true},
                ],
            }),
        } as Response));
        vi.stubGlobal('fetch', fetchMock);
        render(<MemoryRouter><Achievements username="magnus"/></MemoryRouter>);
        expect(await screen.findByTestId('club-title')).toHaveTextContent('Amateur');
        expect(String((fetchMock.mock.calls as unknown as [string][])[0][0])).toContain('/profile/magnus/achievements');
        const items = screen.getAllByRole('listitem');
        expect(items[0]).toHaveTextContent('First game');
        expect(items[0]).toHaveTextContent('new!');
        expect(items[1]).toHaveTextContent('3 of 10');
    });
});
