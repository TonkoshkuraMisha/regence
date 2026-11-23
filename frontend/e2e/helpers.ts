// Shared steps of the E2E scenarios.

import {expect} from '@playwright/test';
import type {APIRequestContext, Page} from '@playwright/test';

export const PASSWORD = 'e2e-pass-12345';
// On the production stack the API is at the same address (nginx); against dev servers (Vite + uvicorn) it has its own address: E2E_API_URL.
export const API = process.env.E2E_API_URL ?? '';

/**
 * A player for a scenario: registration and login before the page loads. Login goes through page.request: it shares the cookie with
 * the page's browser context, and the refresh cookie (task 17.5) restores the session on load. Registration
 * is limited to 5 accounts per hour from one address, so the scenarios of one run (one worker) share a single player.
 * Returns the access token — for API requests from the scenario itself.
 */
const players = new Map<string, string>();

export async function loginPage(page: Page, username: string): Promise<string> {
    const response = await page.request.post(`${API}/api/v1/auth/login`, {form: {username, password: PASSWORD}});
    expect(response.ok()).toBe(true);
    return (await response.json()).access_token as string;
}

export async function loginNewPlayer(page: Page, request: APIRequestContext, prefix: string): Promise<string> {
    let username = process.env.E2E_SHARED_PLAYER === '0' ? undefined : players.get('shared');
    if (!username) {
        username = `${prefix}_${Date.now().toString(36)}`;
        expect((await request.post(`${API}/api/v1/auth/register`, {data: {username, password: PASSWORD, accept_terms: true}})).ok()).toBe(true);
        players.set('shared', username);
    }
    return loginPage(page, username);
}

/**
 * The "New game" dialog of the game hall (owner's scheme 18.11) at the "Start" step: the opponent is a person or a bot, the time
 * control is whichever is selected. From the first step, so as not to depend on the choice remembered by the previous game.
 */
export async function openNewGame(page: Page, who: 'human' | 'bot'): Promise<void> {
    await page.getByTestId('new-game-open').click();
    await page.getByTestId('new-game-step-who').click();
    await page.getByTestId(`new-game-who-${who}`).click();
    await page.getByTestId('new-game-next').click();
    await expect(page.getByTestId(`new-game-start-${who}`)).toBeVisible();
}
