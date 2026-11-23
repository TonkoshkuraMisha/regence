// --- FILE: frontend/src/i18n/core.ts ---
// Message catalog engine: languages, plurals, parameter substitution, typed keys.
// Texts are in messages/*.ts; all catalogs must have the same keys (checked by TypeScript through the
// Messages type) and the same parameters and plural forms (checked by the i18n.test.ts test).

export const LANGUAGES = ['en', 'uk'] as const;
export type Language = (typeof LANGUAGES)[number];

export const DEFAULT_LANGUAGE: Language = 'en';


export type PluralCategory = 'zero' | 'one' | 'two' | 'few' | 'many' | 'other';

/** Forms of one message for different numbers. Which are needed is decided by the language's Intl.PluralRules. */
export interface Plural {
    readonly kind: 'plural';
    readonly forms: Partial<Record<PluralCategory, string>> & { other: string };
}

/** Message with plural forms: plural({one: '{count} game', other: '{count} games'}). */
export function plural(forms: Plural['forms']): Plural {
    return {kind: 'plural', forms};
}

export function isPlural(value: unknown): value is Plural {
    return typeof value === 'object' && value !== null && (value as Plural).kind === 'plural';
}

// --- key types -------------------------------------------------------------------------------------------

type Join<P extends string, K extends string> = P extends '' ? K : `${P}.${K}`;

/** Keys of ordinary messages: "settings.title", "auth.login.submit"... */
export type TextKey<T, P extends string = ''> = {
    [K in keyof T & string]: T[K] extends string
        ? Join<P, K>
        : T[K] extends Plural
            ? never
            : TextKey<T[K], Join<P, K>>;
}[keyof T & string];

/** Keys of messages with plural forms. */
export type PluralKey<T, P extends string = ''> = {
    [K in keyof T & string]: T[K] extends string
        ? never
        : T[K] extends Plural
            ? Join<P, K>
            : PluralKey<T[K], Join<P, K>>;
}[keyof T & string];

export type Params = Record<string, string | number>;

// --- substitution -------------------------------------------------------------------------------------------

const PLACEHOLDER = /\{(\w+)\}/g;

/** Template parameter names in order of appearance (for catalog checks). */
export function placeholders(template: string): string[] {
    return Array.from(template.matchAll(PLACEHOLDER), (match) => match[1]);
}

/**
 * Substitutes parameters into a template. A missing parameter stays visible as {name} - so the error is seen on
 * screen and in tests, instead of a silent "undefined".
 */
export function interpolate(template: string, params?: Params): string {
    if (!params) return template;
    return template.replace(PLACEHOLDER, (whole, name: string) =>
        Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : whole);
}

/**
 * Splits a template into pieces: strings and substituted values of any type (for example, React elements - links
 * inside a sentence). The sentence stays whole in the catalog, only "where to insert" goes into code.
 */
export function interpolateParts<T>(template: string, params: Record<string, T | string | number>): Array<T | string> {
    const parts: Array<T | string> = [];
    let last = 0;
    for (const match of template.matchAll(PLACEHOLDER)) {
        const index = match.index ?? 0;
        if (index > last) parts.push(template.slice(last, index));
        const name = match[1];
        const value = Object.prototype.hasOwnProperty.call(params, name) ? params[name] : match[0];
        parts.push(typeof value === 'number' ? String(value) : value);
        last = index + match[0].length;
    }
    if (last < template.length) parts.push(template.slice(last));
    return parts;
}

const pluralRulesCache = new Map<Language, Intl.PluralRules>();

export function pluralCategory(language: Language, count: number): PluralCategory {
    let rules = pluralRulesCache.get(language);
    if (!rules) {
        rules = new Intl.PluralRules(language);
        pluralRulesCache.set(language, rules);
    }
    return rules.select(count) as PluralCategory;
}

/** Plural forms required by a language (for catalog checks): en - one/other, uk - one/few/many/other. */
export function requiredPluralCategories(language: Language): PluralCategory[] {
    return new Intl.PluralRules(language).resolvedOptions().pluralCategories as PluralCategory[];
}

export function selectPlural(language: Language, value: Plural, count: number): string {
    const category = pluralCategory(language, count);
    return value.forms[category] ?? value.forms.other;
}

/** Value at the path "a.b.c" in the catalog, or undefined. */
export function lookup(catalog: unknown, key: string): unknown {
    let node: unknown = catalog;
    for (const part of key.split('.')) {
        if (typeof node !== 'object' || node === null || isPlural(node)) return undefined;
        node = (node as Record<string, unknown>)[part];
    }
    return node;
}

/** Language choice from the browser's language list: Ukrainian is its own, everything else is English. */
export function detectLanguage(preferred: readonly string[]): Language {
    for (const tag of preferred) {
        const base = tag.toLowerCase().split('-')[0];
        if ((LANGUAGES as readonly string[]).includes(base)) return base as Language;
    }
    return DEFAULT_LANGUAGE;
}

export function isLanguage(value: unknown): value is Language {
    return typeof value === 'string' && (LANGUAGES as readonly string[]).includes(value);
}
