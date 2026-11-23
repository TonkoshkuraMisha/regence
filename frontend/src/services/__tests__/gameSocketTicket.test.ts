// --- FILE: frontend/src/services/__tests__/gameSocketTicket.test.ts ---

import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {gameSocket} from '../gameSocket';
import {getToken, setToken} from '../authToken';

class FakeWebSocket {
    static OPEN = 1;
    static CONNECTING = 0;
    static instances: FakeWebSocket[] = [];
    readyState = FakeWebSocket.CONNECTING;
    onopen: (() => void) | null = null;
    onmessage: ((e: {data: string}) => void) | null = null;
    onclose: ((e: {code: number}) => void) | null = null;
    onerror: ((e: unknown) => void) | null = null;

    constructor(public url: string) {
        FakeWebSocket.instances.push(this);
    }

    send() {
    }

    close() {
    }
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('gameSocket: connecting by a one-time ticket', () => {
    let events: string[];

    beforeEach(() => {
        FakeWebSocket.instances = [];
        setToken('jwt.secret.token');  // the login token is in memory (task 17.5)
        events = [];
        vi.stubGlobal('WebSocket', FakeWebSocket);
        vi.stubGlobal('window', {dispatchEvent: (e: Event) => events.push(e.type)});
    });

    afterEach(() => {
        gameSocket.disconnect();
        vi.unstubAllGlobals();
    });

    it('puts a ticket into the WebSocket address, not the JWT', async () => {
        const fetchMock = vi.fn().mockResolvedValue({ok: true, status: 200, json: async () => ({ticket: 'one-time'})});
        vi.stubGlobal('fetch', fetchMock);

        gameSocket.connect('jwt.secret.token');
        await flush();

        expect(fetchMock).toHaveBeenCalledOnce();
        const [, init] = fetchMock.mock.calls[0];
        expect(init.headers.Authorization).toBe('Bearer jwt.secret.token');
        expect(FakeWebSocket.instances).toHaveLength(1);
        expect(FakeWebSocket.instances[0].url).toContain('ticket=one-time');
        expect(FakeWebSocket.instances[0].url).not.toContain('jwt.secret.token');
    });

    it('on 401 for the ticket request logs out and does not connect', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: false, status: 401}));

        gameSocket.connect('jwt.secret.token');
        await flush();

        expect(FakeWebSocket.instances).toHaveLength(0);
        expect(getToken()).toBeNull();
        expect(events).toContain('regence-auth-expired');
    });

    it('a close with code 1008 (session revoked) logs out', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: true, status: 200, json: async () => ({ticket: 't'})}));

        gameSocket.connect('jwt.secret.token');
        await flush();
        FakeWebSocket.instances[0].onclose?.({code: 1008});

        expect(getToken()).toBeNull();
        expect(events).toContain('regence-auth-expired');
    });

    it('does not open a socket if they disconnected while waiting for the ticket', async () => {
        let resolveFetch: (v: unknown) => void = () => {
        };
        vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise((r) => (resolveFetch = r))));

        gameSocket.connect('jwt.secret.token');
        gameSocket.disconnect();
        resolveFetch({ok: true, status: 200, json: async () => ({ticket: 'late'})});
        await flush();

        expect(FakeWebSocket.instances).toHaveLength(0);
    });

    it('closing the old socket after a token change does not touch the new connection', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: true, status: 200, json: async () => ({ticket: 't'})}));

        gameSocket.connect('jwt.secret.token');
        await flush();
        gameSocket.connect('another.user.token');
        await flush();
        expect(FakeWebSocket.instances).toHaveLength(2);
        const [oldSocket, newSocket] = FakeWebSocket.instances;
        newSocket.readyState = FakeWebSocket.OPEN;
        const sendSpy = vi.spyOn(newSocket, 'send');

        // The close event of the old socket arrives late — including with code 1008.
        oldSocket.onclose?.({code: 1008});

        expect(events).not.toContain('regence-auth-expired');
        gameSocket.send('leave_queue');
        expect(sendSpy).toHaveBeenCalledOnce();           // went to the current socket,
        expect(FakeWebSocket.instances).toHaveLength(2);  // and did not open a third connection
    });
});
