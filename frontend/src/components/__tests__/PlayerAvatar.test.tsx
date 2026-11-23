// Own avatars (task 18.4): by name until chosen; a choice of piece and background; no external addresses.

import {fireEvent, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {AvatarPicker, PlayerAvatar, avatarCode} from '../PlayerAvatar';

describe('avatars', () => {
    it('by name — stable and without external addresses; the chosen one — as chosen; junk — by name', () => {
        expect(avatarCode('magnus')).toBe(avatarCode('Magnus'));
        expect(avatarCode('magnus')).toMatch(/^[wb][KQRBNP]-[0-7]$/);
        expect(avatarCode('magnus', 'bN-3')).toBe('bN-3');
        expect(avatarCode('magnus', 'https://evil/x.svg')).toBe(avatarCode('magnus'));
        render(<PlayerAvatar username="magnus" avatar="wQ-2"/>);
        const img = screen.getByTestId('player-avatar').querySelector('img')!;
        expect(img.getAttribute('src')).toBe('/assets/pieces/lewis/wQ.svg');
    });

    it('choice: a piece keeps the background, a background keeps the piece', () => {
        const onChange = vi.fn();
        render(<AvatarPicker username="magnus" value="wQ-2" onChange={onChange}/>);
        expect(screen.getByTestId('avatar-piece-wQ')).toHaveAttribute('aria-pressed', 'true');
        fireEvent.click(screen.getByTestId('avatar-piece-bN'));
        expect(onChange).toHaveBeenLastCalledWith('bN-2');
        fireEvent.click(screen.getByTestId('avatar-bg-5'));
        expect(onChange).toHaveBeenLastCalledWith('wQ-5');
    });
});
