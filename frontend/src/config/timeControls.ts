// --- FILE: frontend/src/config/timeControls.ts ---
// Time controls for online play: 4 categories (as on chess.com and lichess.org), each with
// the most popular presets. This used to hold the full list of DGT 2500 clock programs (36 of them,
// including Bronstein/US Delay, byo-yomi, hourglass, gong, Scrabble) - but for network games the server
// understands only plain time + increment per move (Fischer), so all
// those exotic modes were purely decorative for online play and only confused the choice.
//
// Labels and descriptions are in the message catalogs (getters), only numbers here.

import {t} from '../i18n';

export type TimeControlCategory = 'bullet' | 'blitz' | 'rapid' | 'classical';

export type TimeControlId =
    | 'bullet-1+0' | 'bullet-1+1' | 'bullet-2+1' | 'bullet-manual'
    | 'blitz-3+0' | 'blitz-3+2' | 'blitz-5+0' | 'blitz-5+3' | 'blitz-manual'
    | 'rapid-10+0' | 'rapid-10+5' | 'rapid-15+10' | 'rapid-manual'
    | 'classical-30+0' | 'classical-30+20' | 'classical-60+30' | 'classical-manual';

export interface TimeControlOption {
    id: TimeControlId;
    category: TimeControlCategory;
    base: number; // minutes at the start
    inc: number; // seconds added per move (Fischer); 0 - no increment
    readonly label: string;
    readonly details: string;
    isManual?: boolean;
}

export interface TimeControlGroup {
    category: TimeControlCategory;
    readonly title: string;
    options: TimeControlOption[];
}

/** Preset label: "3 min + 2 sec/move" in the current language. */
export function timeControlLabel(base: number, inc: number): string {
    return inc > 0 ? t('timeControl.minutesIncrement', {base, inc}) : t('timeControl.minutes', {base});
}

function option(category: TimeControlCategory, base: number, inc: number, manual = false): TimeControlOption {
    const id = (manual ? `${category}-manual` : `${category}-${base}+${inc}`) as TimeControlId;
    return {
        id,
        category,
        base,
        inc,
        ...(manual ? {isManual: true} : {}),
        get label() {
            return manual
                ? t('timeControl.manual', {category: t(`ratingCategory.${category}`)})
                : timeControlLabel(base, inc);
        },
        get details() {
            return t(`timeControl.details.${id}`);
        },
    };
}

function group(category: TimeControlCategory, options: TimeControlOption[]): TimeControlGroup {
    return {
        category,
        options,
        get title() {
            return t(`ratingCategory.${category}`);
        },
    };
}

export const TIME_CONTROLS: TimeControlGroup[] = [
    group('bullet', [
        option('bullet', 1, 0),
        option('bullet', 1, 1),
        option('bullet', 2, 1),
        option('bullet', 1, 0, true),
    ]),
    group('blitz', [
        option('blitz', 3, 0),
        option('blitz', 3, 2),
        option('blitz', 5, 0),
        option('blitz', 5, 3),
        option('blitz', 5, 0, true),
    ]),
    group('rapid', [
        option('rapid', 10, 0),
        option('rapid', 10, 5),
        option('rapid', 15, 10),
        option('rapid', 15, 10, true),
    ]),
    group('classical', [
        // 30 minutes with no increment is already classical: the server (classify_time_control) assigns the game
        // to a category by the estimate "base + 40 x increment", the classical threshold is 25 minutes.
        option('classical', 30, 0),
        option('classical', 30, 20),
        option('classical', 60, 30),
        option('classical', 60, 30, true),
    ]),
];

export const ALL_TIME_CONTROLS: TimeControlOption[] = TIME_CONTROLS.flatMap(g => g.options);
export const DEFAULT_TIME_CONTROL: TimeControlOption =
    ALL_TIME_CONTROLS.find(o => o.id === 'blitz-3+2') || ALL_TIME_CONTROLS[0];

/**
 * Control category - the same rule as on the server (src/services/rating.classify_time_control): duration estimate
 * "base + 40 x increment"; bullet - up to 3 minutes, blitz - up to 8, rapid - up to 25, beyond that classical.
 */
export function timeControlCategory(baseMs: number, incrementMs: number): TimeControlCategory {
    const estimatedS = baseMs / 1000 + 40 * (incrementMs / 1000);
    if (estimatedS < 180) return 'bullet';
    if (estimatedS < 480) return 'blitz';
    if (estimatedS < 1500) return 'rapid';
    return 'classical';
}
