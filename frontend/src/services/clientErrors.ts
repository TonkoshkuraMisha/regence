// --- FILE: frontend/src/services/clientErrors.ts ---
// Page error reports to the server (POST /api/v1/client-errors, src/api/client_errors.py). Each report
// carries a trail of the latest events — «breadcrumbs» (breadcrumbs.ts: requests with an X-Request-ID number, WebSocket messages and
// closes, page changes). The breadcrumbs SURVIVE a page reload: if the page suddenly reloaded
// (crash, build update, error), the very first report of the new page (kind «reload») carries what happened before it.
//
// What is sent: the failure kind, a short message, the stack, the page address and breadcrumbs — without request bodies, tokens or personal data.
// No more than MAX_REPORTS reports per page load and without repeats of the same message. The server silently drops reports
// above its limit. Installation — installClientErrorReporting() in main.tsx; network — only through http.ts.

import {addBreadcrumb, CLIENT_ERRORS_PATH, getBreadcrumbs} from './breadcrumbs';
import {apiFetch} from './http';

/** Report kind — matches ClientErrorIn.kind on the server. */
export type ReportKind = 'render' | 'error' | 'unhandledrejection' | 'socket' | 'reload';
const MAX_REPORTS = 10;
const MAX_MESSAGE = 500;
const MAX_STACK = 4000;
const MAX_URL = 300;

let reportsSent = 0;
const reportedMessages = new Set<string>();

/** Reset of the report counters — tests only. */
export function resetClientErrorsForTests() {
    reportsSent = 0;
    reportedMessages.clear();
}

/** Sends a report (does not throw: a report failure must not cause a new failure). Returns whether it went out. */
export async function reportClientError(kind: ReportKind, message: string, stack?: string): Promise<boolean> {
    const text = (message || 'unknown error').slice(0, MAX_MESSAGE);
    const key = `${kind}:${text}`;
    if (reportsSent >= MAX_REPORTS || reportedMessages.has(key)) return false;
    reportedMessages.add(key);
    reportsSent += 1;
    try {
        await apiFetch(CLIENT_ERRORS_PATH, {
            method: 'POST',
            body: JSON.stringify({
                kind,
                message: text,
                ...(stack ? {stack: stack.slice(0, MAX_STACK)} : {}),
                url: `${window.location.pathname}${window.location.search}`.slice(0, MAX_URL),
                breadcrumbs: getBreadcrumbs(),
            }),
        });
        return true;
    } catch {
        return false;
    }
}

/** Navigation type: 'reload' — refresh, 'navigate' — ordinary visit, 'back_forward', etc. */
function navigationType(): string {
    const entry = typeof performance !== 'undefined' && performance.getEntriesByType
        ? performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
        : undefined;
    return entry?.type ?? 'navigate';
}

/**
 * Enables collection: window error and unhandledrejection, writing the page opening into the breadcrumbs and, if the page was refreshed
 * (reload), a «reload» report with the trail from before the refresh. Called once from main.tsx.
 */
export function installClientErrorReporting() {
    const type = navigationType();
    const previous = getBreadcrumbs();
    addBreadcrumb('route', `${window.location.pathname} (${type})`);
    if (type === 'reload' && previous.length > 0) {
        addBreadcrumb('reload', 'page reloaded');
        void reportClientError('reload', 'page reloaded');
    }
    window.addEventListener('error', (event) => {
        void reportClientError('error', event.message || String(event.error), event.error instanceof Error ? event.error.stack : undefined);
    });
    window.addEventListener('unhandledrejection', (event) => {
        const reason: unknown = event.reason;
        void reportClientError('unhandledrejection', reason instanceof Error ? reason.message : String(reason),
            reason instanceof Error ? reason.stack : undefined);
    });
}
