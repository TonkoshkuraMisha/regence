// Opponents for beginners (task 21.4): selection filters (type, strength, style), habits (no more than three), opening
// character and the new sliders go into the opponent config.

import {act, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {PersonalityWorkshop} from '../PersonalityWorkshop';
import {resetBotCatalogCache} from '../../../services/botCatalog';
import {DEFAULT_CONFIG} from '../../../services/personalities';
import {strengthBucket, styleTags} from '../../../config/archetypes';

const archetype = (id: string, rating: number, extra: Record<string, unknown> = {}) => ({
    id, config: {...DEFAULT_CONFIG, target_elo: rating, ...extra},
    declared_rating: rating, rating, measured: false, games: 0, ci95: null,
});

const CATALOG = {
    calibration: null,
    historical: [],
    archetypes: [
        archetype('blunderer', 350, {habits: ['hangs_pieces']}),
        archetype('trapper', 900, {opening_style: 'trapper', aggression: 40}),
        archetype('rusher', 700, {aggression: 70}),
        archetype('combinator', 2200, {aggression: 80}),
    ],
};

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
    vi.stubGlobal('fetch', vi.fn(async (input: string) => ({
        ok: true, status: 200, json: async () => (String(input).endsWith('/bots/catalog') ? CATALOG : {openings: []}),
    }) as Response));
});

afterEach(() => vi.unstubAllGlobals());

async function renderWorkshop(onPlay = vi.fn()) {
    await act(async () => render(
        <PersonalityWorkshop token={null} playDisabled={false} onPlay={onPlay} canStartFromPosition={false}
                             startFromPosition={false} onStartFromPositionChange={vi.fn()}/>,
    ));
    return onPlay;
}

const shown = () => within(screen.getByTestId('archetype-list')).queryAllByRole('button').map((b) => b.textContent ?? '');

describe('opponents for beginners', () => {
    it('strength buckets and style labels', () => {
        expect([350, 800, 1250, 1700, 2400].map(strengthBucket)).toEqual(['beginner', 'novice', 'club', 'strong', 'expert']);
        expect(styleTags({...DEFAULT_CONFIG, habits: ['early_queen'], aggression: -40, opening_style: 'gambit'}))
            .toEqual(['weakness', 'calm', 'opening']);
        expect(styleTags(DEFAULT_CONFIG)).toEqual([]);
    });

    it('filters by strength, style and type', async () => {
        await renderWorkshop();
        expect(shown()).toHaveLength(4);
        fireEvent.change(screen.getByTestId('filter-strength'), {target: {value: 'beginner'}});
        expect(shown().map((s) => s.split(' ')[0])).toEqual(['Gaper', 'Rusher']);
        fireEvent.change(screen.getByTestId('filter-style'), {target: {value: 'weakness'}});
        expect(shown()).toHaveLength(1);
        fireEvent.change(screen.getByTestId('filter-strength'), {target: {value: 'expert'}});
        expect(screen.getByText('No opponents match the filter.')).toBeInTheDocument();
        fireEvent.change(screen.getByTestId('filter-show'), {target: {value: 'mine'}});
        expect(screen.queryByTestId('archetype-list')).toBeNull();
    });

    it('habits — no more than three; character and sliders — in the opponent config', async () => {
        const onPlay = await renderWorkshop();
        for (const habit of ['hangs_pieces', 'early_queen', 'pawn_grabber']) fireEvent.click(screen.getByTestId(`habit-${habit}`));
        expect(screen.getByTestId('habit-knight_lover')).toBeDisabled();
        fireEvent.change(screen.getByTestId('opening-style'), {target: {value: 'trap_victim'}});
        fireEvent.change(screen.getByRole('slider', {name: 'Attitude to a draw'}), {target: {value: '-60'}});
        fireEvent.change(screen.getByRole('slider', {name: 'Passed pawns'}), {target: {value: '180'}});
        fireEvent.change(screen.getByRole('slider', {name: 'Strength (Elo)'}), {target: {value: '300'}});
        fireEvent.click(screen.getByRole('button', {name: /White/}));
        const config = onPlay.mock.calls[0][0].config;
        expect(config).toMatchObject({habits: ['hangs_pieces', 'early_queen', 'pawn_grabber'], opening_style: 'trap_victim',
            draw_attitude: -60, passed_pawns: 180, target_elo: 300});
    });
});
