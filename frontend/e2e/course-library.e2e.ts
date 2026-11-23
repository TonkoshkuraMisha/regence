// The big course, the library and the new trainers in a real browser against the full stack (tasks 27.5–27.12), as a guest —
// without registration (its per-IP limit is used up by other scenarios). The library database in the stack is empty: "Guess the structure"
// answers with training skeletons, "Miniatures" with an empty set.

import {expect, test} from '@playwright/test';

test('Big course: levels, branches, skeleton and jump to a section', async ({page}) => {
    await page.goto('/learn');
    await page.getByTestId('learn-course-link').click();
    await expect(page.getByTestId('supercourse-page')).toBeVisible();
    await expect(page.getByTestId('course-module-T0.0')).toContainText('Board, pieces and captures');
    await page.getByTestId('course-level-3').click();
    await expect(page.getByTestId('course-module-S3.5')).toContainText('The “saw”');
    // All modules are filled in (27.6): the former empty T3.2 is visible even without "skeleton" mode; the mode itself is checked by a unit test.
    await expect(page.getByTestId('course-module-T3.2')).toContainText('Winning a square');
    // The structure module (27.11): first a lesson on plans, then library games with this structure.
    await page.getByTestId('course-module-S3.5').getByRole('button').first().click();
    await expect(page).toHaveURL(/\/learn\/structure-saw/);
    await expect(page.getByTestId('lesson-player')).toBeVisible();
    await page.goBack();
    await page.getByTestId('course-level-3').click();
    await page.getByTestId('course-module-S3.5').getByRole('button').nth(1).click();
    await expect(page).toHaveURL(/\/library\?structure=saw/);
    await expect(page.getByTestId('library-structure')).toHaveValue('saw');
});

test('"Guess the structure": ten questions with skeletons, the result', async ({page}) => {
    await page.goto('/train/structure_quiz');
    await page.getByTestId('trainer-start').click();
    await expect(page.getByTestId('structure-quiz')).toBeVisible();
    for (let i = 0; i < 10; i++) {
        await page.locator('[data-testid^="quiz-option-"]').first().click();
        await page.getByTestId('quiz-next').click();
    }
    await expect(page.getByTestId('trainer-result')).toBeVisible();
});

test('endgames: must-know positions and studies on the trainer page', async ({page}) => {
    await page.goto('/learn/endgames');
    await expect(page.getByTestId('must-know-1')).toContainText('Stage 1');
    await expect(page.getByTestId('endgame-study_saavedra')).toBeVisible();
    await page.getByTestId('endgame-vancura').click();
    await expect(page.locator('[data-square="a8"]').first()).toBeVisible();
});
