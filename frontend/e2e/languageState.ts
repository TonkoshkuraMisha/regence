// Выбранный язык интерфейса для E2E: сайт по умолчанию английский и язык браузера не угадывает (решение владельца
// 22.11), поэтому сценарии заранее кладут в localStorage тот язык, на который они написаны, — как это делает игрок в шапке.

import type {Language} from '../src/i18n/core.ts';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:8080';

/** storageState Playwright с выбранным языком; origin — адрес стенда. */
export function languageState(language: Language) {
    return {
        cookies: [],
        origins: [{origin: new URL(BASE_URL).origin, localStorage: [{name: 'regence_language', value: language}]}],
    };
}
