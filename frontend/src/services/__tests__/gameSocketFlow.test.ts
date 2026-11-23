// The WebSocket connection (gameSocket.ts), branches beyond gameSocketTicket.test.ts: subscriptions and event broadcast ('*'),
// the message queue before connecting, sending to an open socket, reconnecting after a drop and after a 429/500
// on ticket issue, no reconnect on a normal close (1000), a JSON parsing failure.

import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {gameSocket} from '../gameSocket';
import {clearToken, setToken} from '../authToken';

class FakeWebSocket {
    static OPEN = 1;
    static CONNECTING = 0;
    static instances: FakeWebSocket[] = [];
    readyState = FakeWebSocket.CONNECTING;
    onopen: (() => void) | null = null;
    onmessage: ((e: {data: string}) => void) | null = null;
    onclose: ((e: {code: number}) => void) | null = null;
    onerror: ((e: unknown) => void) | null = null;
    sent: string[] = [];

    constructor(public url: string) {
        FakeWebSocket.instances.push(this);
    }

    send(msg: string) {
        this.sent.push(msg);
    }

    close() {
    }

    open() {
        this.readyState = FakeWebSocket.OPEN;
        this.onopen?.();
    }
}

const ticketOk = () => ({ok: true, status: 200, json: async () => ({ticket: 't'})});
const flush = async () => {
    await vi.advanceTimersByTimeAsync(0);
};

describe('gameSocket: events, the queue and reconnecting', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        FakeWebSocket.instances = [];
        setToken('jwt');
        vi.stubGlobal('WebSocket', FakeWebSocket);
        vi.spyOn(console, 'warn').mockImplementation(() => undefined);
        vi.spyOn(console, 'error').mockImplementation(() => undefined);
    });

    afterEach(() => {
        gameSocket.disconnect();
        vi.useRealTimers();
        vi.restoreAllMocks();
        vi.unstubAllGlobals();
    });

    it('a message goes to subscribers by event name and to the "*" subscriber; after off — it does not arrive', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ticketOk()));
        const named = vi.fn();
        const all = vi.fn();
        gameSocket.on('move_made', named);
        gameSocket.on('*', all);
        gameSocket.connect('jwt');
        await flush();
        const ws = FakeWebSocket.instances[0];
        ws.open();
        ws.onmessage?.({data: JSON.stringify({event: 'move_made', san: 'e4'})});
        ws.onmessage?.({data: JSON.stringify({event: 'clock_update'})});
        expect(named).toHaveBeenCalledTimes(1);
        expect(all).toHaveBeenCalledTimes(2);
        gameSocket.off('move_made', named);
        gameSocket.off('*', all);
        gameSocket.off('unknown_event', named);
        ws.onmessage?.({data: JSON.stringify({event: 'move_made'})});
        expect(named).toHaveBeenCalledTimes(1);
    });

    it('invalid JSON does not break receiving and is written to the console', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ticketOk()));
        gameSocket.connect('jwt');
        await flush();
        const ws = FakeWebSocket.instances[0];
        ws.open();
        ws.onmessage?.({data: '{not json'});
        ws.onerror?.(new Event('error'));
        expect(console.error).toHaveBeenCalled();
    });

    it('messages without a connection wait in the queue and go out after opening; into an open socket — at once', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ticketOk()));
        gameSocket.connect('jwt');
        gameSocket.send('join_queue', {base: 3});
        await flush();
        const ws = FakeWebSocket.instances[0];
        expect(ws.sent).toEqual([]);
        ws.open();
        expect(ws.sent).toEqual([JSON.stringify({action: 'join_queue', base: 3})]);
        gameSocket.send('leave_queue');
        expect(ws.sent).toHaveLength(2);
    });

    it('a repeated connect on an open or connecting socket does not open a second one', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ticketOk()));
        gameSocket.connect('jwt');
        gameSocket.connect('jwt');  // the ticket request is in progress
        await flush();
        gameSocket.connect('jwt');  // the socket is in the CONNECTING state
        gameSocket.connect('');     // an empty token is ignored
        expect(FakeWebSocket.instances).toHaveLength(1);
    });

    it('without login send sends nothing and writes an error', () => {
        clearToken();
        gameSocket.send('ping');
        expect(console.error).toHaveBeenCalled();
        expect(FakeWebSocket.instances).toHaveLength(0);
    });

    it('a connection drop: reconnecting after 1.5 s; a normal close 1000 — without it', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ticketOk()));
        gameSocket.connect('jwt');
        await flush();
        FakeWebSocket.instances[0].onclose?.({code: 1006});
        await vi.advanceTimersByTimeAsync(1500);
        expect(FakeWebSocket.instances).toHaveLength(2);
        FakeWebSocket.instances[1].onclose?.({code: 1000});
        await vi.advanceTimersByTimeAsync(5000);
        expect(FakeWebSocket.instances).toHaveLength(2);
    });

    it('a 429 on ticket issue — a retry after 15 s, another failure — after 1.5 s', async () => {
        const fetchMock = vi.fn()
            .mockResolvedValueOnce({ok: false, status: 429})
            .mockResolvedValueOnce({ok: false, status: 500})
            .mockResolvedValue(ticketOk());
        vi.stubGlobal('fetch', fetchMock);
        gameSocket.connect('jwt');
        await flush();
        expect(fetchMock).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(1500);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(13500);
        expect(fetchMock).toHaveBeenCalledTimes(2);
        await vi.advanceTimersByTimeAsync(1500);
        expect(fetchMock).toHaveBeenCalledTimes(3);
        expect(FakeWebSocket.instances).toHaveLength(1);
    });

    it('a new connect cancels the scheduled reconnect', async () => {
        const fetchMock = vi.fn().mockResolvedValue(ticketOk());
        vi.stubGlobal('fetch', fetchMock);
        gameSocket.connect('jwt');
        await flush();
        FakeWebSocket.instances[0].onclose?.({code: 1006});
        gameSocket.connect('jwt');
        await flush();
        expect(FakeWebSocket.instances).toHaveLength(2);
        await vi.advanceTimersByTimeAsync(3000);
        expect(FakeWebSocket.instances).toHaveLength(2);
    });
});
