// The chosen UI language for E2E: the site is English by default and does not guess the browser language (owner decision
// 22.11), so scenarios put into localStorage in advance the language they are written for — as a player does in the header.

import type {Language} from '../src/i18n/core.ts';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:8080';

/** Playwright storageState with the chosen language; origin is the address of the stand. */
export function languageState(language: Language) {
    return {
        cookies: [],
        origins: [{origin: new URL(BASE_URL).origin, localStorage: [{name: 'regence_language', value: language}]}],
    };
}
