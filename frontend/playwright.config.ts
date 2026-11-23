// E2E tests (Playwright) against the built production stack: nginx + API + PostgreSQL + Redis.
//
//   docker compose -f docker-compose.prod.yml up -d --build   (HTTP_PORT=8080)
//   npx playwright install chromium                            (once)
//   E2E_BASE_URL=http://localhost:8080 npm run test:e2e
//
// Each run registers two new players, and registration is limited to 5 accounts per hour
// from one IP: for frequent local runs restart the stack's Redis (the limits are stored there).

import {defineConfig, devices} from '@playwright/test';
import {languageState} from './e2e/languageState.ts';

export default defineConfig({
    testDir: './e2e',
    testMatch: '**/*.e2e.ts',
    timeout: 90_000,
    expect: {timeout: 15_000},
    fullyParallel: false,
    workers: 1,
    retries: process.env.CI ? 1 : 0,
    reporter: process.env.CI ? [['list'], ['html', {open: 'never'}]] : 'list',
    use: {
        baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8080',
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        viewport: {width: 1400, height: 900},
        // The scenarios are written against the English interface (the site's default language; it does not guess the
        // browser language, owner's decision 22.11), so the language is chosen in advance, as a player does in the header.
        locale: 'en-US',
        storageState: languageState('en'),
        permissions: ['clipboard-read', 'clipboard-write'],
    },
    projects: [{name: 'chromium', use: {...devices['Desktop Chrome'], viewport: {width: 1400, height: 900}}}],
});
