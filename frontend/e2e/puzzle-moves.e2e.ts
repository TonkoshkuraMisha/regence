// A move in a puzzle with a real mouse — by dragging and by two clicks (the puzzle of the day and a rated puzzle). Earlier
// the puzzle scenarios made no moves ("Show solution"), and a board where the piece did not move passed the test.

import {expect, test} from '@playwright/test';
import type {APIRequestContext, Page} from '@playwright/test';
import {Chess} from 'chess.js';
import {loginNewPlayer} from './helpers.ts';

async function login(page: Page, request: APIRequestContext, prefix: string) {
    await loginNewPlayer(page, request, prefix);
}

/** Any legal move of the solver — after the opponent's first move. */
function anyLegalMove(view: { fen: string; first_move: string }) {
    const game = new Chess(view.fen);
    game.move({from: view.first_move.slice(0, 2), to: view.first_move.slice(2, 4), promotion: view.first_move[4]});
    const move = game.moves({verbose: true}).find((m) => !m.promotion) ?? game.moves({verbose: true})[0];
    return {from: move.from, to: move.to};
}

async function square(page: Page, name: string) {
    const box = await page.locator(`[data-testid="puzzle-board"] [data-square="${name}"]`).boundingBox();
    if (!box) throw new Error(`no square ${name}`);
    return {x: box.x + box.width / 2, y: box.y + box.height / 2};
}

const answered = (page: Page) => page.locator('[data-testid="puzzle-mark-ok"], [data-testid="puzzle-mark-wrong"]');

test('puzzle of the day: a piece is dragged with the mouse, the server answers the move', async ({page, request}) => {
    await login(page, request, 'drag');
    await page.goto('/puzzles');
    const daily = page.waitForResponse((r) => r.url().includes('/api/v1/puzzles/daily'));
    await page.getByTestId('puzzle-mode-daily').click();
    const view = await (await daily).json();
    await expect(page.getByTestId('puzzle-status')).toContainText('Your move', {timeout: 10_000});

    const {from, to} = anyLegalMove(view);
    const start = await square(page, from);
    const end = await square(page, to);
    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    await page.mouse.move((start.x + end.x) / 2, (start.y + end.y) / 2, {steps: 5});
    await page.mouse.move(end.x, end.y, {steps: 5});
    await page.mouse.up();

    await expect(answered(page)).toBeVisible({timeout: 10_000});
    await page.screenshot({path: 'test-results/puzzle-drag.png'});
});

test('rated puzzle: a move by two clicks', async ({page, request}) => {
    await login(page, request, 'click');
    await page.goto('/puzzles');
    const next = page.waitForResponse((r) => r.url().includes('/api/v1/puzzles/next'));
    await page.getByTestId('puzzle-next').click();
    const view = await (await next).json();
    await expect(page.getByTestId('puzzle-status')).toContainText('Your move', {timeout: 10_000});

    const {from, to} = anyLegalMove(view);
    await page.locator(`[data-testid="puzzle-board"] [data-square="${from}"]`).click();
    await page.locator(`[data-testid="puzzle-board"] [data-square="${to}"]`).click();
    await expect(answered(page)).toBeVisible({timeout: 10_000});
});

test('tactics: a drag move in a training session on a theme', async ({page, request}) => {
    await login(page, request, 'thm');
    await page.goto('/puzzles');
    await page.getByTestId('puzzle-mode-themes').click();
    await page.getByTestId('training-theme-fork').click();
    const train = page.waitForResponse((r) => r.url().includes('/api/v1/puzzles/train'));
    await page.getByTestId('theme-train').click();
    const view = await (await train).json();
    await expect(page.getByTestId('puzzle-status')).toContainText('Your move', {timeout: 10_000});
    const {from, to} = anyLegalMove(view);
    await page.locator(`[data-testid="puzzle-board"] [data-square="${from}"]`)
        .dragTo(page.locator(`[data-testid="puzzle-board"] [data-square="${to}"]`));
    await expect(answered(page)).toBeVisible({timeout: 10_000});
    // The puzzle is chosen at random and the move is the first legal one: it may turn out to be the correct first move of a multi-move
    // puzzle, and then it continues without a result. In that case the puzzle is given up — the theme progress counts anyway.
    const progress = page.getByTestId('training-progress');
    const giveUp = page.getByTestId('puzzle-give-up');
    await expect(progress.or(giveUp).first()).toBeVisible();
    if (!(await progress.isVisible())) await giveUp.click();
    await expect(progress).toBeVisible();
});

test('a move by two hints is counted as correct', async ({page, request}) => {
    await login(page, request, 'hint');
    await page.goto('/puzzles');
    await page.getByTestId('puzzle-next').click();
    await expect(page.getByTestId('puzzle-status')).toContainText('Your move', {timeout: 10_000});
    const hint = page.waitForResponse((r) => r.url().includes('/hint'));
    await page.getByTestId('puzzle-hint').click();
    await hint;
    const second = page.waitForResponse((r) => r.url().includes('/hint'));
    await page.getByTestId('puzzle-hint').click();
    const {from, to} = await (await second).json();
    // The hint does not name the promotion — we move if it is a plain move, and pick the queen if asked.
    await page.locator(`[data-testid="puzzle-board"] [data-square="${from}"]`)
        .dragTo(page.locator(`[data-testid="puzzle-board"] [data-square="${to}"]`));
    const dialog = page.getByRole('dialog');
    if (await dialog.isVisible().catch(() => false)) await page.getByTestId('puzzle-promote-q').click();
    await expect(page.locator('[data-testid="puzzle-mark-ok"]')).toBeVisible({timeout: 10_000});
});

test('defence: "What is threatened?" — the threat, then the defence; "Don\'t blunder" — choosing a move', async ({page, request}) => {
    await login(page, request, 'def');
    await page.goto('/puzzles');
    await page.getByTestId('puzzle-mode-defense').click();
    const next = page.waitForResponse((r) => r.url().includes('/defense/next'));
    await page.getByTestId('defense-next').click();
    const drill = await (await next).json();
    await expect(page.getByTestId('defense-status')).toContainText('What would they play?');

    await page.locator(`[data-testid="puzzle-board"] [data-square="e4"]`).click();
    await expect(page.getByTestId('defense-threat-result')).toBeVisible();
    await expect(page.getByTestId('defense-status')).toContainText('Now defend');
    const game = new Chess(drill.fen);
    const move = game.moves({verbose: true}).find((m) => !m.promotion)!;
    await page.locator(`[data-testid="puzzle-board"] [data-square="${move.from}"]`)
        .dragTo(page.locator(`[data-testid="puzzle-board"] [data-square="${move.to}"]`));
    await expect(page.getByTestId('defense-outcome')).toBeVisible({timeout: 10_000});
    await expect(page.getByTestId('defense-progress')).toBeVisible();

    const blunder = page.waitForResponse((r) => r.url().includes('/defense/next'));
    await page.getByTestId('defense-kind-blunder').click();
    const choice = (await (await blunder).json()).choices[0];
    await page.getByTestId(`defense-choice-${choice}`).click();
    await expect(page.getByTestId('defense-outcome')).toBeVisible({timeout: 10_000});
    await page.screenshot({path: 'test-results/defense.png'});
});

test('generator exercises: "take the unprotected piece" by dragging and mate in 1 by clicks', async ({page, request}) => {
    await login(page, request, 'drl');
    await page.goto('/puzzles');
    await page.getByTestId('puzzle-mode-drills').click();

    const capture = page.waitForResponse((r) => r.url().includes('/drills/next'));
    await page.getByTestId('drill-next').click();
    const first = await (await capture).json();
    const game = new Chess(first.fen);
    const enemy = game.turn() === 'w' ? 'b' : 'w';
    const take = game.moves({verbose: true}).find((m) => m.captured && m.captured !== 'k'
        && !game.isAttacked(m.to, enemy))!;
    await page.locator(`[data-testid="puzzle-board"] [data-square="${take.from}"]`)
        .dragTo(page.locator(`[data-testid="puzzle-board"] [data-square="${take.to}"]`));
    await expect(page.getByTestId('drill-outcome')).toHaveText('Correct!', {timeout: 10_000});

    await page.getByTestId('drill-kind-mate1').click();
    const mate = page.waitForResponse((r) => r.url().includes('/drills/next'));
    await page.getByTestId('drill-next').click();
    const second = await (await mate).json();
    const board = new Chess(second.fen);
    const mating = board.moves({verbose: true}).find((m) => m.san.endsWith('#'))!;
    await page.locator(`[data-testid="puzzle-board"] [data-square="${mating.from}"]`).click();
    await page.locator(`[data-testid="puzzle-board"] [data-square="${mating.to}"]`).click();
    const dialog = page.getByRole('dialog');
    if (await dialog.isVisible().catch(() => false)) await page.getByTestId(`puzzle-promote-${mating.promotion ?? 'q'}`).click();
    await expect(page.getByTestId('drill-outcome')).toHaveText('Correct!', {timeout: 10_000});
    await page.screenshot({path: 'test-results/drills.png'});
});
