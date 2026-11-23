// --- FILE: frontend/src/i18n/__tests__/core.test.tsx ---
// The translation mechanism: substitution, plural forms, choosing and changing the language, re-rendering components.

import {act, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';
import {
    LANGUAGE_STORAGE_KEY,
    detectLanguage,
    getLanguage,
    interpolate,
    interpolateParts,
    makeI18n,
    pluralCategory,
    setLanguage,
    t,
    translate,
    translatePlural,
    useI18n,
} from '../index';

afterEach(() => {
    setLanguage('en', {persist: false});
    localStorage.clear();
});

describe('parameter substitution', () => {
    it('substitutes parameters and leaves the missing ones visible', () => {
        expect(interpolate('{a} and {b}', {a: 1, b: 'two'})).toBe('1 and two');
        expect(interpolate('{a} and {b}', {a: 1})).toBe('1 and {b}');
        expect(interpolate('no parameters')).toBe('no parameters');
    });

    it('substitutes elements without breaking the sentence', () => {
        const link = {type: 'link'};
        expect(interpolateParts('Code — {link}. Done', {link})).toEqual(['Code — ', link, '. Done']);
        expect(interpolateParts('{n} pcs.', {n: 3})).toEqual(['3', ' pcs.']);
    });
});

describe('plural forms', () => {
    it.each([
        [1, 'one'], [2, 'few'], [4, 'few'], [5, 'many'], [11, 'many'], [21, 'one'], [22, 'few'], [25, 'many'], [1.5, 'other'],
    ])('uk: %s → %s', (count, category) => {
        expect(pluralCategory('uk', count)).toBe(category);
    });

    it('English: one / other', () => {
        expect(pluralCategory('en', 1)).toBe('one');
        expect(pluralCategory('en', 2)).toBe('other');
    });

    it('chooses the form and substitutes count', () => {
        expect(translatePlural('uk', 'auth.importConfirm', 2)).toContain('збережено 2 суперники');
        expect(translatePlural('uk', 'auth.importConfirm', 5)).toContain('збережено 5 суперників');
        expect(translatePlural('en', 'auth.importConfirm', 1)).toContain('1 workshop opponent saved');
        expect(translatePlural('en', 'auth.importConfirm', 4)).toContain('4 workshop opponents saved');
    });
});

describe('language choice', () => {
    it.each([
        [['uk-UA'], 'uk'], [['ru'], 'en'], [['en-GB'], 'en'], [['de-DE', 'uk'], 'uk'], [['fr', 'pl'], 'en'], [[], 'en'],
    ])('browser %j → %s', (preferred, expected) => {
        expect(detectLanguage(preferred)).toBe(expected);
    });

    it('a language change is remembered and changes the document lang', () => {
        setLanguage('uk');
        expect(getLanguage()).toBe('uk');
        expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('uk');
        expect(document.documentElement.lang).toBe('uk');
        expect(t('settings.title')).toBe('Налаштування');
    });

    it('the same key in both languages', () => {
        expect(translate('en', 'nav.leaderboard')).toBe('Leaderboard');
        expect(translate('uk', 'nav.leaderboard')).toBe('Лідери');
    });

    it('rich substitutes elements into a whole sentence', () => {
        const {rich} = makeI18n('en');
        render(<p data-testid="p">{rich('about.engineText', {link: <a href="https://example.org">source</a>})}</p>);
        expect(screen.getByTestId('p').textContent).toMatch(/^Game analysis .* the source code is at source\. The engine/);
        expect(screen.getByRole('link', {name: 'source'})).toBeInTheDocument();
    });
});

function Title() {
    const {t: translateHere, language} = useI18n();
    return <h1 data-language={language}>{translateHere('settings.title')}</h1>;
}

describe('useI18n', () => {
    it('a component re-renders on a language change without a reload', () => {
        setLanguage('en', {persist: false});
        render(<Title/>);
        expect(screen.getByRole('heading')).toHaveTextContent('Settings');

        act(() => setLanguage('uk'));
        expect(screen.getByRole('heading')).toHaveTextContent('Налаштування');
        expect(screen.getByRole('heading')).toHaveAttribute('data-language', 'uk');

        act(() => setLanguage('en'));
        expect(screen.getByRole('heading')).toHaveTextContent('Settings');
        expect(screen.getByRole('heading')).toHaveAttribute('data-language', 'en');
    });
});
