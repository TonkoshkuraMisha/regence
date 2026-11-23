// --- FILE: frontend/src/services/__tests__/clientErrors.test.ts ---
// Page error reports and the event trail (breadcrumbs.ts, clientErrors.ts, the request id in http.ts): breadcrumbs
// survive a reload (sessionStorage), a request carries X-Request-ID, a report goes to /client-errors with the trail, without
// repeats and beyond the limit, and the report's own requests do not get into the trail.

import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {addBreadcrumb, clearBreadcrumbs, getBreadcrumbs, newRequestId} from '../breadcrumbs';
import {reportClientError, resetClientErrorsForTests} from '../clientErrors';
import {apiRequest} from '../http';

function stubFetch(status = 200) {
    const fetchMock = vi.fn(async () => ({ok: status < 400, status, json: async () => ({}), headers: new Headers()}) as Response);
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

beforeEach(() => {
    sessionStorage.clear();
    clearBreadcrumbs();
    resetClientErrorsForTests();
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('breadcrumbs', () => {
    it('keeps no more than the last 30 events and saves them in sessionStorage', () => {
        for (let i = 0; i < 35; i += 1) addBreadcrumb('route', `/page${i}`);
        const crumbs = getBreadcrumbs();
        expect(crumbs).toHaveLength(30);
        expect(crumbs[0].name).toBe('/page5');
        expect(JSON.parse(sessionStorage.getItem('regence_breadcrumbs') ?? '[]')).toHaveLength(30);
    });

    it('the request id — 16 safe characters (fits the server rule)', () => {
        expect(newRequestId()).toMatch(/^[a-z0-9]{16}$/);
        expect(newRequestId()).not.toBe(newRequestId());
    });
});

describe('the request id in http.ts', () => {
    it('every request carries X-Request-ID and leaves a breadcrumb with the method, the path without parameters and the status', async () => {
        const fetchMock = stubFetch();
        await apiRequest('/tournaments/2?full=1');
        const init = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        const headers = init[1].headers as Record<string, string>;
        expect(headers['X-Request-ID']).toMatch(/^[a-z0-9]{16}$/);
        expect(getBreadcrumbs()).toEqual([expect.objectContaining({
            kind: 'request', name: 'GET /tournaments/2', status: 200, request_id: headers['X-Request-ID'],
        })]);
    });

    it('a network failure also leaves a trail', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline'); }));
        await expect(apiRequest('/profile/me')).rejects.toBeTruthy();
        expect(getBreadcrumbs()[0].name).toBe('GET /profile/me (no connection)');
    });
});

describe('reportClientError', () => {
    it('sends a report to /client-errors with the trail, and does not write its own request into the trail', async () => {
        addBreadcrumb('socket', 'event move_made');
        const fetchMock = stubFetch(204);
        expect(await reportClientError('error', 'boom', 'stack-line')).toBe(true);
        const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(url).toMatch(/\/api\/v1\/client-errors$/);
        const body = JSON.parse(String(init.body));
        expect(body).toMatchObject({kind: 'error', message: 'boom', stack: 'stack-line'});
        expect(body.breadcrumbs).toEqual([expect.objectContaining({name: 'event move_made'})]);
        expect(getBreadcrumbs()).toHaveLength(1);
    });

    it('does not repeat the same message and does not send more than ten reports', async () => {
        const fetchMock = stubFetch(204);
        await reportClientError('error', 'same');
        expect(await reportClientError('error', 'same')).toBe(false);
        for (let i = 0; i < 12; i += 1) await reportClientError('error', `m${i}`);
        expect(fetchMock).toHaveBeenCalledTimes(10);
    });

    it('a report sending failure does not throw an exception', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline'); }));
        await expect(reportClientError('render', 'x')).resolves.toBe(false);
    });
});

describe('installClientErrorReporting', () => {
    it('writes a page visit into the breadcrumbs, and window error and unhandledrejection go out as reports', async () => {
        const {installClientErrorReporting} = await import('../clientErrors');
        const fetchMock = stubFetch(204);
        installClientErrorReporting();
        expect(getBreadcrumbs().some((c) => c.kind === 'route')).toBe(true);

        window.dispatchEvent(new ErrorEvent('error', {message: 'oops', error: new Error('oops')}));
        const rejection = new Event('unhandledrejection') as Event & {reason: unknown};
        rejection.reason = new Error('rejected');
        window.dispatchEvent(rejection);
        const plain = new Event('unhandledrejection') as Event & {reason: unknown};
        plain.reason = 'a string';
        window.dispatchEvent(plain);
        await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
        const kinds = fetchMock.mock.calls.map((c) => JSON.parse(String((c as unknown as [string, RequestInit])[1].body)).kind);
        expect(kinds).toEqual(['error', 'unhandledrejection', 'unhandledrejection']);
    });

    it('after a page refresh with a non-empty trail a reload report goes out', async () => {
        const {installClientErrorReporting} = await import('../clientErrors');
        addBreadcrumb('route', '/before');
        vi.spyOn(performance, 'getEntriesByType').mockReturnValue([{type: 'reload'}] as unknown as PerformanceEntryList);
        const fetchMock = stubFetch(204);
        installClientErrorReporting();
        await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
        expect(JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body)).kind).toBe('reload');
        vi.restoreAllMocks();
    });
});
