// Личные сообщения, дополнительные пути: настройка «кто может писать» и чёрный список, скрытие и блокировка
// переписки, подгрузка ранних сообщений, отметка прочитанного, предупреждение фильтра («переписать» и
// «отправить на проверку»). Сеть — стаб fetch по адресу и методу.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {setToken} from '../../../services/authToken';
import {MessagesPage} from '../MessagesPage';

type Call = { url: string; method: string; body: unknown };
type Reply = unknown | Error;
type Handler = (call: Call) => Reply;

function stubFetch(handler: Handler) {
    const calls: Call[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
        const call = {url: String(url), method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : null};
        calls.push(call);
        const reply = handler(call);
        const failed = reply instanceof Error;
        return {
            ok: !failed, status: failed ? 422 : 200,
            json: async () => (failed ? {detail: {code: reply.message, params: {}, message: ''}} : reply),
        } as Response;
    }));
    return calls;
}

const msg = (id: number, mine: boolean, body: string, read = true) =>
    ({id, mine, body, attachment: null, created_at: '2026-11-17T10:00:00Z', read});
const thread = (messages: unknown[], extra: object = {}) =>
    ({username: 'magnus', avatar: null, can_write: true, reason: null, blocked: false, messages, ...extra});

function Where() {
    return <div data-testid="where">{useLocation().pathname}</div>;
}

function page(path: string) {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <Routes>
                <Route path="/messages" element={<MessagesPage/>}/>
                <Route path="/messages/:username" element={<MessagesPage/>}/>
            </Routes>
            <Where/>
        </MemoryRouter>,
    );
}

beforeEach(() => setToken('jwt'));
afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe('настройки личных сообщений', () => {
    it('смена политики уходит на сервер, чёрный список разблокируется', async () => {
        let settings = {dm_policy: 'all', blocked: ['troll']};
        const calls = stubFetch((c) => {
            if (c.url.endsWith('/settings') && c.method === 'PUT') {
                settings = {...settings, dm_policy: (c.body as { dm_policy: string }).dm_policy};
                return settings;
            }
            if (c.url.endsWith('/settings')) return settings;
            if (c.url.includes('/block/troll') && c.method === 'DELETE') {
                settings = {...settings, blocked: []};
                return settings;
            }
            return {unread: 0, conversations: []};
        });
        page('/messages');
        const select = await screen.findByTestId('dm-policy');
        await act(async () => fireEvent.change(select, {target: {value: 'nobody'}}));
        expect(calls.some((c) => c.method === 'PUT' && (c.body as { dm_policy: string }).dm_policy === 'nobody')).toBe(true);
        expect(screen.getByTestId('dm-policy')).toHaveValue('nobody');

        await act(async () => fireEvent.click(screen.getByRole('button', {name: 'Разблокировать'})));
        expect(calls.some((c) => c.method === 'DELETE' && c.url.includes('/block/troll'))).toBe(true);
        await waitFor(() => expect(screen.getByText(/никого|Никого|нет/i)).toBeInTheDocument());
    });
});

describe('переписка: действия', () => {
    const base = (extra?: Handler): Handler => (c) => {
        const own = extra?.(c);
        if (own !== undefined) return own;
        if (c.url.endsWith('/settings')) return {dm_policy: 'all', blocked: []};
        if (c.url.includes('/with/magnus/read')) return {unread: 0};
        if (c.url.includes('/with/magnus')) return thread([msg(1, false, 'Привет!', false)]);
        return {unread: 0, conversations: []};
    };

    it('непрочитанное сообщение собеседника отмечается прочитанным', async () => {
        const calls = stubFetch(base());
        page('/messages/magnus');
        await screen.findByTestId('dm-theirs');
        await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/with/magnus/read'))).toBe(true));
    });

    it('«Скрыть переписку» отправляет запрос и возвращает к списку', async () => {
        const calls = stubFetch(base((c) => (c.url.endsWith('/hide') ? {unread: 0} : undefined)));
        page('/messages/magnus');
        await screen.findByTestId('dm-theirs');
        await act(async () => fireEvent.click(screen.getByTestId('dm-hide')));
        expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/with/magnus/hide'))).toBe(true);
        await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent(/^\/messages$/));
    });

    it('блокировка спрашивает подтверждение; отказ ничего не отправляет, согласие блокирует', async () => {
        const calls = stubFetch(base((c) => (c.url.includes('/block/magnus') ? {dm_policy: 'all', blocked: ['magnus']} : undefined)));
        const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
        page('/messages/magnus');
        await screen.findByTestId('dm-theirs');
        await act(async () => fireEvent.click(screen.getByTestId('dm-block')));
        expect(calls.some((c) => c.url.includes('/block/magnus'))).toBe(false);
        await act(async () => fireEvent.click(screen.getByTestId('dm-block')));
        expect(confirm).toHaveBeenCalledTimes(2);
        expect(calls.some((c) => c.method === 'POST' && c.url.includes('/block/magnus'))).toBe(true);
    });

    it('у заблокированного собеседника кнопка снимает блокировку без вопроса', async () => {
        const calls = stubFetch((c) => {
            if (c.url.includes('/block/magnus')) return {dm_policy: 'all', blocked: []};
            if (c.url.endsWith('/settings')) return {dm_policy: 'all', blocked: ['magnus']};
            if (c.url.includes('/with/magnus')) return thread([msg(1, false, 'Привет!')], {blocked: true});
            return {unread: 0, conversations: []};
        });
        const confirm = vi.spyOn(window, 'confirm');
        page('/messages/magnus');
        await screen.findByTestId('dm-theirs');
        await act(async () => fireEvent.click(screen.getByTestId('dm-block')));
        expect(confirm).not.toHaveBeenCalled();
        expect(calls.some((c) => c.method === 'DELETE' && c.url.includes('/block/magnus'))).toBe(true);
    });

    it('полная страница ранних сообщений — кнопка «Предыдущие» подгружает более старые', async () => {
        const recent = Array.from({length: 50}, (_, i) => msg(100 + i, i % 2 === 0, `новое ${i}`));
        const calls = stubFetch((c) => {
            if (c.url.endsWith('/settings')) return {dm_policy: 'all', blocked: []};
            if (c.url.includes('before_id=100')) return thread([msg(90, false, 'старое')]);
            if (c.url.includes('/with/magnus')) return thread(recent);
            return {unread: 0, conversations: []};
        });
        page('/messages/magnus');
        fireEvent.click(await screen.findByRole('button', {name: 'Предыдущие сообщения'}));
        expect(await screen.findByText('старое')).toBeInTheDocument();
        expect(calls.some((c) => c.url.includes('before_id=100'))).toBe(true);
        // Страница неполная — подгружать больше нечего.
        expect(screen.queryByRole('button', {name: 'Предыдущие сообщения'})).toBeNull();
    });
});

describe('предупреждение фильтра', () => {
    function flaggedHandler(sent: Call[]): Handler {
        return (c) => {
            if (c.url.endsWith('/settings')) return {dm_policy: 'all', blocked: []};
            if (c.url.includes('/with/magnus') && c.method === 'POST') {
                sent.push(c);
                return (c.body as { send_anyway: boolean }).send_anyway
                    ? {...msg(7, true, 'резкий текст'), held: true}
                    : new Error('text_flagged');
            }
            if (c.url.includes('/with/magnus')) return thread([]);
            return {unread: 0, conversations: []};
        };
    }

    it('«переформулировать» закрывает предупреждение, текст остаётся', async () => {
        stubFetch(flaggedHandler([]));
        page('/messages/magnus');
        fireEvent.change(await screen.findByTestId('dm-input'), {target: {value: 'резкий текст'}});
        await act(async () => fireEvent.click(screen.getByTestId('dm-send')));
        fireEvent.click(await screen.findByTestId('flagged-rephrase'));
        expect(screen.queryByTestId('flagged-notice')).toBeNull();
        expect(screen.getByTestId('dm-input')).toHaveValue('резкий текст');
    });

    it('«отправить на проверку» повторяет отправку с send_anyway, сообщение помечено как придержанное', async () => {
        const sent: Call[] = [];
        stubFetch(flaggedHandler(sent));
        page('/messages/magnus');
        fireEvent.change(await screen.findByTestId('dm-input'), {target: {value: 'резкий текст'}});
        await act(async () => fireEvent.click(screen.getByTestId('dm-send')));
        await act(async () => fireEvent.click(await screen.findByTestId('flagged-send-anyway')));
        expect(sent.map((c) => (c.body as { send_anyway: boolean }).send_anyway)).toEqual([false, true]);
        expect(await screen.findByTestId('held-note')).toBeInTheDocument();
        expect(screen.queryByTestId('flagged-notice')).toBeNull();
    });
});
