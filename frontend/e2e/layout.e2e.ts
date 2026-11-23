/// <reference lib="dom" />
// Layout on a phone and on a wide screen, in both languages (tasks 17.6 and 17.7): the page does not scroll sideways, text
// does not overflow the screen and is not clipped in buttons, links and blocks with hidden overflow. An intentional ellipsis
// (`text-overflow: ellipsis`) and blocks with their own horizontal scroll (tables) are not errors. On failure a page
// screenshot is attached to the report; E2E_LAYOUT_SHOTS=1 — screenshots of all pages (for the eyes).

import {expect, test} from '@playwright/test';
import type {Page, TestInfo} from '@playwright/test';
import {API, loginNewPlayer} from './helpers.ts';
import {languageState} from './languageState.ts';

const LANGUAGES = ['en', 'uk'] as const;
// Phones — from the narrowest common one (360 px) to a large one (430 px, task 24.2). Texts are longest on the
// narrow screen, so 360 runs in all languages; 430 in Ukrainian, to catch what breaks at the layout boundary.
const VIEWPORTS = [
    {name: 'phone', width: 360, height: 780, languages: LANGUAGES},
    {name: 'phone', width: 430, height: 932, languages: ['uk'] as const},
    {name: 'wide', width: 1600, height: 900, languages: LANGUAGES},
    // Tablet and laptop (17.11): pages between the phone and the wide screen used to go unchecked — that is how the header
    // ended up wider than the screen at 768–1366 px. One language: the layout matters here, not the text length.
    {name: 'tablet', width: 768, height: 1024, languages: ['uk'] as const},
    {name: 'laptop', width: 1366, height: 768, languages: ['uk'] as const},
];
// Pages without parameters and the sections that have their own first page.
const ROUTES = [
    '/', '/puzzles', '/learn', '/learn/basics', '/learn/classics', '/learn/endgames', '/learn/mates', '/train', '/tools',
    '/watch', '/guess', '/train/games', '/tournaments', '/arenas', '/conferences', '/teams', '/study', '/leaderboard', '/about', '/settings', '/moderation',
    '/learn/course', '/library', '/programs', '/exam', '/workout', '/repertoire', '/play/960', '/train/structure_quiz',
    '/import', '/transparency', '/time-machine', '/masters', 'PROFILE',
];

interface Problem {
    kind: 'page-scroll' | 'off-screen' | 'clipped';
    text: string;
    detail: string;
}

/** Layout problems on the open page (runs in the browser). */
async function findProblems(page: Page): Promise<Problem[]> {
    return page.evaluate(() => {
        const problems: { kind: 'page-scroll' | 'off-screen' | 'clipped'; text: string; detail: string }[] = [];
        const doc = document.documentElement;
        if (doc.scrollWidth > doc.clientWidth + 1) {
            problems.push({kind: 'page-scroll', text: '', detail: `${doc.scrollWidth} > ${doc.clientWidth}`});
        }
        const scrollsSideways = (el: Element | null): boolean => {
            for (let node = el; node && node !== document.body; node = node.parentElement) {
                const overflowX = getComputedStyle(node).overflowX;
                if ((overflowX === 'auto' || overflowX === 'scroll') && node.scrollWidth > node.clientWidth) return true;
            }
            return false;
        };
        const ownText = (el: Element) => Array.from(el.childNodes)
            .filter((n) => n.nodeType === Node.TEXT_NODE).map((n) => n.textContent ?? '').join('').trim();
        for (const el of Array.from(document.querySelectorAll('body *'))) {
            if (!(el instanceof HTMLElement)) continue;
            const text = ownText(el);
            if (!text) continue;
            const style = getComputedStyle(el);
            if (style.visibility === 'hidden' || style.display === 'none') continue;
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;
            if (style.position !== 'fixed' && (rect.right > window.innerWidth + 1 || rect.left < -1) && !scrollsSideways(el)) {
                problems.push({kind: 'off-screen', text: text.slice(0, 60), detail: `${Math.round(rect.left)}..${Math.round(rect.right)} / ${window.innerWidth}`});
                continue;
            }
            if (style.textOverflow === 'ellipsis') continue;
            const clips = style.overflowX === 'hidden' || style.overflowX === 'clip';
            const control = el.matches('button, a, label, [role="button"], th, td');
            if ((clips || control) && el.scrollWidth > el.clientWidth + 2 && !scrollsSideways(el)) {
                problems.push({kind: 'clipped', text: text.slice(0, 60), detail: `${el.tagName.toLowerCase()} ${el.scrollWidth} > ${el.clientWidth}`});
            }
        }
        return problems;
    });
}

async function check(page: Page, testInfo: TestInfo, label: string, route: string): Promise<string[]> {
    await page.goto(route);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(300);
    const problems = await findProblems(page);
    if (problems.length > 0 || process.env.E2E_LAYOUT_SHOTS === '1') {
        await testInfo.attach(`${label} ${route}`, {body: await page.screenshot({fullPage: true}), contentType: 'image/png'});
    }
    return problems.map((p) => `${label} ${route}: ${p.kind} «${p.text}» (${p.detail})`);
}

for (const language of LANGUAGES) {
    for (const viewport of VIEWPORTS.filter((v) => (v.languages as readonly string[]).includes(language))) {
        test(`layout: ${language}, ${viewport.name} ${viewport.width}px`, async ({page, request}, testInfo) => {
            test.setTimeout(240_000);
            await page.setViewportSize({width: viewport.width, height: viewport.height});
            const token = await loginNewPlayer(page, request, 'layout');
            // The language comes from the profile (task 17.7): otherwise on login it would override the browser language.
            await page.request.patch(`${API}/api/v1/profile/me/settings`, {
                data: {language}, headers: {Authorization: `Bearer ${token}`},
            });
            const me = await (await page.request.get(`${API}/api/v1/profile/me`, {headers: {Authorization: `Bearer ${token}`}})).json();
            const failures: string[] = [];
            try {
                for (const route of ROUTES) {
                    const path = route === 'PROFILE' ? `/profile/${encodeURIComponent(me.username)}` : route;
                    failures.push(...await check(page, testInfo, `${language} ${viewport.width}`, path));
                }
            } finally {
                // The player is shared by the run, and the other scenarios are written against the English interface — restore the language.
                await page.request.patch(`${API}/api/v1/profile/me/settings`, {
                    data: {language: 'en'}, headers: {Authorization: `Bearer ${token}`},
                });
            }
            expect(failures).toEqual([]);
        });
    }
}

// The guest header (not logged in): it has more buttons than a logged-in player's, and the site name appears only from
// a certain width — at that boundary the header once overflowed the screen (380–407 px). The main run is logged in and
// does not see this, so the guest is checked separately, at all phone widths.
test('layout: guest header on phones 360–480 px', async ({browser}, testInfo) => {
    const failures: string[] = [];
    for (const width of [360, 375, 380, 390, 400, 412, 420, 430, 440, 460, 480]) {
        const context = await browser.newContext({viewport: {width, height: 800}, locale: 'en-US', storageState: languageState('en')});
        const page = await context.newPage();
        for (const route of ['/about', '/time-machine']) {
            failures.push(...await check(page, testInfo, `guest ${width}`, route));
        }
        await context.close();
    }
    expect(failures).toEqual([]);
});

// The header on tablets and laptops (768–1440 px): nobody used to check it between the phone and the wide screen,
// and it did not fit — for a guest up to ~1200 px, for a logged-in player with a long name up to 1366 px (the login button and the profile
// menu went off the screen, the page scrolled sideways). Now at these widths the menu shows icons with tooltips,
// labels appear from 1360 px (for a logged-in player the longest one from 1500 px). The interface font is the system one: in
// the CI build (Linux) it is wider than on Windows, so the thresholds are tuned to the wide font, and this test is
// their real check. The guest and the logged-in player are checked separately: their headers have different contents.
// 640–720 px is the boundary where the name and the site name appear for a logged-in player.
const HEADER_WIDTHS = [640, 700, 720, 768, 820, 1024, 1180, 1280, 1340, 1360, 1366, 1440, 1500, 1536];

test('layout: guest header on tablets and laptops 640–1440 px', async ({browser}, testInfo) => {
    test.setTimeout(240_000);
    const failures: string[] = [];
    for (const [locale, language] of [['en-US', 'en'], ['uk-UA', 'uk']] as const) {
        for (const width of HEADER_WIDTHS) {
            const context = await browser.newContext({viewport: {width, height: 800}, locale, storageState: languageState(language)});
            const page = await context.newPage();
            failures.push(...await check(page, testInfo, `guest ${locale} ${width}`, '/about'));
            await context.close();
        }
    }
    expect(failures).toEqual([]);
});

test('layout: logged-in player header on tablets and laptops 640–1440 px', async ({page, request}, testInfo) => {
    test.setTimeout(240_000);
    const token = await loginNewPlayer(page, request, 'layout');
    const failures: string[] = [];
    try {
        for (const language of ['en', 'uk']) {
            await page.request.patch(`${API}/api/v1/profile/me/settings`, {
                data: {language}, headers: {Authorization: `Bearer ${token}`},
            });
            for (const width of HEADER_WIDTHS) {
                await page.setViewportSize({width, height: 800});
                failures.push(...await check(page, testInfo, `player ${language} ${width}`, '/about'));
            }
        }
    } finally {
        await page.request.patch(`${API}/api/v1/profile/me/settings`, {
            data: {language: 'en'}, headers: {Authorization: `Bearer ${token}`},
        });
    }
    expect(failures).toEqual([]);
});
