// Catalogs in their own alphabet: Ukrainian has no Russian-only letters (the hard sign, e-reverse, yery, yo); English has no Cyrillic.
// Catches texts copied into the wrong catalog without translation. The letters are written as \u escapes so that
// this file itself contains no Cyrillic.

import {describe, expect, it} from 'vitest';
import {en} from '../messages/en';
import {uk} from '../messages/uk';

function flatten(value: unknown, prefix = ''): [string, string][] {
    if (typeof value === 'string') return [[prefix, value]];
    if (value && typeof value === 'object') {
        return Object.entries(value).flatMap(([key, inner]) => flatten(inner, prefix ? `${prefix}.${key}` : key));
    }
    return [];
}

/** Letters that exist only in Russian: yery, e-reverse, hard sign, yo (lower and upper case). */
const RUSSIAN_ONLY = /[\u044B\u044D\u044A\u0451\u042B\u042D\u042A\u0401]/;
/** Any Cyrillic letter (the whole block). */
const ANY_CYRILLIC = /[\u0400-\u04FF]/;

// Proper names and quotations where a "foreign" letter is legitimate (key → reason).
const ALLOWED: Record<string, RegExp> = {};

function offenders(catalog: unknown, forbidden: RegExp): string[] {
    return flatten(catalog)
        .filter(([key, text]) => forbidden.test(text) && !(ALLOWED[key]?.test(text)))
        .map(([key, text]) => `${key}: ${text.slice(0, 100)}`);
}

describe('catalog alphabet', () => {
    it('the catalogs are read in full', () => {
        expect(flatten(uk).length).toBeGreaterThan(3000);
        expect(flatten(en).length).toBeGreaterThan(3000);
    });

    it('Ukrainian — without Russian-only letters', () => {
        const found = offenders(uk, RUSSIAN_ONLY);
        expect(found, `\n${found.join('\n')}`).toEqual([]);
    });

    it('English — without Cyrillic', () => {
        const found = offenders(en, ANY_CYRILLIC);
        expect(found, `\n${found.join('\n')}`).toEqual([]);
    });
});

// Content texts (lessons, classics, courses): the uk / en fields inside JSON.
const CONTENT = import.meta.glob<unknown>('../../content/**/*.json', {eager: true, import: 'default'});

function localized(value: unknown, path: string, out: [string, string, string][]) {
    if (Array.isArray(value)) {
        value.forEach((inner, i) => localized(inner, `${path}[${i}]`, out));
    } else if (value && typeof value === 'object') {
        for (const [key, inner] of Object.entries(value)) {
            if ((key === 'uk' || key === 'en') && typeof inner === 'string') out.push([`${path}.${key}`, key, inner]);
            else localized(inner, `${path}.${key}`, out);
        }
    }
}

describe('content text alphabet', () => {
    it('uk / en in JSON — in their own alphabet', () => {
        const texts: [string, string, string][] = [];
        for (const [file, data] of Object.entries(CONTENT)) localized(data, file.replace('../../content/', ''), texts);
        expect(texts.length).toBeGreaterThan(500);
        const forbidden: Record<string, RegExp> = {uk: RUSSIAN_ONLY, en: ANY_CYRILLIC};
        const found = texts.filter(([, lang, text]) => forbidden[lang].test(text)).map(([path, , text]) => `${path}: ${text.slice(0, 90)}`);
        expect(found, `\n${found.join('\n')}`).toEqual([]);
    });
});
