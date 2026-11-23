// UI language in a real browser: English by default for any browser language (owner decision 22.11),
// switches in the header without a reload and is remembered — after a reload the page stays in the chosen language.

import {expect, test} from '@playwright/test';

test.describe('UI language', () => {
    test('a Ukrainian browser still gets English; the choice of Ukrainian survives a reload', async ({browser}) => {
        const context = await browser.newContext({locale: 'uk-UA', storageState: {cookies: [], origins: []}});
        const page = await context.newPage();
        await page.goto('/');

        await expect(page.locator('html')).toHaveAttribute('lang', 'en');
        await expect(page.getByRole('link', {name: 'Play'})).toBeVisible();
        await expect(page.getByRole('button', {name: 'Log in'})).toBeVisible();

        await page.getByRole('combobox', {name: 'Language'}).selectOption('uk');
        await expect(page.locator('html')).toHaveAttribute('lang', 'uk');
        await expect(page.getByRole('link', {name: 'Гра'})).toBeVisible();
        await expect(page.getByRole('button', {name: 'Увійти'})).toBeVisible();

        await page.reload();
        await expect(page.getByRole('link', {name: 'Гра'})).toBeVisible();
        await context.close();
    });

    test('a browser with an unsupported language gets English', async ({browser}) => {
        const context = await browser.newContext({locale: 'de-DE', storageState: {cookies: [], origins: []}});
        const page = await context.newPage();
        await page.goto('/');

        await expect(page.locator('html')).toHaveAttribute('lang', 'en');
        await page.getByRole('button', {name: 'Log in'}).click();
        await expect(page.getByRole('dialog', {name: 'Log in to regence'})).toBeVisible();
        await context.close();
    });
});
