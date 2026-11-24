// The full path of a PvP game in two real browsers: registration and login, a challenge by link,
// drag moves synchronised to the opponent, a mate, the result for both, a rematch with swapped colours.
//
// The players register once for the whole file: registration is limited to 5 accounts per hour per IP.

import {expect, test, type Browser, type Page} from '@playwright/test';
import {openNewGame} from './helpers.ts';

const PASSWORD = 'e2e-pass-12345';

function uniqueName(prefix: string): string {
    // 3–30 characters: Latin letters, digits, _ (the registration rules).
    return `${prefix}_${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`;
}

async function newPlayer(browser: Browser, username: string): Promise<Page> {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto('/');

    await page.getByRole('button', {name: 'Log in'}).click();
    await page.getByRole('button', {name: 'No account? Sign up'}).click();
    await page.getByPlaceholder('e.g. string1').fill(username);
    await page.getByPlaceholder('••••••••').fill(PASSWORD);
    await page.getByTestId('auth-age-adult').check();  // the age: 16 or older (task 23.1)
    await page.getByTestId('auth-terms').check();  // consent to the rules and privacy (task 23.1)
    await page.getByRole('button', {name: 'Sign up'}).click();

    // After registration the player is already logged in (task 17.8): a welcome with an offer of the first game — "Later".
    const welcome = page.getByRole('dialog', {name: `Welcome, ${username}!`});
    await welcome.getByRole('button', {name: 'Later'}).click();
    await expect(welcome).toHaveCount(0);
    await expect(page.getByText(username).first()).toBeVisible();
    return page;
}

const square = (page: Page, id: string) => page.locator(`[data-square="${id}"]`);
// The piece is <img alt="wp"> with pointer-events: none: we drag by the square, and check presence by the img.
const pieceOn = (page: Page, id: string) => square(page, id).locator('img[alt]');

async function move(mover: Page, opponent: Page, from: string, to: string) {
    await square(mover, from).dragTo(square(mover, to));
    for (const page of [mover, opponent]) {
        await expect(pieceOn(page, to)).toHaveCount(1);
        await expect(pieceOn(page, from)).toHaveCount(0);
    }
}

async function resign(page: Page) {
    // Resignation is confirmed by a system dialog; Playwright dismisses it by default.
    page.once('dialog', (dialog) => {
        expect(dialog.message()).toBe('Do you really want to resign?');
        void dialog.accept();
    });
    await page.getByRole('button', {name: 'Resign'}).click();
}

async function startFriendGame(creator: Page, acceptor: Page, color: 'white' | 'black') {
    await creator.goto('/');
    await acceptor.goto('/');
    await openNewGame(creator, 'human');
    await creator.getByRole('button', {name: 'With a friend'}).click();
    await creator.getByRole('button', {name: color === 'white' ? '♔ White' : '♚ Black'}).click();
    await creator.getByRole('button', {name: 'Generate and copy the link'}).click();
    const link = await creator.locator('input[readonly][value*="/challenge/"]').inputValue();
    expect(link).toMatch(/\/challenge\/[A-Za-z0-9]+$/);

    await acceptor.goto(new URL(link).pathname);
    for (const page of [creator, acceptor]) {
        await expect(page.getByText('Rated game in progress')).toBeVisible();
    }
    await expect(creator.getByText(`You play ${color === 'white' ? 'White' : 'Black'}`)).toBeVisible();
    await expect(acceptor.getByText(`You play ${color === 'white' ? 'Black' : 'White'}`)).toBeVisible();
}

test.describe.serial('PvP in two browsers', () => {
    let alice: Page;
    let bob: Page;
    let aliceName: string;
    let bobName: string;
    let carol: Page | undefined;

    test.beforeAll(async ({browser}) => {
        aliceName = uniqueName('e2e_a');
        bobName = uniqueName('e2e_b');
        alice = await newPlayer(browser, aliceName);
        bob = await newPlayer(browser, bobName);
    });

    test.afterAll(async () => {
        await alice?.context().close();
        await bob?.context().close();
        await carol?.context().close();
    });

    test('a challenge by link, a mate, the result for both and a rematch with a colour swap', async () => {
        await startFriendGame(alice, bob, 'white');

        // "Fool's mate": 1. f3 e5 2. g4 Qh4#
        await move(alice, bob, 'f2', 'f3');
        await move(bob, alice, 'e7', 'e5');
        await move(alice, bob, 'g2', 'g4');
        await move(bob, alice, 'd8', 'h4');

        for (const page of [alice, bob]) {
            await expect(page.getByText('Game over (0-1)')).toBeVisible();
        }

        // Rematch: the colours swap, a new game for both.
        await alice.getByRole('button', {name: 'Rematch', exact: true}).click();
        await expect(bob.getByText('Your opponent offers a rematch (colors switched)!')).toBeVisible();
        await bob.getByRole('button', {name: 'Accept rematch'}).click();

        for (const page of [alice, bob]) {
            await expect(page.getByText('Rated game in progress')).toBeVisible();
        }
        await expect(bob.getByText('You play White')).toBeVisible();
        await move(bob, alice, 'e2', 'e4');
        await move(alice, bob, 'e7', 'e5');

        // We finish the rematch by resigning (before the 2nd half-move "Abort the game" is shown instead), so that
        // the next scenario starts without an active game.
        await resign(alice);
        for (const page of [alice, bob]) {
            await expect(page.getByText('Game over (1-0)')).toBeVisible();
        }
    });

    test('an illegal move is rejected and does not change the opponent\'s position', async () => {
        await startFriendGame(alice, bob, 'white');

        // A rook through its own pawn — the board does not change for anyone.
        await square(alice, 'a1').dragTo(square(alice, 'a4'));
        for (const page of [alice, bob]) {
            await expect(pieceOn(page, 'a1')).toHaveCount(1);
            await expect(pieceOn(page, 'a4')).toHaveCount(0);
        }

        await move(alice, bob, 'e2', 'e4');
        await move(bob, alice, 'e7', 'e5');
        await resign(alice);
        await expect(bob.getByText('Game over (0-1)')).toBeVisible();
    });

    test('a spectator sees the game from the Live list, cannot interfere and gets its result', async ({browser}) => {
        // The third player registers only here (registration is limited by the number of accounts per IP)
        // and before the game starts: the players have 30 seconds for the first move, otherwise the game is cancelled.
        carol = await newPlayer(browser, uniqueName('e2e_c'));
        const spectator = carol;

        await startFriendGame(alice, bob, 'white');
        await move(alice, bob, 'e2', 'e4');
        await move(bob, alice, 'e7', 'e5');

        await spectator.getByRole('button', {name: /Playing now \(Live\)/}).click();
        // The game row is the innermost block that has both the player names and the button.
        const watchButton = spectator.getByRole('button', {name: 'Watch'});
        const liveGame = spectator.locator('div')
            .filter({hasText: `${aliceName} vs ${bobName}`})
            .filter({has: watchButton})
            .last();
        await liveGame.getByRole('button', {name: 'Watch'}).click();

        // The spectator gets the position with the moves already made and sees the following ones.
        await expect(spectator.getByText(`Spectator mode: ${aliceName} vs ${bobName}`)).toBeVisible();
        await expect(pieceOn(spectator, 'e4')).toHaveCount(1);
        await expect(pieceOn(spectator, 'e5')).toHaveCount(1);
        await move(alice, bob, 'g1', 'f3');
        await expect(pieceOn(spectator, 'f3')).toHaveCount(1);
        await expect(pieceOn(spectator, 'g1')).toHaveCount(0);

        // Interfering is impossible: neither by a move nor by a chat message.
        await expect(spectator.getByText('Spectators can only read the chat.')).toBeVisible();
        await expect(spectator.getByPlaceholder('Write a message…')).toHaveCount(0);
        await square(spectator, 'd2').dragTo(square(spectator, 'd4'));
        for (const page of [spectator, alice, bob]) {
            await expect(pieceOn(page, 'd2')).toHaveCount(1);
            await expect(pieceOn(page, 'd4')).toHaveCount(0);
        }

        await resign(alice);
        await expect(spectator.getByText('Game over. Result: 0-1 (resignation)')).toBeVisible();

        await spectator.getByRole('button', {name: 'Stop watching'}).click();
        await expect(spectator.getByText('Free board / Analysis')).toBeVisible();
    });
});
