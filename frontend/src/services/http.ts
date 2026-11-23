// --- FILE: frontend/src/services/http.ts ---
// Common request to the server API (/api/v1/...) for services/*.ts modules: address from config/api.ts (API_BASE_URL), login token
// from authToken.ts if the player is logged in (without login the request goes without it — open sections are served anyway), JSON body
// with a Content-Type header. A server refusal becomes a UiError with text by error code (apiErrors.ts, codes —
// src/core/errors.py); network unavailable — UiError "no connection". Components do not hit the network themselves: they call a service,
// and the service calls apiRequest (JSON response) or apiFetch (whole response: PGN text, headers) (project rule: a component
// renders, services/*.ts goes to the network).

import {API_BASE_URL} from '../config/api';
import {uiMessage} from '../i18n';
import type {MessageKey} from '../i18n';
import {readApiErrorOr, UiError} from './apiErrors';
import {getToken} from './authToken';
import {addBreadcrumb, CLIENT_ERRORS_PATH, newRequestId} from './breadcrumbs';

/** HTTP "no content" response: such a request returns undefined, it has no body. */
const NO_CONTENT = 204;

/** Fallback refusal text: a catalog key or a key by HTTP status (e.g. 429 from a proxy without a body). */
export type Fallback = MessageKey | ((status: number) => MessageKey);

/** Full address of an API path — for links (href of a PGN download etc.), not for requests from code. */
export const apiUrl = (path: string) => `${API_BASE_URL}/api/v1${path}`;

/**
 * Request to /api/v1{path}; the response is a checked Response (2xx status), the body is read by the caller: text, headers.
 * Headers from init extend the common ones (token and Content-Type), not replace them.
 */
export async function apiFetch(path: string, init: RequestInit = {}, fallback: Fallback = 'common.networkError'): Promise<Response> {
    const token = getToken();
    // End-to-end request number: the server writes it to every log line and returns it in X-Request-ID; it is also in the reports
    // of page errors (clientErrors.ts). Requests of the reports themselves are not traced.
    const requestId = newRequestId();
    const tracked = path !== CLIENT_ERRORS_PATH;
    const label = `${init.method ?? 'GET'} ${path.split('?')[0]}`;
    let res: Response;
    try {
        res = await fetch(apiUrl(path), {
            ...init,
            headers: {
                ...(typeof init.body === 'string' ? {'Content-Type': 'application/json'} : {}),
                ...(token ? {Authorization: `Bearer ${token}`} : {}),
                'X-Request-ID': requestId,
                ...(init.headers as Record<string, string> | undefined),
            },
        });
    } catch {
        if (tracked) addBreadcrumb('request', `${label} (no connection)`, {request_id: requestId});
        throw new UiError(uiMessage('common.noConnection'));
    }
    if (tracked) addBreadcrumb('request', label, {status: res.status, request_id: requestId});
    if (!res.ok) throw new UiError(await readApiErrorOr(res, typeof fallback === 'function' ? fallback(res.status) : fallback));
    return res;
}

/** Request to /api/v1{path}; the response is parsed JSON (204 — undefined). fallback — refusal text without a known code. */
export async function apiRequest<T>(path: string, init: RequestInit = {}, fallback: Fallback = 'common.networkError'): Promise<T> {
    const res = await apiFetch(path, init, fallback);
    if (res.status === NO_CONTENT) return undefined as T;
    return res.json() as Promise<T>;
}
