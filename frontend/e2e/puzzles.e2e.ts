// Puzzles on a real server with the full database (24,530 puzzles from an open database): the jump from the header, a puzzle being served,
// the opponent's move, "Show solution" — the result and the solution, the next puzzle, the history and the solver's rating.

import {expect, test} from '@playwright/test';

const PASSWORD = 'e2e-pass-12345';

test('puzzles: serving, showing the solution, the next puzzle and the history', async ({page, request}) => {
    const username = `puz_${Date.now().toString(36)}`;
    expect((await request.post('/api/v1/auth/register', {data: {username, password: PASSWORD, accept_terms: true}})).ok()).toBe(true);
    // Login in the page context: the refresh cookie restores it on load (task 17.5).
    expect((await page.request.post('/api/v1/auth/login', {form: {username, password: PASSWORD}})).ok()).toBe(true);

    await page.goto('/');
    await page.getByRole('banner').getByRole('link', {name: 'Puzzles'}).click();
    await expect(page).toHaveURL(/\/puzzles$/);

    await page.getByTestId('puzzle-next').click();
    // The opponent moves first, then the solver's move.
    await expect(page.getByTestId('puzzle-status')).toContainText('Your move', {timeout: 10_000});
    await expect(page.getByTestId('puzzle-info')).toContainText('Puzzle rating');

    await page.getByTestId('puzzle-give-up').click();
    await expect(page.getByTestId('puzzle-outcome')).toContainText('Not this time');
    await expect(page.getByTestId('puzzle-solution')).toContainText('Solution:');
    await expect(page.getByTestId('puzzle-history')).toBeVisible();
    await page.screenshot({path: 'test-results/puzzles-solution.png'});

    await page.getByTestId('puzzle-next').click();
    await expect(page.getByTestId('puzzle-status')).toContainText('Your move', {timeout: 10_000});
    await expect(page.getByTestId('puzzle-profile')).toContainText('solved 1');
});

test('tactics: theme explanation, showing on the board and training at a stage', async ({page, request}) => {
    const username = `thm_${Date.now().toString(36)}`;
    expect((await request.post('/api/v1/auth/register', {data: {username, password: PASSWORD, accept_terms: true}})).ok()).toBe(true);
    // Login in the page context: the refresh cookie restores it on load (task 17.5).
    expect((await page.request.post('/api/v1/auth/login', {form: {username, password: PASSWORD}})).ok()).toBe(true);

    await page.goto('/puzzles');
    await page.getByTestId('puzzle-mode-themes').click();
    await page.getByTestId('training-theme-fork_knight').click();
    await expect(page.getByTestId('theme-card')).toContainText('Knight fork');
    await page.getByTestId('theme-demo').click();
    await page.getByTestId('demo-next').click();
    await expect(page.getByTestId('demo-caption')).toContainText('opponent');

    await page.getByTestId('theme-train').click();
    await expect(page.getByTestId('puzzle-info')).toContainText('stage 1');
    await expect(page.getByTestId('puzzle-status')).toContainText('Your move', {timeout: 10_000});
    await page.getByTestId('puzzle-give-up').click();
    await expect(page.getByTestId('training-progress')).toContainText('Stage 1: solved cleanly 0');
    await page.screenshot({path: 'test-results/puzzles-training.png'});
});
