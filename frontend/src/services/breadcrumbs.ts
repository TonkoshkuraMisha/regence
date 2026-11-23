// --- FILE: frontend/src/services/breadcrumbs.ts ---
// «Breadcrumbs» — a trail of the page's latest events: API requests (with an X-Request-ID number, by which the whole chain is found
// in the server log), WebSocket messages and closes, page changes. Stored in sessionStorage, so it SURVIVES
// a page reload: the report of the new page (clientErrors.ts) carries what happened before the reload. The module has no
// network dependencies — it is written by http.ts and gameSocket.ts and read by clientErrors.ts (so there is no circular dependency).
// Request bodies, tokens and personal data do not get into the breadcrumbs — only the method, the path without parameters, the status and the request number.

export type CrumbKind = 'request' | 'socket' | 'route' | 'reload';

export interface Breadcrumb {
    t: number;
    kind: CrumbKind;
    name: string;
    status?: number;
    request_id?: string;
}

/** Path of the report request: its own requests are not written to the breadcrumbs (otherwise the report would describe itself). */
export const CLIENT_ERRORS_PATH = '/client-errors';

const STORAGE_KEY = 'regence_breadcrumbs';
// This many breadcrumbs are accepted by the server (MAX_BREADCRUMBS in src/api/client_errors.py) and kept by the page.
const MAX_CRUMBS = 30;
const MAX_NAME = 120;

let crumbs: Breadcrumb[] = loadCrumbs();

function loadCrumbs(): Breadcrumb[] {
    try {
        const raw = sessionStorage.getItem(STORAGE_KEY);
        const parsed: unknown = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? (parsed as Breadcrumb[]).slice(-MAX_CRUMBS) : [];
    } catch {
        return [];
    }
}

function saveCrumbs() {
    try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(crumbs));
    } catch {
        // Storage unavailable (private mode, full) — the breadcrumbs stay only in memory.
    }
}

/** Appends an event to the trail; old ones are pushed out. */
export function addBreadcrumb(kind: CrumbKind, name: string, extra: {status?: number; request_id?: string} = {}) {
    crumbs = [...crumbs, {t: Date.now(), kind, name: name.slice(0, MAX_NAME), ...extra}].slice(-MAX_CRUMBS);
    saveCrumbs();
}

/** Copy of the trail (for reports and tests). */
export function getBreadcrumbs(): Breadcrumb[] {
    return [...crumbs];
}

/** Clearing the trail — tests only. */
export function clearBreadcrumbs() {
    crumbs = [];
    saveCrumbs();
}

/** New request number: 16 characters [0-9a-f] — fits the server's REQUEST_ID_PATTERN. */
export function newRequestId(): string {
    const uuid = typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
    return uuid.replace(/-/g, '').slice(0, 16);
}
