// Appearance and "Report a problem" in a real browser against the full stack (tasks 31.1 and 24.4).
// A theme preset changes the page background itself: until 17.11 the app's root block covered it, and the chosen pattern was
// visible only in the settings preview — unit tests checked the body style, not what the player sees.

import {expect, test} from '@playwright/test';
import {loginNewPlayer} from './helpers.ts';

test('"Autumn park" theme: page background is visible, the choice survives a reload', async ({page}) => {
    await page.goto('/settings');
    await page.getByTestId('preset-autumn_park').click();

    // The background is set on body, and the app's root block does not cover it.
    const look = async () => await page.evaluate(`(() => {
        const root = document.querySelector('#root > div');
        return {
            image: getComputedStyle(document.body).backgroundImage,
            color: getComputedStyle(document.body).backgroundColor,
            cover: root ? getComputedStyle(root).backgroundColor : 'no root',
            board: localStorage.getItem('regence_board_theme'),
        };
    })()`) as { image: string; color: string; cover: string; board: string | null };
    await expect.poll(async () => (await look()).image).toContain('/assets/patterns/leaves.svg');
    const chosen = await look();
    expect(chosen.color).toBe('rgb(58, 40, 20)');
    expect(chosen.cover).toBe('rgba(0, 0, 0, 0)');
    expect(chosen.board).toBe('autumn');

    // The pattern itself is served by the server as an image, not as a placeholder page.
    const tile = await page.request.get('/assets/patterns/leaves.svg');
    expect(tile.ok()).toBe(true);
    expect(tile.headers()['content-type']).toContain('svg');

    await page.reload();
    await expect.poll(async () => (await look()).image).toContain('/assets/patterns/leaves.svg');
    expect((await look()).cover).toBe('rgba(0, 0, 0, 0)');
});

test('report a problem: a guest sends a message, the server accepts it', async ({page}) => {
    await page.goto('/about');
    await page.getByTestId('report-problem-open').click();
    await expect(page.getByTestId('report-problem')).toBeVisible();
    await page.getByTestId('report-problem-text').fill('End-to-end check: a guest message from the "About" page.');
    // The page address is sent with the message — it is shown in the dialog.
    await expect(page.getByTestId('report-problem-context')).toContainText('/about');
    const [response] = await Promise.all([
        page.waitForResponse((r) => r.url().includes('/api/v1/beta/feedback') && r.request().method() === 'POST'),
        page.getByTestId('report-problem-send').click(),
    ]);
    expect(response.status()).toBeLessThan(300);
    await expect(page.getByTestId('report-problem-sent')).toBeVisible();
});

test('after a direct visit a logged-in player immediately sees the page with their session and opens the message dialog', async ({page, request}) => {
    await loginNewPlayer(page, request, 'report');
    await page.setViewportSize({width: 1366, height: 768});
    // Direct visit: the session is restored from the cookie before the first page — the page area is never left empty.
    await page.goto('/library');
    await expect(page.getByTestId('session-restoring')).toHaveCount(0);
    await page.getByTestId('report-problem-open').click();
    await expect(page.getByTestId('report-problem')).toBeVisible();
    await expect(page.getByTestId('report-problem-context')).toContainText('/library');
});
