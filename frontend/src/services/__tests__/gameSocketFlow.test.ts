// Соединение WebSocket (gameSocket.ts), ветки сверх gameSocketTicket.test.ts: подписки и рассылка событий ('*'),
// очередь сообщений до подключения, отправка в открытый сокет, повторное подключение после обрыва и после отказа
// 429/500 на выдаче тикета, отсутствие переподключения при штатном закрытии (1000), сбой разбора JSON.

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

describe('gameSocket: события, очередь и переподключение', () => {
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

    it('сообщение уходит подписчикам по имени события и подписчику на "*"; после off — не приходит', async () => {
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

    it('некорректный JSON не роняет приём и пишется в консоль', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ticketOk()));
        gameSocket.connect('jwt');
        await flush();
        const ws = FakeWebSocket.instances[0];
        ws.open();
        ws.onmessage?.({data: '{не json'});
        ws.onerror?.(new Event('error'));
        expect(console.error).toHaveBeenCalled();
    });

    it('сообщения без связи ждут в очереди и уходят после открытия; в открытый сокет — сразу', async () => {
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

    it('повторный connect при открытом или подключающемся сокете не открывает второй', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ticketOk()));
        gameSocket.connect('jwt');
        gameSocket.connect('jwt');  // идёт запрос тикета
        await flush();
        gameSocket.connect('jwt');  // сокет в состоянии CONNECTING
        gameSocket.connect('');     // пустой токен игнорируется
        expect(FakeWebSocket.instances).toHaveLength(1);
    });

    it('без входа send ничего не отправляет и пишет ошибку', () => {
        clearToken();
        gameSocket.send('ping');
        expect(console.error).toHaveBeenCalled();
        expect(FakeWebSocket.instances).toHaveLength(0);
    });

    it('обрыв соединения: повторное подключение через 1,5 с; штатное закрытие 1000 — без него', async () => {
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

    it('отказ 429 на выдаче тикета — повтор через 15 с, прочий сбой — через 1,5 с', async () => {
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

    it('новое connect отменяет запланированное переподключение', async () => {
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
