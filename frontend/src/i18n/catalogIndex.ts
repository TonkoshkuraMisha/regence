// --- FILE: frontend/src/i18n/catalogIndex.ts ---
// Flat "key -> texts" list of the catalog (task 17.7): the term glossary checks the catalogs through it, and the "translation
// helper" mode finds the key by the text the player clicked.

import {isPlural, type Language} from './core';
import {CATALOGS} from './index';

export interface CatalogEntry {
    key: string;
    /** The string itself or all plural forms. */
    texts: string[];
}

function walk(node: unknown, prefix: string, out: CatalogEntry[]): void {
    if (typeof node === 'string') {
        out.push({key: prefix, texts: [node]});
    } else if (isPlural(node)) {
        out.push({key: prefix, texts: Object.values(node.forms).filter((v): v is string => typeof v === 'string')});
    } else if (node && typeof node === 'object') {
        for (const [key, child] of Object.entries(node)) walk(child, prefix ? `${prefix}.${key}` : key, out);
    }
}

const cache = new Map<Language, CatalogEntry[]>();

export function catalogEntries(language: Language): CatalogEntry[] {
    let entries = cache.get(language);
    if (!entries) {
        entries = [];
        walk(CATALOGS[language], '', entries);
        cache.set(language, entries);
    }
    return entries;
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Keys whose text (with any substituted parameters) matches the displayed one; exact matches first. */
export function findKeysByText(language: Language, shown: string): string[] {
    const text = shown.replace(/\s+/g, ' ').trim();
    if (!text) return [];
    const exact: string[] = [];
    const templated: string[] = [];
    for (const entry of catalogEntries(language)) {
        for (const template of entry.texts) {
            const normalized = template.replace(/\s+/g, ' ').trim();
            if (normalized === text) {
                exact.push(entry.key);
                break;
            }
            if (normalized.includes('{')) {
                const pattern = new RegExp(`^${normalized.split(/\{\w+\}/).map(escape).join('.+?')}$`, 's');
                if (pattern.test(text)) {
                    templated.push(entry.key);
                    break;
                }
            }
        }
    }
    return [...exact, ...templated];
}
