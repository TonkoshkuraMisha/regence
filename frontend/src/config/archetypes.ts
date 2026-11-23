// --- FILE: frontend/src/config/archetypes.ts ---

/**
 * Workshop opponent on the board: profile, style radar and strength explanation. The archetypes themselves
 * (fictional characters) live on the server - src/services/bots/archetypes.py - the frontend receives
 * them together with the measured strength via GET /bots/catalog (services/botCatalog.ts).
 */

import {t} from '../i18n';
import type {PersonalityConfig} from '../services/personalities';
import type {HistoricalBotProfile} from './champions';
import {hasMessage} from '../i18n';
import type {Messages} from '../i18n';

/** Workshop opponent in a game: name, config and (if saved on the server) its id. */
export interface CustomOpponent {
    name: string;
    /**
     * Name under which the game is saved on the server, if it differs from the displayed one: for a past master
     * ("Time Machine") the board shows the name in the player's language, while the tournament and PGN use the Latin one.
     */
    savedName?: string;
    config: PersonalityConfig;
    personalityId?: number;
    bio?: string;
    /**
     * Workshop archetype unchanged (including a ladder opponent): name and description are taken from the catalog in the
     * player's language, and the game goes to the archive with the key "archetype:<id>".
     */
    archetypeId?: ArchetypeId;
}

/** Workshop archetype id - key of the archetypes section in the catalogs (the same list as on the server). */
export type ArchetypeId = keyof Messages['archetypes'];

/** Check of an id that came from the server: an unknown archetype (server newer than the client) is not shown. */
export function isArchetypeId(value: unknown): value is ArchetypeId {
    return typeof value === 'string' && hasMessage(`archetypes.${value}.name`);
}

/** Archetype key in the game archive (games.personality_name) - the same as on the server. */
export const ARCHETYPE_PREFIX = 'archetype:';

export function archetypeKey(id: ArchetypeId): string {
    return `${ARCHETYPE_PREFIX}${id}`;
}

// Workshop opponent avatar - a knight silhouette (our own image, no external files).
const WORKSHOP_AVATAR = `data:image/svg+xml;utf8,${encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="10" fill="#3b2412"/>'
    + '<path d="M22 50h22l-2-6c0-8 4-12 4-20 0-8-6-14-14-14l-2 4-4 2-6 8 2 4 6-2 4 2-10 12z" fill="#e7c38b"/></svg>',
)}`;

/** Profile for the board and panel - in the same form as for historical bots. */
export function customBotProfile(opponent: CustomOpponent): HistoricalBotProfile {
    const name = () => (opponent.archetypeId ? t(`archetypes.${opponent.archetypeId}.name`) : opponent.name);
    return {
        id: 'custom',
        get name() {
            return name();
        },
        get shortName() {
            return name();
        },
        get playerLabel() {
            return name();
        },
        get title() {
            return t('bots.workshopTitle');
        },
        get era() {
            return t('bots.workshopEra');
        },
        rating: opponent.config.target_elo,
        get motto() {
            if (opponent.archetypeId) return t(`archetypes.${opponent.archetypeId}.bio`);
            return opponent.bio || t('bots.workshopMotto');
        },
        avatar: WORKSHOP_AVATAR,
        fallbackAvatar: WORKSHOP_AVATAR,
    };
}

/**
 * Illustrative summary of the sliders for the radar (0..100). This is an illustration of character, not a strength measurement:
 * measured strength is task 10.4.
 */
export type RadarAxis = 'attack' | 'defense' | 'tactics' | 'position' | 'endgame';

export function styleRadar(config: PersonalityConfig): { key: RadarAxis; axis: string; value: number }[] {
    const clamp = (v: number) => Math.round(Math.max(0, Math.min(100, v)));
    const attack = (config.aggression + 100) / 2;
    const precision = 100 - Math.min(config.blunder_guard_cp, 400) / 4;
    const strength = ((config.target_elo - 600) / 2200) * 100;
    const values: Record<RadarAxis, number> = {
        attack: clamp(attack * 0.7 + config.mobility * 0.15),
        defense: clamp((100 - attack) * 0.5 + config.king_safety * 0.25),
        tactics: clamp(attack * 0.3 + precision * 0.3 + strength * 0.4 - config.randomness * 0.2),
        position: clamp(config.center_control * 0.25 + config.pawn_structure * 0.25),
        endgame: clamp(config.pawn_structure * 0.2 + strength * 0.6),
    };
    return (Object.keys(values) as RadarAxis[]).map((key) => ({
        key,
        axis: t(`workshop.radar.${key}`),
        value: values[key],
    }));
}

/**
 * Share of controlled mistakes by target strength - a copy of the server's ERROR_RATE_CURVE (src/services/bots/personality.py,
 * tuned from calibration). That the numbers match is checked by tests/test_personality_bot.py.
 */
export const ERROR_RATE_CURVE: readonly (readonly [number, number])[] = [
    [300, 0.57], [600, 0.43], [1500, 0.0],
];

export function errorRate(elo: number): number {
    for (let i = 1; i < ERROR_RATE_CURVE.length; i++) {
        const [loElo, loRate] = ERROR_RATE_CURVE[i - 1];
        const [hiElo, hiRate] = ERROR_RATE_CURVE[i];
        if (elo <= hiElo) {
            const share = (Math.max(elo, loElo) - loElo) / (hiElo - loElo);
            return loRate + (hiRate - loRate) * share;
        }
    }
    return 0;
}

// --- Opponent selection filters (task 21.4) -------------------------------------------------

export const STRENGTH_BUCKETS = ['beginner', 'novice', 'club', 'strong', 'expert'] as const;
export type StrengthBucket = typeof STRENGTH_BUCKETS[number];
export const STYLE_TAGS = ['weakness', 'attacking', 'calm', 'opening'] as const;
export type StyleTag = typeof STYLE_TAGS[number];

export function strengthBucket(rating: number): StrengthBucket {
    if (rating < 800) return 'beginner';
    if (rating < 1200) return 'novice';
    if (rating < 1600) return 'club';
    if (rating < 2000) return 'strong';
    return 'expert';
}

/** Opponent style labels from its config: weakness, attack, calm, opening character. */
export function styleTags(config: PersonalityConfig): StyleTag[] {
    const tags: StyleTag[] = [];
    if ((config.habits ?? []).length > 0) tags.push('weakness');
    if (config.aggression >= 30) tags.push('attacking');
    if (config.aggression <= -30) tags.push('calm');
    if ((config.opening_style ?? 'normal') !== 'normal') tags.push('opening');
    return tags;
}

/** Strength explanation: error share - by the same curve as on the server. */
export function strengthNote(config: PersonalityConfig): string {
    const elo = config.target_elo;
    const errors = Math.round(errorRate(elo) * 100);
    if (errors > 0) return t('workshop.strengthWithErrors', {elo, errors});
    return t('workshop.strengthExact', {elo});
}
