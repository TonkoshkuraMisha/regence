// --- FILE: frontend/src/i18n/index.tsx ---
// Current language and translation. The language is a module store (useSyncExternalStore), not a React context: translation
// is needed outside components too (WebSocket service, sounds, configs), and components work without a provider wrapper -
// including in tests where they are rendered one by one.

import {Fragment, useMemo, useSyncExternalStore, type ReactNode} from 'react';
import {enUS, uk as ukDateLocale, type Locale} from 'date-fns/locale';
import {
    DEFAULT_LANGUAGE,
    interpolate,
    interpolateParts,
    isLanguage,
    isPlural,
    lookup,
    selectPlural,
    type Language,
    type Params,
    type PluralKey,
    type TextKey,
} from './core';
import {en, type Messages} from './messages/en';
import {uk} from './messages/uk';

export * from './core';
export {LANGUAGE_NATIVE_NAMES, LANGUAGE_SHORT_LABELS} from './messages/languageNames';
export type {Messages};

export const CATALOGS: Record<Language, Messages> = {en, uk};

export type MessageKey = TextKey<Messages>;
export type MessagePluralKey = PluralKey<Messages>;

const DATE_LOCALES: Record<Language, Locale> = {en: enUS, uk: ukDateLocale};

export const LANGUAGE_STORAGE_KEY = 'regence_language';

function readStoredLanguage(): Language | null {
    try {
        const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
        return isLanguage(stored) ? stored : null;
    } catch {
        return null;
    }
}

// The default language is English (owner's decision of 22.11): the browser language is not guessed, the player chooses, the choice is remembered.
let currentLanguage: Language = readStoredLanguage() ?? DEFAULT_LANGUAGE;
const listeners = new Set<() => void>();

function applyDocumentLanguage(language: Language) {
    if (typeof document !== 'undefined') document.documentElement.lang = language;
}

applyDocumentLanguage(currentLanguage);

export function getLanguage(): Language {
    return currentLanguage;
}

export function setLanguage(language: Language, {persist = true}: { persist?: boolean } = {}): void {
    if (persist) {
        try {
            localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
        } catch {
            // private mode or storage blocked - the language just will not be remembered
        }
    }
    if (language === currentLanguage) return;
    currentLanguage = language;
    applyDocumentLanguage(language);
    listeners.forEach((listener) => listener());
}

export function subscribeLanguage(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

function reportMissing(language: Language, key: string) {
    if (import.meta.env.DEV) console.error(`[i18n] missing message "${key}" for language ${language}`);
}

export function translate(language: Language, key: MessageKey, params?: Params): string {
    const value = lookup(CATALOGS[language], key);
    if (typeof value === 'string') return interpolate(value, params);
    reportMissing(language, key);
    const fallback = lookup(CATALOGS.en, key);
    return typeof fallback === 'string' ? interpolate(fallback, params) : key;
}

export function translatePlural(language: Language, key: MessagePluralKey, count: number, params?: Params): string {
    const value = lookup(CATALOGS[language], key);
    const message = isPlural(value) ? value : lookup(CATALOGS.en, key);
    if (!isPlural(message)) {
        reportMissing(language, key);
        return key;
    }
    return interpolate(selectPlural(language, message, count), {count, ...params});
}

/** Translation in the current language - for code outside components. In components use useI18n() to re-render on change. */
export function t(key: MessageKey, params?: Params): string {
    return translate(currentLanguage, key, params);
}

export function tp(key: MessagePluralKey, count: number, params?: Params): string {
    return translatePlural(currentLanguage, key, count, params);
}

/** date-fns locale of the current language - for date formatting outside components. */
export function getDateLocale(): Locale {
    return DATE_LOCALES[currentLanguage];
}

export interface I18n {
    language: Language;
    t: (key: MessageKey, params?: Params) => string;
    tp: (key: MessagePluralKey, count: number, params?: Params) => string;
    /** A message with elements substituted (links, emphasis): the whole sentence stays in the catalog. */
    rich: (key: MessageKey, params: Record<string, ReactNode | string | number>) => ReactNode;
    dateLocale: Locale;
    setLanguage: (language: Language) => void;
}

export function makeI18n(language: Language): I18n {
    return {
        language,
        t: (key, params) => translate(language, key, params),
        tp: (key, count, params) => translatePlural(language, key, count, params),
        rich: (key, params) => {
            const template = translate(language, key);
            const parts = interpolateParts<ReactNode>(template, params);
            return parts.map((part, index) => <Fragment key={index}>{part}</Fragment>);
        },
        dateLocale: DATE_LOCALES[language],
        setLanguage,
    };
}

export function useI18n(): I18n {
    const language = useSyncExternalStore(subscribeLanguage, getLanguage, getLanguage);
    return useMemo(() => makeI18n(language), [language]);
}

/**
 * Message for display: a catalog key with parameters (translated on every display - hence also after a language
 * change) or text as is (a name sent by the server, or error text whose code the client does not know yet).
 * A parameter can itself be a message: "The bot could not make a move: {detail}", where detail is a server error.
 */
export type UiMessage = { key: MessageKey; params?: Record<string, MessageParam> } | { text: string };

export type MessageParam = string | number | UiMessage;

export function uiMessage(key: MessageKey, params?: Record<string, MessageParam>): UiMessage {
    return params ? {key, params} : {key};
}

/** Whether such a string key exists in the catalog (reference - English): for codes that came from the server. */
export function hasMessage(key: string): key is MessageKey {
    return typeof lookup(CATALOGS.en, key) === 'string';
}

export function renderUiMessage(message: UiMessage, translateFn: I18n['t']): string {
    if ('text' in message) return message.text;
    if (!message.params) return translateFn(message.key);
    const rendered: Params = {};
    for (const [name, param] of Object.entries(message.params)) {
        rendered[name] = typeof param === 'object' ? renderUiMessage(param, translateFn) : param;
    }
    return translateFn(message.key, rendered);
}
