// --- FILE: frontend/src/services/apiErrors.ts ---
// Server errors → messages in the player's language. The server returns a code, parameters and an English text
// (src/core/errors.py); the player-facing text is taken from the serverErrors catalog by code. The server's English text
// is shown only if the client does not know the code yet (for example, a stale tab).

import {hasMessage, uiMessage} from '../i18n';
import type {MessageKey, MessageParam, UiMessage} from '../i18n';

type Params = Record<string, MessageParam>;

function primitiveParams(raw: unknown): Params {
    const params: Params = {};
    if (raw && typeof raw === 'object') {
        for (const [name, value] of Object.entries(raw as Record<string, unknown>)) {
            if (typeof value === 'string' || typeof value === 'number') params[name] = value;
            else if (typeof value === 'boolean') params[name] = String(value);
        }
    }
    return params;
}

/** Error by server code: from the catalog, and if the code is unknown — the server's English text. */
export function serverErrorMessage(code: unknown, params?: unknown, message?: unknown): UiMessage | null {
    const key = `serverErrors.${String(code)}`;
    if (typeof code === 'string' && hasMessage(key)) return uiMessage(key, primitiveParams(params));
    return typeof message === 'string' && message ? {text: message} : null;
}

/** Field validation error (422): the server's own check — by code, the standard one — by type from the validation catalog. */
function validationItemMessage(item: unknown): UiMessage | null {
    if (!item || typeof item !== 'object') return null;
    // The server's English msg is not shown: the check type and its parameters are translated by the catalog.
    const {type, loc, params} = item as { type?: unknown; loc?: unknown; params?: unknown };
    const fromCode = serverErrorMessage(type, params);
    let message: UiMessage | null = fromCode;
    if (!message) {
        const key = `validation.${String(type)}`;
        message = hasMessage(key)
            ? uiMessage(key as MessageKey, primitiveParams(params))
            : uiMessage('validation.invalid_value');
    }
    const field = Array.isArray(loc) ? loc.filter((part) => typeof part === 'string').at(-1) : undefined;
    // The request body root («body») is not a field; a whole-model check gets no field label.
    if (typeof field === 'string' && field !== 'body') {
        const fieldKey = `fields.${field}`;
        return uiMessage('validation.withField', {
            field: hasMessage(fieldKey) ? uiMessage(fieldKey) : field,
            message,
        });
    }
    return message;
}

/** API response detail → message; null — the response has nothing suitable to show. */
export function apiErrorMessage(detail: unknown): UiMessage | null {
    if (Array.isArray(detail)) return detail.length ? validationItemMessage(detail[0]) : null;
    if (detail && typeof detail === 'object') {
        const {code, params, message} = detail as { code?: unknown; params?: unknown; message?: unknown };
        return serverErrorMessage(code, params, message);
    }
    // Responses without a code: standard FastAPI and proxy errors («Not Found», «Method Not Allowed»).
    return typeof detail === 'string' && detail ? {text: detail} : null;
}

/** Error from a response (the body is read once); null — there is no body or no error in it. */
export async function readApiError(res: Response): Promise<UiMessage | null> {
    try {
        const data = await res.json();
        return apiErrorMessage(data?.detail);
    } catch {
        return null;
    }
}

/** Error from a response or the catalog's fallback message. */
export async function readApiErrorOr(res: Response, fallback: MessageKey): Promise<UiMessage> {
    return (await readApiError(res)) ?? uiMessage(fallback);
}

/** Exception with a message to show: services throw it, components show ui in the player's language. */
export class UiError extends Error {
    readonly ui: UiMessage;

    constructor(ui: UiMessage) {
        super('text' in ui ? ui.text : ui.key);
        this.name = 'UiError';
        this.ui = ui;
    }
}

/** Message from a caught exception: UiError — as is, otherwise (network, code error) — the fallback. */
export function errorMessage(err: unknown, fallback: MessageKey): UiMessage {
    return err instanceof UiError ? err.ui : uiMessage(fallback);
}
