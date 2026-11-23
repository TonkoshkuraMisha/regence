// The mentor in game review on a real Stockfish: a game with a scholar's mate, the review, comments on the mating
// move and on the blunder before it, arrows on the board.

import {expect, test} from '@playwright/test';

const PASSWORD = 'e2e-pass-12345';

test('game review: the mentor explains the blunder and the mate', async ({page, request}) => {
    const username = `coach_${Date.now().toString(36)}`;
    expect((await request.post('/api/v1/auth/register', {data: {username, password: PASSWORD, accept_terms: true}})).ok()).toBe(true);
    const login = await request.post('/api/v1/auth/login', {form: {username, password: PASSWORD}});
    const {access_token: token} = await login.json();

    // 1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6?? 4. Qxf7# — the player with White against Morphy.
    const saved = await request.post('/api/v1/bots/save-game', {
        headers: {Authorization: `Bearer ${token}`},
        data: {
            bot_id: 'morphy', player_color: 'white', result: '1-0',
            moves_uci: ['e2e4', 'e7e5', 'f1c4', 'b8c6', 'd1h5', 'g8f6', 'h5f7'],
            base_time_ms: 300000, increment_ms: 0,
        },
    });
    expect(saved.ok()).toBe(true);
    const {game_id: gameId} = await saved.json();

    await page.goto(`/game/${gameId}`);
    // The saved game is reviewed by the Celery worker right away: if it was faster than the page opening, the review is already
    // shown and there is no "Computer analysis" button (the test failed that way in CI, where the worker is free). Otherwise, start it.
    const analyze = page.getByRole('button', {name: 'Computer analysis'});
    const coach = page.getByTestId('coach-comment');
    await expect(analyze.or(coach).first()).toBeVisible({timeout: 30_000});
    if (await analyze.isVisible()) await analyze.click();

    await expect(coach).toContainText('checkmate', {timeout: 60_000});  // the mating move: "♕xf7# — checkmate!"

    await page.getByTitle('Move back').click();  // 3... Nf6?? — misses the mate
    await expect(coach).toContainText('♞f6');
    await expect(coach).toContainText('♕xf7#');
    await expect(page.getByTestId('coach-arrow-threat')).toHaveCount(1);
    await page.screenshot({path: 'test-results/coach-blunder.png'});
});
