// --- FILE: frontend/src/i18n/messages/languageNames.ts ---
// Native language names. They are not translated: in the switcher people look for a language by its own name,
// so "Українська" is written in Ukrainian whatever the interface language is.

import type {Language} from '../core';

export const LANGUAGE_NATIVE_NAMES: Record<Language, string> = {
    en: 'English',
    uk: 'Українська',
};

/**
 * Short language labels in the compact switcher. The language code in the app is ISO 639-1 (uk),
 * but the label for Ukrainian is "UA": "UK" reads as the United Kingdom.
 */
export const LANGUAGE_SHORT_LABELS: Record<Language, string> = {
    en: 'EN',
    uk: 'UA',
};
