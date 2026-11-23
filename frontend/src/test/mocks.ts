// --- FILE: frontend/src/test/mocks.ts ---
// Shared test doubles for the Chessboard component tests: gameSocket (we do not bring up a WS —
// we just record send() and let the test pull the registered handlers
// of events by hand) and a fetch router by URL prefix.

import {vi, type Mock} from 'vitest';

export function emitSocketEvent(onMock: Mock, event: string, data: any) {
    const call = onMock.mock.calls.find(([name]: [string]) => name === event);
    call?.[1]?.(data);
}

type FetchHandler = () => unknown;

/**
 * vi.fn() for global.fetch: compares the URL by includes() with the keys of handlers (the check order is
 * the declaration order) and returns {ok: true, json: () => handler()}. Unmatched requests are
 * {ok: false} (exactly what graceful degradation does in the component itself).
 */
export function mockFetchRouter(handlers: Record<string, FetchHandler>) {
    return vi.fn(async (input: string | URL | Request) => {
        const url = typeof input === 'string' ? input : input.toString();
        for (const [pattern, handler] of Object.entries(handlers)) {
            if (url.includes(pattern)) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => handler(),
                    text: async () => JSON.stringify(handler()),
                } as Response;
            }
        }
        return {ok: false, status: 404, json: async () => ({}), text: async () => ''} as Response;
    });
}
