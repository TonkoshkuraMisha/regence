/// <reference lib="dom" />
// The app on a phone (task 24.2) on the production stack: the manifest with icons is served by nginx with the right type,
// the service worker registers and takes the page under control, without a network the player's own offline page replaces the browser error
// in the player's language, and with a connection back — the site again.

import {expect, test} from '@playwright/test';

test('manifest and icons', async ({request}) => {
    const response = await request.get('/manifest.webmanifest');
    expect(response.ok()).toBe(true);
    expect(response.headers()['content-type']).toContain('application/manifest+json');
    const manifest = await response.json();
    expect(manifest).toMatchObject({start_url: '/', display: 'standalone'});
    const purposes = manifest.icons.map((icon: { purpose: string }) => icon.purpose);
    expect(purposes).toContain('maskable');
    for (const icon of manifest.icons as { src: string; type: string }[]) {
        const file = await request.get(icon.src);
        expect(file.ok(), icon.src).toBe(true);
        expect(file.headers()['content-type'], icon.src).toContain(icon.type);
    }
    const worker = await request.get('/sw.js');
    expect(worker.ok()).toBe(true);
    expect(worker.headers()['cache-control']).toContain('no-cache');
});

test('service worker and offline page', async ({page, context}) => {
    await page.goto('/');
    await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('href', '/manifest.webmanifest');
    const scope = await page.evaluate(async () => (await navigator.serviceWorker.ready).scope);
    expect(new URL(scope).pathname).toBe('/');
    // The worker takes the page under control after clients.claim(); a reload is the sure way.
    await page.reload();
    await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);

    await context.setOffline(true);
    try {
        await page.goto('/puzzles');
        await expect(page.locator('#offline-title')).toHaveText('No connection');
        await expect(page.locator('#offline-retry')).toHaveText('Try again');
    } finally {
        await context.setOffline(false);
    }
    // The connection is back: the offline page reloads itself (the online event in offline.js). Our own navigation may
    // collide with that reload ("navigation interrupted"), so we retry until the site opens.
    await expect(async () => {
        await page.goto('/puzzles');
        await expect(page.locator('#offline-title')).toHaveCount(0, {timeout: 2000});
        await expect(page.locator('#root')).not.toBeEmpty({timeout: 2000});
    }).toPass({timeout: 20_000});
});
