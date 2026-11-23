// --- FILE: frontend/src/services/sentry.ts ---
// Sentry on the page (project regence-web): collecting unhandled errors and render errors with request tracing.
// Enabled only when VITE_SENTRY_DSN is set (at build time; for development — frontend/.env, for production —
// the build argument in frontend/Dockerfile): without it the module does nothing and makes no network calls.
//
// What is NOT enabled: Session Replay and personal data collection (off by default in @sentry/react 11) — recording the player's screen would contradict
// the "Privacy" summary (components/PrivacyPage.tsx). Our own investigation of "the page suddenly reloaded" —
// reports and the event trail in clientErrors.ts / breadcrumbs.ts (they go to our server log, not to Sentry).
// The X-Request-ID request number sent by http.ts is visible in the trace and links a Sentry event to the server log.

import * as Sentry from '@sentry/react';

/** Share of requests traced: in development — all, in production — one tenth (at first, later tuned to load). */
const TRACES_SAMPLE_RATE_PROD = 0.1;

/** Whether Sentry is enabled in this build (a DSN is set). */
export function sentryEnabled(dsn: string | undefined = import.meta.env.VITE_SENTRY_DSN): boolean {
    return Boolean(dsn);
}

/** Starts Sentry if a DSN is set; returns whether it started. Called once from main.tsx. */
export function initSentry(dsn: string | undefined = import.meta.env.VITE_SENTRY_DSN): boolean {
    if (!sentryEnabled(dsn)) return false;
    Sentry.init({
        dsn,
        environment: import.meta.env.MODE,
        tracesSampleRate: import.meta.env.PROD ? TRACES_SAMPLE_RATE_PROD : 1.0,
        integrations: [Sentry.browserTracingIntegration()],
    });
    return true;
}

/** Passes a caught render error to Sentry (page error boundary); without a DSN — does nothing. */
export function captureRenderError(error: Error, componentStack?: string | null): void {
    if (!sentryEnabled()) return;
    Sentry.captureException(error, {contexts: {react: {componentStack: componentStack ?? ''}}});
}
