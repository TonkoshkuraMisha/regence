// Язык интерфейса в настоящем браузере: по умолчанию английский при любом языке браузера (решение владельца 22.11),
// переключается в шапке без перезагрузки и запоминается — после перезагрузки страница остаётся на выбранном языке.

import {expect, test} from '@playwright/test';

test.describe('язык интерфейса', () => {
    test('украинский браузер всё равно получает английский; выбор украинского переживает перезагрузку', async ({browser}) => {
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

    test('браузер на неподдерживаемом языке получает английский', async ({browser}) => {
        const context = await browser.newContext({locale: 'de-DE', storageState: {cookies: [], origins: []}});
        const page = await context.newPage();
        await page.goto('/');

        await expect(page.locator('html')).toHaveAttribute('lang', 'en');
        await page.getByRole('button', {name: 'Log in'}).click();
        await expect(page.getByRole('dialog', {name: 'Log in to regence'})).toBeVisible();
        await context.close();
    });
});
