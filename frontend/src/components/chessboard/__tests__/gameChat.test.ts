// --- FILE: frontend/src/components/chessboard/__tests__/gameChat.test.ts ---
// The game chat (gameChat.ts): parsing the chat_message event, the feed of the last CHAT_HISTORY messages, sending text
// (truncation to CHAT_TEXT_MAX, an empty one is not sent) and a quick phrase by code.

import {afterEach, describe, expect, it, vi} from 'vitest';
import {appendChat, CHAT_HISTORY, CHAT_TEXT_MAX, chatItemFrom, sendChatPreset, sendChatText} from '../gameChat';
import {gameSocket} from '../../../services/gameSocket';

afterEach(() => vi.restoreAllMocks());

describe('game chat', () => {
    it('a message from an event: text or a quick phrase code; an empty one and one without a sender — null', () => {
        expect(chatItemFrom({sender: 'bob', text: 'Hello', timestamp: 5})).toEqual({sender: 'bob', text: 'Hello', timestamp: 5});
        expect(chatItemFrom({sender: 'bob', text: 'ignore', preset: 'good_luck', timestamp: 5}))
            .toEqual({sender: 'bob', text: '', preset: 'good_luck', timestamp: 5});
        expect(chatItemFrom({sender: 'bob', preset: 'nonsense'})).toBeNull();
        expect(chatItemFrom({text: 'who?'})).toBeNull();
    });

    it('the feed keeps the last CHAT_HISTORY messages', () => {
        let list = Array.from({length: CHAT_HISTORY}, (_, i) => ({sender: 'a', text: String(i), timestamp: i}));
        list = appendChat(list, {sender: 'a', text: 'new', timestamp: 99});
        expect(list).toHaveLength(CHAT_HISTORY);
        expect(list[0].text).toBe('1');
        expect(list.at(-1)?.text).toBe('new');
    });

    it('sending: text is truncated, an empty one is not sent; a quick phrase — by code', () => {
        const send = vi.spyOn(gameSocket, 'send').mockImplementation(() => undefined);
        expect(sendChatText(7, '   ')).toBe(false);
        expect(send).not.toHaveBeenCalled();
        expect(sendChatText(7, ` ${'x'.repeat(CHAT_TEXT_MAX + 10)} `)).toBe(true);
        expect(send).toHaveBeenLastCalledWith('chat_message', {game_id: 7, text: 'x'.repeat(CHAT_TEXT_MAX)});
        sendChatPreset(7, 'thanks');
        expect(send).toHaveBeenLastCalledWith('chat_message', {game_id: 7, preset: 'thanks'});
    });
});
