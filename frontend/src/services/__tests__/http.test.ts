// --- FILE: frontend/src/services/__tests__/http.test.ts ---
// The shared API request (services/http.ts): the /api/v1 address, the login token and Content-Type for a JSON body, a 204 reply without a body,
// a server refusal — a UiError with the error code, no network — a "no connection" UiError.

import {afterEach, describe, expect, it, vi} from 'vitest';
import {UiError} from '../apiErrors';
import {setToken} from '../authToken';
import {apiRequest} from '../http';
import type {MessageKey} from '../../i18n';

function stubFetch(response: Partial<Response> | Error) {
    const fetchMock = vi.fn(async () => {
        if (response instanceof Error) throw response;
        return {ok: true, status: 200, json: async () => ({}), ...response} as Response;
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
});

describe('apiRequest', () => {
    it('the /api/v1 address, the login token and a JSON body with a header', async () => {
        setToken('jwt');
        const fetchMock = stubFetch({json: async () => ({id: 7})});
        const result = await apiRequest<{ id: number }>('/feed/posts', {method: 'POST', body: JSON.stringify({body: 'hi'})});
        expect(result).toEqual({id: 7});
        const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(url).toMatch(/\/api\/v1\/feed\/posts$/);
        expect(init.method).toBe('POST');
        expect(init.headers).toEqual({'Content-Type': 'application/json', Authorization: 'Bearer jwt', 'X-Request-ID': expect.stringMatching(/^[a-z0-9]{16}$/)});
    });

    it('without login and without a body — no headers; own headers complement the shared ones', async () => {
        const fetchMock = stubFetch({});
        await apiRequest('/watch/archive');
        await apiRequest('/watch/archive', {headers: {'X-Test': '1'}});
        expect((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].headers).toEqual({'X-Request-ID': expect.any(String)});
        expect((fetchMock.mock.calls[1] as unknown as [string, RequestInit])[1].headers).toEqual({'X-Request-ID': expect.any(String), 'X-Test': '1'});
    });

    it('204 — without a body', async () => {
        stubFetch({status: 204, json: async () => {
            throw new Error('no body');
        }});
        await expect(apiRequest('/imports/1', {method: 'DELETE'})).resolves.toBeUndefined();
    });

    it('the fallback text can depend on the status: 429 without a body — "too many attempts"', async () => {
        stubFetch({ok: false, status: 429, json: async () => {
            throw new Error('not json');
        }});
        const fallback = (status: number): MessageKey => (status === 429 ? 'auth.tooManyAttempts' : 'auth.wrongCredentials');
        const refused = await apiRequest('/auth/login', {method: 'POST'}, fallback).catch((err: unknown) => err);
        expect((refused as UiError).ui).toEqual(expect.objectContaining({key: 'auth.tooManyAttempts'}));
    });

    it('a server refusal — a UiError with a code; no network — "no connection"', async () => {
        stubFetch({ok: false, status: 404, json: async () => ({detail: {code: 'puzzle_not_found', message: 'Puzzle not found'}})});
        const refused = await apiRequest('/feed/posts/1').catch((err: unknown) => err);
        expect(refused).toBeInstanceOf(UiError);
        expect((refused as UiError).ui).toEqual(expect.objectContaining({key: 'serverErrors.puzzle_not_found'}));

        stubFetch(new TypeError('Failed to fetch'));
        const offline = await apiRequest('/feed/posts/1').catch((err: unknown) => err);
        expect((offline as UiError).ui).toEqual(expect.objectContaining({key: 'common.noConnection'}));
    });
});
