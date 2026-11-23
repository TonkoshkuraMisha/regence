// A single glossary of chess terms (task 17.7): a term is written the same way everywhere in the catalog.

import {describe, expect, it} from 'vitest';
import {LANGUAGES} from '../index';
import {GLOSSARY} from '../messages/glossary';
import {catalogEntries, findKeysByText} from '../catalogIndex';

describe('term glossary', () => {
    it('every term has both languages, without repeats', () => {
        expect(new Set(GLOSSARY.map((term) => term.id)).size).toBe(GLOSSARY.length);
        for (const term of GLOSSARY) for (const language of LANGUAGES) expect(term[language].trim()).not.toBe('');
    });

    for (const language of LANGUAGES) {
        it(`the ${language} catalog has no undesirable spellings of terms`, () => {
            const problems: string[] = [];
            for (const term of GLOSSARY) {
                for (const source of term.avoid?.[language] ?? []) {
                    const pattern = new RegExp(`(?<!\\p{L})${source}`, 'iu');
                    for (const entry of catalogEntries(language)) {
                        if (entry.texts.some((text) => pattern.test(text))) problems.push(`${term.id}: ${entry.key} ~ /${source}/`);
                    }
                }
            }
            expect(problems).toEqual([]);
        });
    }

    it('undesirable variants do not match the term itself', () => {
        for (const term of GLOSSARY) {
            for (const language of LANGUAGES) {
                for (const source of term.avoid?.[language] ?? []) {
                    expect(new RegExp(`(?<!\\p{L})${source}`, 'iu').test(term[language])).toBe(false);
                }
            }
        }
    });

    it('there are no Latin look-alike letters inside Cyrillic words', () => {
        const mixed = /\p{Script=Cyrillic}[a-zA-Z]|[a-zA-Z]\p{Script=Cyrillic}/u;
        for (const language of ['uk'] as const) {
            const bad = catalogEntries(language).filter((entry) => entry.texts.some((text) => mixed.test(text))).map((e) => e.key);
            expect(bad).toEqual([]);
        }
    });
});

describe('finding a key by text', () => {
    it('finds an exact text and a template with parameters', () => {
        expect(findKeysByText('en', 'Skewer')).toContain('themes.skewer.name');
        expect(findKeysByText('en', 'Report sent')).toEqual(['moderation.reportSent']);
        expect(findKeysByText('en', 'from magnus')).toContain('moderation.from');
        expect(findKeysByText('en', '   ')).toEqual([]);
    });
});
