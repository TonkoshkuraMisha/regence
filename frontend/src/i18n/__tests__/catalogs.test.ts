// --- FILE: frontend/src/i18n/__tests__/catalogs.test.ts ---
// Catalog integrity: TypeScript (the Messages type) guarantees identical keys, and this test covers everything
// the types cannot express: identical parameters in all languages, a full set of plural forms, no empty strings
// and no letters of a foreign language (this catches a string that was forgotten to be translated or was copied from the neighbouring catalog).

import {describe, expect, it} from 'vitest';
import {
    CATALOGS,
    LANGUAGES,
    isPlural,
    placeholders,
    requiredPluralCategories,
    type Language,
    type Plural,
} from '../index';

type Leaf = { key: string; value: string | Plural };

function leaves(node: unknown, prefix = ''): Leaf[] {
    if (typeof node === 'string' || isPlural(node)) return [{key: prefix, value: node as string | Plural}];
    return Object.entries(node as Record<string, unknown>).flatMap(([key, child]) =>
        leaves(child, prefix ? `${prefix}.${key}` : key));
}

const byLanguage = Object.fromEntries(
    LANGUAGES.map((language) => [language, new Map(leaves(CATALOGS[language]).map((leaf) => [leaf.key, leaf.value]))]),
) as Record<Language, Map<string, string | Plural>>;

const texts = (value: string | Plural): string[] => (typeof value === 'string' ? [value] : Object.values(value.forms));
const paramSet = (value: string | Plural): string[] =>
    [...new Set(texts(value).flatMap(placeholders))].filter((name) => name !== 'count').sort();

// Letters that do not exist in the language: English has no Cyrillic at all, Ukrainian has no yery, e-reverse, hard sign or yo.
// Written as \u escapes so that this file itself contains no Cyrillic.
const FOREIGN_LETTERS: Record<Language, RegExp> = {
    en: /[\u0400-\u04FF]/,
    uk: /[\u044B\u044D\u044A\u0451\u042B\u042D\u042A\u0401]/,
};

describe('message catalogs', () => {
    const keys = [...byLanguage.en.keys()];

    it('all languages have the same keys', () => {
        for (const language of LANGUAGES) {
            expect([...byLanguage[language].keys()].sort()).toEqual([...keys].sort());
        }
    });

    it.each(keys)('"%s": identical parameters in all languages', (key) => {
        const expected = paramSet(byLanguage.en.get(key)!);
        for (const language of LANGUAGES) {
            expect(paramSet(byLanguage[language].get(key)!), `${language}: ${key}`).toEqual(expected);
        }
    });

    it.each(LANGUAGES)('%s: all plural forms are present and carry {count}', (language) => {
        const required = requiredPluralCategories(language);
        for (const [key, value] of byLanguage[language]) {
            if (!isPlural(value)) continue;
            for (const category of required) {
                expect(value.forms[category], `${language}: ${key} — no ${category} form`).toBeTruthy();
                expect(value.forms[category], `${language}: ${key}.${category}`).toContain('{count}');
            }
        }
    });

    it.each(LANGUAGES)('%s: no empty strings and no letters of a foreign language', (language) => {
        for (const [key, value] of byLanguage[language]) {
            for (const text of texts(value)) {
                expect(text.trim(), `${language}: ${key} is empty`).not.toBe('');
                expect(FOREIGN_LETTERS[language].test(text), `${language}: ${key} = "${text}"`).toBe(false);
            }
        }
    });

    it('a plural-form key is the same in all languages', () => {
        for (const key of keys) {
            const kinds = LANGUAGES.map((language) => isPlural(byLanguage[language].get(key)));
            expect(new Set(kinds).size, key).toBe(1);
        }
    });
});
