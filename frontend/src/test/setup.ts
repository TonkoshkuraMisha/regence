// --- FILE: frontend/src/test/setup.ts ---
// Shared environment setup for component tests (React Testing Library + jsdom).
// jsdom does not implement some of the APIs that Chessboard.tsx really uses — we put in
// minimal stubs once here, and not in every test file.

import '@testing-library/jest-dom/vitest';
import {afterEach, beforeEach} from 'vitest';
import {cleanup, configure} from '@testing-library/react';

// Expectations (findBy*, waitFor) give up after 1 s by default. When all test files run in parallel
// under coverage measurement — and the CI runner has fewer cores — heavy components (GameViewer with a
// recharts chart) occasionally did not manage to render, and the test failed with working code. A wait finishes at once
// as soon as the condition is met, so the extra time does not slow down green tests.
configure({asyncUtilTimeout: 5000});

import {setLanguage} from '../i18n';
import {clearToken} from '../services/authToken';
import {clearBotGameSnapshot} from '../services/botGameSnapshot';

// Component tests are written against the English interface: the language is set explicitly and is not taken from jsdom
// (which has en-US). Individual tests switch the language themselves — that is how Ukrainian is checked too.
beforeEach(() => {
    setLanguage('en', {persist: false});
});

afterEach(() => {
    cleanup();
    clearBotGameSnapshot();  // the bot game snapshot (also written on unmount) must not "continue" someone else's test
    clearToken();  // the login token lives in the module memory (task 17.5) — it is not carried over between tests
});

if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {
    };
}

// recharts (ResponsiveContainer) subscribes to ResizeObserver in an effect, which jsdom does not have. The stub is
// for the whole run, and not in a test's beforeEach: vi.unstubAllGlobals() in afterEach removed it, and the deferred effect of the
// chart, firing under load already on unmount, failed with "ResizeObserver is not defined".
if (!('ResizeObserver' in globalThis)) {
    class ResizeObserverStub {
        observe() {
        }

        unobserve() {
        }

        disconnect() {
        }
    }

    (globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver = ResizeObserverStub;
}

if (!document.elementsFromPoint) {
    document.elementsFromPoint = () => [];
}

if (!navigator.clipboard) {
    Object.defineProperty(navigator, 'clipboard', {
        value: {writeText: () => Promise.resolve()},
        configurable: true,
    });
}
