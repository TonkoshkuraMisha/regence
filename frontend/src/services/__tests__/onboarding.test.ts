// First login (task 17.8): the opponent of the first game by the starting rating.

import {describe, expect, it} from 'vitest';
import {pickFirstOpponent} from '../onboarding';
import type {CatalogArchetype} from '../botCatalog';
import {DEFAULT_CONFIG} from '../personalities';

const archetype = (id: string, rating: number) => ({
    id, rating, declared_rating: rating, measured: true, games: 80, ci95: 100, config: DEFAULT_CONFIG,
}) as unknown as CatalogArchetype;

const CATALOG = [archetype('quiet', 848), archetype('rusher', 792), archetype('cavalier', 1198), archetype('centralist', 1395)];

describe('opponent of the first game', () => {
    it('the strongest archetype is not stronger than the player — by the measured strength', () => {
        expect(pickFirstOpponent(CATALOG, 1200)?.id).toBe('cavalier');
        expect(pickFirstOpponent(CATALOG, 1850)?.id).toBe('centralist');
    });

    it('for a beginner who is weaker than all — the weakest', () => {
        expect(pickFirstOpponent(CATALOG, 600)?.id).toBe('rusher');
    });

    it('an empty catalog — no opponent', () => {
        expect(pickFirstOpponent([], 1200)).toBeNull();
    });
});
