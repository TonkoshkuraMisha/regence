// --- FILE: frontend/src/components/chessboard/gameChat.ts ---
// Game chat: parsing the chat_message event and sending a message over the shared WebSocket (services/gameSocket). The server
// (src/api/websockets.py, the chat_message action) truncates the text to CHAT_TEXT_MAX characters and lets only the game's players
// write. A quick phrase is sent as a code (preset), and everyone sees it in their own language. Shared by the main board
// (hooks/useGameSocket.ts) and the Fischer Random game against a human (chess960/Chess960LiveGame.tsx, the useGameChat hook).

import {useEffect, useState} from 'react';
import {gameSocket} from '../../services/gameSocket';
import {isChatPreset} from './types';
import type {ChatMessageItem, ChatPresetId} from './types';

/** Length of one's own message, as the server truncates it (raw_text[:140] in src/api/websockets.py). */
export const CHAT_TEXT_MAX = 140;
/** How many of the latest messages are kept in page memory. */
export const CHAT_HISTORY = 50;

/** Message from a chat_message event; empty or without a sender gives null. */
export function chatItemFrom(data: { sender?: string; text?: string; preset?: unknown; timestamp?: number }): ChatMessageItem | null {
    const preset = isChatPreset(data.preset) ? data.preset : undefined;
    if (!data.sender || (!data.text && !preset)) return null;
    return {sender: data.sender, text: preset ? '' : data.text ?? '', ...(preset ? {preset} : {}), timestamp: data.timestamp || Date.now()};
}

/** Append a message to the feed, keeping the last CHAT_HISTORY. */
export const appendChat = (list: ChatMessageItem[], item: ChatMessageItem) => [...list.slice(-(CHAT_HISTORY - 1)), item];

/** Send one's own text to the game chat; an empty one is not sent. Returns whether the message was sent. */
export function sendChatText(gameId: number, text: string): boolean {
    const message = text.trim();
    if (!message) return false;
    gameSocket.send('chat_message', {game_id: gameId, text: message.slice(0, CHAT_TEXT_MAX)});
    return true;
}

/** Send a quick phrase by code. */
export function sendChatPreset(gameId: number, preset: ChatPresetId): void {
    gameSocket.send('chat_message', {game_id: gameId, preset});
}

/**
 * Chat of a single game for pages outside the main board: subscription to this game's chat_message, the feed and the input field.
 * Changing the game (a rematch) clears the feed.
 */
export function useGameChat(gameId: number | null) {
    const [messages, setMessages] = useState<ChatMessageItem[]>([]);
    const [input, setInput] = useState('');
    useEffect(() => {
        setMessages([]);
        if (gameId === null) return;
        const onChat = (data: { game_id?: number | string; sender?: string; text?: string; preset?: unknown; timestamp?: number }) => {
            if (Number(data.game_id) !== gameId) return;
            const item = chatItemFrom(data);
            if (item) setMessages((list) => appendChat(list, item));
        };
        gameSocket.on('chat_message', onChat);
        return () => gameSocket.off('chat_message', onChat);
    }, [gameId]);
    return {
        messages, input, setInput,
        send: () => {
            if (gameId !== null && sendChatText(gameId, input)) setInput('');
        },
        sendPreset: (preset: ChatPresetId) => {
            if (gameId !== null) sendChatPreset(gameId, preset);
        },
    };
}
