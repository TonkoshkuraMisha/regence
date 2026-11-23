// The skill map (task 22.1): shown only to the player themselves, sections, weak themes, mistakes, openings and courses.

import {act, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {SkillMap} from '../SkillMap';
import type {SkillMapData} from '../../services/skills';
import {setToken} from '../../services/authToken';

const DATA: SkillMapData = {
    username: 'player1', puzzle_rating: 1500,
    sections: 'ABCDEFGHIJKL'.split('').map((s) => ({section: s, attempts: s === 'A' ? 6 : 0, score: s === 'A' ? 100 : null})),
    weakest_themes: [{theme: 'pin', section: 'B', attempts: 5, score: 20}],
    mistakes: {total: 3, fixed: 1, themes: [{theme: 'fork', count: 2}]},
    trainers: [{trainer: 'coord_find', attempts: 2, best: 9, max_level: 1}],
    openings: {repertoires: 1, new: 1, learning: 1, learned: 1},
    endgames: {done: 1, total: 25}, mates: {done: 1, total: 20},
};

beforeEach(() => {
    setToken('jwt');
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
    setToken(null);
});

const view = (username: string) => render(<MemoryRouter><SkillMap username={username}/></MemoryRouter>);

describe('skill map', () => {
    it('own profile — sections, weak themes, mistakes, openings, courses', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, json: async () => DATA}) as Response));
        await act(async () => view('player1'));
        expect(screen.getByTestId('skill-sections')).toHaveTextContent('A. Double attack100%');
        expect(screen.getByTestId('skill-weakest')).toHaveTextContent('Pin20% · 5');
        expect(screen.getByTestId('skill-mistakes')).toHaveTextContent('Positions from your games: 3, fixed: 1.');
        expect(screen.getByTestId('skill-openings')).toHaveTextContent('Learned 1 · in progress 1 · new 1');
        expect(screen.getByTestId('skill-courses')).toHaveTextContent('Endgames: 1 of 25');
    });

    it('someone else\'s profile and a guest — no block', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, json: async () => DATA}) as Response));
        const {container} = await act(async () => view('someone_else'));
        expect(container).toBeEmptyDOMElement();
        setToken(null);
        const guest = await act(async () => view('player1'));
        expect(guest.container).toBeEmptyDOMElement();
    });
});
