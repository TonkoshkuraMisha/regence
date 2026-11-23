// --- FILE: frontend/src/components/__tests__/InviteFriend.test.tsx ---
// "Invite a friend" (26.2): a personal link with the server's code, copying and a counter of those who came through it.

import {fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {InviteFriend} from '../InviteFriend';
import {mockFetchRouter} from '../../test/mocks';

afterEach(() => vi.unstubAllGlobals());

describe('InviteFriend', () => {
    it('shows the link with the code, counts those who came and copies the link', async () => {
        vi.stubGlobal('fetch', mockFetchRouter({'/beta/my-invite': () => ({code: 'ABCDE23456', uses: 3, max_uses: 50, state: 'active'})}));
        const writeText = vi.fn(async () => undefined);
        Object.defineProperty(navigator, 'clipboard', {value: {writeText}, configurable: true});
        render(<InviteFriend/>);
        const input = await screen.findByTestId('invite-link');
        expect((input as HTMLInputElement).value).toBe(`${window.location.origin}/?invite=ABCDE23456`);
        expect(screen.getByTestId('invite-uses')).toHaveTextContent('3');
        fireEvent.click(screen.getByTestId('invite-copy'));
        expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/?invite=ABCDE23456`);
    });

    it('without a server answer there is no block', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', {status: 401})));
        const {container} = render(<InviteFriend/>);
        await Promise.resolve();
        expect(container.querySelector('[data-testid="invite-friend"]')).toBeNull();
    });
});
