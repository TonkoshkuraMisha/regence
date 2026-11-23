// New sections in a real browser against the full stack (task A.5): a tournament with a real simulation worker, a school
// lesson, the opponent workshop and the club ladder. Unit-level tests call the simulation directly — here it is played by the
// Celery worker of the simulation queue, and the player's game is accepted by the server.

import {expect, test} from '@playwright/test';
import type {APIRequestContext, Page} from '@playwright/test';
import {API, loginNewPlayer, openNewGame} from './helpers.ts';

/** The player is shared by the run: resign a tournament left over from the previous attempt to be able to create a new one. */
async function withdrawActiveTournaments(request: APIRequestContext, token: string) {
    const headers = {Authorization: `Bearer ${token}`};
    const list = await (await request.get(`${API}/api/v1/tournaments`, {headers})).json() as { id: number; status: string }[];
    for (const t of list.filter((item) => item.status === 'active')) {
        await request.post(`${API}/api/v1/tournaments/${t.id}/withdraw`, {headers});
    }
}

async function resign(page: Page) {
    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', {name: /Resign/}).click();
}

test('tournament: bot games are played by the worker, the own game is recorded in the tournament', async ({page, request}) => {
    test.setTimeout(240_000);
    const token = await loginNewPlayer(page, request, 'tour');
    await withdrawActiveTournaments(request, token);

    await page.goto('/tournaments');
    for (const bot of ['Morphy', 'Philidor', 'Staunton']) {
        await page.getByRole('button', {name: new RegExp(`^${bot}`)}).click();
    }
    await page.getByRole('button', {name: 'Create tournament'}).click();
    await expect(page.getByTestId('tournament-view')).toBeVisible();
    await expect(page.getByTestId('crosstable')).toBeVisible();

    // The first-round bot games are finished by the simulation worker; the page refreshes by itself.
    await expect.poll(async () => page.locator('[data-testid^="tgame-"]').filter({hasText: /1-0|0-1|1\/2-1\/2/}).count(),
        {timeout: 150_000, intervals: [2_000]}).toBeGreaterThan(0);

    await page.getByRole('button', {name: 'Play my game'}).click();
    // During the game — the tournament bar (round, opponent, table above the board), after it — the way back to the tournament.
    await expect(page.getByTestId('tournament-bar')).toBeVisible();
    await resign(page);
    await expect(page.getByText(/The result is recorded in the tournament/)).toBeVisible();
    const back = page.getByTestId('back-to-tournament');
    await expect(back).toBeVisible();
    await expect(page.getByRole('button', {name: /Rematch/})).toHaveCount(0);
    await back.click();

    // The round is closed by the player's game: in the table the player has a loss, the round is the second one.
    await expect(page.getByTestId('tournament-status')).toContainText('Round 2 of 3', {timeout: 30_000});
    await expect(page.getByRole('link', {name: 'Game'}).first()).toBeVisible();
});

test('school lesson: steps, a wrong move with feedback, a correct move and the opponent reply', async ({page, request}) => {
    await loginNewPlayer(page, request, 'learn');
    await page.goto('/learn/tactics-double-attack');
    await expect(page.getByTestId('lesson-counter')).toContainText('Step 1 of 6');
    await page.getByRole('button', {name: 'Next'}).click();
    await page.getByRole('button', {name: 'Next'}).click();  // the demonstration can be skipped

    await expect(page.getByTestId('lesson-counter')).toContainText('Step 3 of 6');
    const cell = (sq: string) => page.locator(`[data-square="${sq}"]`).first();
    await cell('d5').click();
    await cell('f6').click();
    await expect(page.getByTestId('lesson-feedback')).toContainText('the g7 pawn simply takes the knight');
    await cell('d5').click();
    await cell('e7').click();
    await expect(page.getByTestId('lesson-feedback')).toContainText('Check and an attack on the queen');
    await expect(page.getByText('Now continue the line.')).toBeVisible();
});

test('workshop: the opponent is saved in the profile and plays the first move', async ({page, request}) => {
    await loginNewPlayer(page, request, 'shop');
    await page.goto('/');
    await openNewGame(page, 'bot');
    await page.getByRole('tab', {name: 'Workshop'}).click();
    await page.getByRole('button', {name: /^Centralist/}).click();
    await page.getByPlaceholder(/Gambit/).fill(`E2E${Date.now().toString(36).slice(-4)}`);
    await page.getByRole('button', {name: /Save opponent/}).click();
    await expect(page.getByText('Saved to your profile')).toBeVisible();

    await page.getByTestId('personality-workshop').getByRole('button', {name: /Black/}).click();
    // The opponent moves first through /bots/custom-move: any first White move frees one of the 16 squares of the first two
    // ranks (earlier we waited for a c/d/e pawn move or a g1 knight move — a weak opponent with its own opening may differ).
    const homeSquares = [...'abcdefgh'].flatMap((file) => [`${file}1`, `${file}2`]).map((sq) => `[data-square="${sq}"] img`).join(', ');
    await expect.poll(async () => page.locator(homeSquares).count(), {timeout: 30_000}).toBeLessThan(16);
});

test('ladder: a game against an opponent chosen by the server, the result in the status', async ({page, request}) => {
    await loginNewPlayer(page, request, 'ladder');
    await page.goto('/');
    await openNewGame(page, 'bot');
    await page.getByRole('tab', {name: 'Ladder'}).click();
    await page.getByTestId('ladder-panel').getByRole('button', {name: /White/}).click();
    await expect(page.getByRole('button', {name: /Take back/})).toBeDisabled();
    await resign(page);
    await expect(page.getByText(/Ladder: rating/)).toBeVisible({timeout: 20_000});
});
