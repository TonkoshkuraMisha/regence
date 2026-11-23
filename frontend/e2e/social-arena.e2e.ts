// An end-to-end path in two real browsers (debt from the ToDo): a direct message reaches the other person, a feed post is visible
// to a follower and gets a "like", an arena game — "Play" for both, a pairing, moves, a resignation and the winner's points in the table.
//
// The players register through the API (the registration limit is raised on the CI stand) and log in through page.request — the same way as
// in helpers.loginPage. The arena is created by CI before the run (scripts/e2e_arena.py) and its number is passed in E2E_ARENA_ID;
// without it (a local run against dev servers) the arena scenario is skipped.

import {expect, test, type Browser, type Page} from '@playwright/test';
import {API, loginPage, PASSWORD} from './helpers.ts';

const ARENA_ID = process.env.E2E_ARENA_ID;

function uniqueName(prefix: string): string {
    return `${prefix}_${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`;
}

interface Player {
    name: string;
    page: Page;
    token: string;
}

async function newPlayer(browser: Browser, prefix: string): Promise<Player> {
    const name = uniqueName(prefix);
    const context = await browser.newContext();
    const page = await context.newPage();
    expect((await page.request.post(`${API}/api/v1/auth/register`, {data: {username: name, password: PASSWORD, accept_terms: true}})).ok()).toBe(true);
    const token = await loginPage(page, name);
    return {name, page, token};
}

const square = (page: Page, id: string) => page.locator(`[data-square="${id}"]`);
const pieceOn = (page: Page, id: string) => square(page, id).locator('img[alt]');

async function move(mover: Page, opponent: Page, from: string, to: string) {
    await square(mover, from).dragTo(square(mover, to));
    for (const page of [mover, opponent]) {
        await expect(pieceOn(page, to)).toHaveCount(1);
        await expect(pieceOn(page, from)).toHaveCount(0);
    }
}

test.describe.serial('communication and the arena in two browsers', () => {
    let alice: Player;
    let bob: Player;

    test.beforeAll(async ({browser}) => {
        alice = await newPlayer(browser, 'e2e_sa');
        bob = await newPlayer(browser, 'e2e_sb');
    });

    test.afterAll(async () => {
        await alice?.page.context().close();
        await bob?.page.context().close();
    });

    test('a direct message reaches the other person', async () => {
        const text = `Hello from e2e ${Date.now()}`;
        await alice.page.goto(`/messages/${bob.name}`);
        await alice.page.getByTestId('dm-input').fill(text);
        await alice.page.getByTestId('dm-send').click();
        await expect(alice.page.getByTestId('dm-messages')).toContainText(text);

        await bob.page.goto(`/messages/${alice.name}`);
        await expect(bob.page.getByTestId('dm-messages')).toContainText(text);
    });

    test('a feed post is visible to a follower and gets a "like"', async () => {
        const followed = await bob.page.request.post(`${API}/api/v1/social/follow/${alice.name}`,
            {headers: {Authorization: `Bearer ${bob.token}`}});
        expect(followed.ok()).toBe(true);

        const text = `Feed post e2e ${Date.now()}`;
        await alice.page.goto('/feed');
        await alice.page.getByTestId('feed-input').fill(text);
        await alice.page.getByTestId('feed-publish').click();
        await expect(alice.page.getByTestId('feed-post').filter({hasText: text})).toBeVisible();

        await bob.page.goto('/feed');
        const post = bob.page.getByTestId('feed-post').filter({hasText: text});
        await expect(post).toBeVisible();
        const like = post.getByTestId('feed-like');
        await like.click();
        await expect(like).toHaveAttribute('aria-pressed', 'true');
        await expect(like).toHaveText('1');
    });

    test('arena game: pairing, moves, resignation and the winner\'s points', async () => {
        test.skip(!ARENA_ID, 'the arena is created by CI (scripts/e2e_arena.py, E2E_ARENA_ID)');
        for (const player of [alice, bob]) {
            await player.page.goto(`/arenas/${ARENA_ID}`);
            await player.page.getByTestId('arena-join').click();
            await player.page.getByTestId('arena-play').click();
        }
        // The pairing is made — both pages move to the board with the game in progress on their own.
        for (const player of [alice, bob]) {
            await expect(player.page.getByTestId('pvp-game-status')).toBeVisible({timeout: 20_000});
        }
        // The colour is by board orientation: for White the first square in the markup is a8 (White at the bottom), for Black — h1.
        await expect(pieceOn(alice.page, 'e2')).toHaveCount(1);
        const aliceWhite = await alice.page.locator('[data-square]').first().getAttribute('data-square') === 'a8';
        const [white, black] = aliceWhite ? [alice, bob] : [bob, alice];
        await move(white.page, black.page, 'e2', 'e4');
        await move(black.page, white.page, 'e7', 'e5');

        white.page.once('dialog', (dialog) => void dialog.accept());
        await white.page.getByRole('button', {name: 'Resign'}).click();

        await black.page.goto(`/arenas/${ARENA_ID}`);
        const winnerRow = black.page.getByTestId('arena-standings').locator('tr', {hasText: black.name});
        // Points — a cell with a bold number: a win brings 2.
        await expect(winnerRow.locator('td.font-bold')).toHaveText('2');
    });
});
