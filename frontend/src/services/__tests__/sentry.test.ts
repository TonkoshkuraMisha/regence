// --- FILE: frontend/src/services/__tests__/sentry.test.ts ---
// Sentry on the page (services/sentry.ts): without a DSN nothing starts and nothing goes to the network; with a DSN — initialization without
// personal data and without screen recording; a render error goes to Sentry only when the DSN is enabled.

import {beforeEach, describe, expect, it, vi} from 'vitest';

const init = vi.fn();
const captureException = vi.fn();
vi.mock('@sentry/react', () => ({
    init: (options: unknown) => init(options),
    captureException: (...args: unknown[]) => captureException(...args),
    browserTracingIntegration: () => ({name: 'tracing'}),
}));

import {captureRenderError, initSentry, sentryEnabled} from '../sentry';

beforeEach(() => {
    init.mockClear();
    captureException.mockClear();
    vi.unstubAllEnvs();
    vi.stubEnv('VITE_SENTRY_DSN', '');  // we do not depend on the DSN in the developer's frontend/.env
});

describe('initSentry', () => {
    it('without a DSN does not start Sentry', () => {
        expect(sentryEnabled('')).toBe(false);
        expect(initSentry('')).toBe(false);
        expect(init).not.toHaveBeenCalled();
    });

    it('with a DSN starts without personal data and without screen recording', () => {
        expect(initSentry('https://key@o1.ingest.de.sentry.io/2')).toBe(true);
        const options = init.mock.calls[0][0] as Record<string, unknown>;
        expect(options).toMatchObject({dsn: 'https://key@o1.ingest.de.sentry.io/2'});
        expect(options).not.toHaveProperty('sendDefaultPii', true);
        expect(JSON.stringify(Object.keys(options))).not.toMatch(/replay/i);
        expect(options.tracesSampleRate).toBe(1.0); // not production in tests
    });
});

describe('captureRenderError', () => {
    it('without a DSN sends nothing', () => {
        captureRenderError(new Error('x'), 'stack');
        expect(captureException).not.toHaveBeenCalled();
    });

    it('with a DSN sends an error with the component stack', () => {
        vi.stubEnv('VITE_SENTRY_DSN', 'https://key@o1.ingest.de.sentry.io/2');
        const error = new Error('render failed');
        captureRenderError(error, 'in Page');
        expect(captureException).toHaveBeenCalledWith(error, {contexts: {react: {componentStack: 'in Page'}}});
    });
});
