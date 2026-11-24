// Game chat panel in kid mode (task 23.1): only quick phrases — free text from others is not shown and cannot be typed.

import {render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {GameChatPanel} from '../GameChatPanel';
import type {ChatMessageItem} from '../types';
import {setKidModeOn} from '../../../services/kidMode';

const messages: ChatMessageItem[] = [
    {sender: 'bob', text: 'hello there', timestamp: 1},
    {sender: 'bob', text: '', preset: 'good_luck', timestamp: 2},
];

function renderPanel() {
    render(<GameChatPanel messages={messages} chatInput="" onChatInputChange={vi.fn()} onSendMessage={vi.fn()}
                          onSendPreset={vi.fn()} isSpectator={false} onLeaveSpectate={vi.fn()} myName="alice"/>);
}

afterEach(() => setKidModeOn(false));

describe('GameChatPanel: kid mode', () => {
    it('an adult sees free text and the input', () => {
        renderPanel();
        expect(screen.getByText('hello there')).toBeInTheDocument();
        expect(screen.getByPlaceholderText('Write a message…')).toBeInTheDocument();
    });

    it('a kid sees only quick phrases and a note instead of the input', () => {
        setKidModeOn(true);
        renderPanel();
        expect(screen.queryByText('hello there')).toBeNull();
        expect(screen.getAllByText('👋 Good luck!').length).toBeGreaterThan(0);
        expect(screen.queryByPlaceholderText('Write a message…')).toBeNull();
        expect(screen.getByTestId('chat-kid-mode')).toHaveTextContent('Kid mode: quick phrases only.');
    });
});
