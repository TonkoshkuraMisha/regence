// --- FILE: frontend/src/services/botCatalog.ts ---

/**
 * Bot catalog from the server (GET /api/v1/bots/catalog): workshop archetypes and bot strength —
 * declared or measured by matches against Stockfish anchors (scripts/calibrate_bots.py).
 * The source of truth for archetypes is the server: the club ladder is built from them as well.
 */

import {API_BASE_URL} from '../config/api';
import type {PersonalityConfig} from './personalities';
import {t, uiMessage} from '../i18n';
import {UiError} from './apiErrors';
import {isArchetypeId} from '../config/archetypes';
import type {ArchetypeId} from '../config/archetypes';

/** Bot strength from src/services/bots/calibration.json (the server reads it, bot_calibration.strength_of). */
export interface BotStrength {
    /** Declared rating — the one the bot is tuned to. */
    declared_rating: number;
    /** Rating to display: the measured one if calibration was done (measured), otherwise equal to the declared one. */
    rating: number;
    measured: boolean;
    /** Number of calibration games and the measured rating's error: ± ci95 points (95 %); null — not measured. */
    games: number;
    ci95: number | null;
    /** Historical bots (task 32.1): rating from games with humans, their count and the engine strength correction. */
    live?: { rating: number; games: number; offset: number } | null;
}

/** Workshop archetype: name and description in the player's language — in the catalog (archetypes.<id>). */
export interface CatalogArchetype extends BotStrength {
    id: ArchetypeId;
    /** Character sliders; the strength sliders are already tuned by self-play (src/services/bots/selfplay.py, task 32.3). */
    config: PersonalityConfig;
}

/** Response of GET /api/v1/bots/catalog. */
export interface BotCatalog {
    /** When and on how many games the last calibration was run; null — there has been none. */
    calibration: { date: string; games: number } | null;
    historical: (BotStrength & { id: string })[];
    archetypes: CatalogArchetype[];
}

let cached: Promise<BotCatalog> | null = null;

/** Bot catalog: one request per tab (the result is cached), after an error the next call goes to the network again. */
export function fetchBotCatalog(): Promise<BotCatalog> {
    if (!cached) {
        cached = fetch(`${API_BASE_URL}/api/v1/bots/catalog`)
            .then((res) => {
                if (!res.ok) throw new UiError(uiMessage('workshop.catalogUnavailable'));
                return res.json() as Promise<BotCatalog>;
            })
            .then((catalog) => ({
                ...catalog,
                // An archetype the client does not know yet (the server updated earlier) is not shown without a name.
                archetypes: catalog.archetypes.filter((a) => isArchetypeId(a.id)),
            }))
            .catch((err) => {
                cached = null; // the next attempt goes to the network again
                throw err;
            });
    }
    return cached;
}

/** For tests: reset the cached catalog. */
export function resetBotCatalogCache(): void {
    cached = null;
}

/** «1720 (meas.)» — measured strength; otherwise — declared. */
export function strengthLabel(s: Pick<BotStrength, 'rating' | 'measured'>): string {
    return s.measured ? t('common.measuredShort', {rating: s.rating}) : String(s.rating);
}

/** Which historical bots the player already knows (task 32.2): games with them and the bot's points in them. */
export interface BotRival {
    bot_id: string;
    games: number;
    bot_points: number;
    /** Permanent opponent: the bot takes games with the player into account when choosing an opening. */
    remembers: boolean;
}

/** GET /api/v1/bots/rivalry — the player's score against historical bots; on any server error — an empty list. */
export async function fetchRivalry(token: string): Promise<BotRival[]> {
    const res = await fetch(`${API_BASE_URL}/api/v1/bots/rivalry`, {headers: {Authorization: `Bearer ${token}`}});
    if (!res.ok) return [];
    return ((await res.json()) as { rivals: BotRival[] }).rivals;
}

/** Points in a score: 2.5 → «2½», 0.5 → «½». */
export function scorePoints(points: number): string {
    const whole = Math.floor(points);
    const half = points - whole >= 0.5;
    return half ? `${whole || ''}½` : String(whole);
}
