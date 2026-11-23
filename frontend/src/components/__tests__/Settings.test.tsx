// --- FILE: frontend/src/components/__tests__/Settings.test.tsx ---
// Settings: the appearance and the sound are saved in the browser, a password change sends a request, replaces
// the token and does not let a server-side WebSocket close log the player out.

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, describe, expect, it, vi, type Mock} from 'vitest';
import Settings from '../Settings';
import {gameSocket} from '../../services/gameSocket';
import {soundEngine} from '../../services/soundEngine';
import {getToken, setToken} from '../../services/authToken';
import {setEarnedForTests} from '../../config/unlocks';

vi.mock('../../services/gameSocket', () => ({
    gameSocket: {connect: vi.fn(), disconnect: vi.fn(), send: vi.fn(), on: vi.fn(), off: vi.fn()},
}));

vi.mock('../../services/soundEngine', async (importOriginal) => {
    const original = await importOriginal<typeof import('../../services/soundEngine')>();
    let muted = false;
    let soundSet = 'wood';
    return {
        SOUND_SETS: original.SOUND_SETS,
        soundEngine: {
            play: vi.fn(),
            isMuted: vi.fn(() => muted),
            toggleMute: vi.fn(() => {
                muted = !muted;
                return muted;
            }),
            getSoundSet: vi.fn(() => soundSet),
            setSoundSet: vi.fn((id: string) => {
                soundSet = id;
            }),
        },
    };
});

const response = (status: number, body: unknown = {}) =>
    ({ok: status < 400, status, json: async () => body}) as Response;

function renderSettings(props: Partial<React.ComponentProps<typeof Settings>> = {}) {
    const onTokenChange = vi.fn();
    const onLogoutEverywhere = vi.fn();
    // In the app the page token is the same as in the login storage: App takes it from authToken.
    setToken(props.token === undefined ? 'old-token' : props.token);
    render(
        <MemoryRouter>
            <Settings
                token="old-token"
                username="alice"
                onTokenChange={onTokenChange}
                onLogoutEverywhere={onLogoutEverywhere}
                {...props}
            />
        </MemoryRouter>,
    );
    return {onTokenChange, onLogoutEverywhere};
}

function fillPasswords(current: string, next: string, repeat: string = next) {
    fireEvent.change(screen.getByLabelText('Current password'), {target: {value: current}});
    fireEvent.change(screen.getByLabelText(/New password \(at least/), {target: {value: next}});
    fireEvent.change(screen.getByLabelText('New password again'), {target: {value: repeat}});
    fireEvent.click(screen.getByRole('button', {name: 'Change password'}));
}

beforeEach(() => {
    localStorage.clear();
    (gameSocket.disconnect as Mock).mockClear();
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('Settings: appearance and sound', () => {
    it('the choice of board and pieces is saved in the browser', () => {
        renderSettings();

        fireEvent.click(screen.getByRole('button', {name: 'Graphite'}));
        fireEvent.click(screen.getByRole('button', {name: 'Staunton (Tournament)'}));

        expect(localStorage.getItem('regence_board_theme')).toBe('slate');
        expect(localStorage.getItem('regence_piece_set')).toBe('cburnett');
        expect(screen.getByRole('button', {name: 'Graphite'})).toHaveAttribute('aria-pressed', 'true');
    });

    it('the sound switch changes the state and blocks the test when the sound is off', () => {
        renderSettings();
        const toggle = screen.getByRole('switch');
        expect(toggle).toHaveAttribute('aria-checked', 'true');

        fireEvent.click(toggle);

        expect(soundEngine.toggleMute).toHaveBeenCalled();
        expect(toggle).toHaveAttribute('aria-checked', 'false');
        expect(screen.getByRole('button', {name: 'Test'})).toBeDisabled();
    });

    it('a one-click theme preset: all parts are chosen, the choice goes to the profile; a manual change clears the mark', async () => {
        const fetchMock = vi.fn(async () => response(200, {}));
        vi.stubGlobal('fetch', fetchMock);
        setToken('old-token');
        setEarnedForTests(['wins_10']);   // the marble board is unlocked for ten wins (task 18.4)
        renderSettings();
        fireEvent.click(screen.getByTestId('preset-marble_hall'));
        expect(localStorage.getItem('regence_board_theme')).toBe('marble');
        expect(localStorage.getItem('regence_piece_set')).toBe('celtic');
        expect(localStorage.getItem('regence_page_pattern')).toBe('marble');
        expect(soundEngine.setSoundSet).toHaveBeenCalledWith('marble');
        expect(screen.getByTestId('preset-marble_hall')).toHaveAttribute('aria-pressed', 'true');
        await waitFor(() => expect((fetchMock.mock.calls as unknown as [string, RequestInit][])
            .some(([url, init]) => url.endsWith('/profile/me/settings') && init.body === JSON.stringify({theme_preset: 'marble_hall'}))).toBe(true));
        fireEvent.click(screen.getByRole('button', {name: 'Graphite'}));
        expect(screen.getByTestId('preset-marble_hall')).toHaveAttribute('aria-pressed', 'false');
        setToken(null);
    });

    it('a separate theme for game review: a preset or "as in the game"', () => {
        renderSettings();
        fireEvent.change(screen.getByTestId('analysis-theme'), {target: {value: 'study'}});
        expect(localStorage.getItem('regence_analysis_board_theme')).toBe('leather');
        expect(localStorage.getItem('regence_analysis_piece_set')).toBe('mpchess');
        expect(localStorage.getItem('regence_board_theme')).toBeNull();
        fireEvent.change(screen.getByTestId('analysis-theme'), {target: {value: 'same'}});
        expect(localStorage.getItem('regence_analysis_board_theme')).toBeNull();
    });

    it('board settings: showing the opponent\'s move, move input, the quick move are saved', () => {
        renderSettings();
        fireEvent.click(screen.getByTestId('pref-lastMove-arrow'));
        fireEvent.click(screen.getByTestId('pref-moveInput-click'));
        fireEvent.click(screen.getByTestId('pref-quickMove'));
        fireEvent.click(screen.getByTestId('pref-captured-order'));
        expect(JSON.parse(localStorage.getItem('regence_board_prefs')!)).toMatchObject(
            {lastMove: 'arrow', moveInput: 'click', quickMove: true, captured: 'order'});
        expect(screen.getByTestId('pref-lastMove-arrow')).toHaveAttribute('aria-checked', 'true');
    });

    it('a locked appearance: visible with the condition, cannot be chosen; after the achievement — can be', () => {
        setEarnedForTests([]);
        renderSettings();
        expect(screen.getByTestId('lock-preset-marble_hall')).toHaveTextContent('Unlocks with the achievement «Ten wins»');
        expect(screen.getByTestId('preset-marble_hall')).toBeDisabled();
        expect(screen.getByTestId('board-marble')).toBeDisabled();
        expect(screen.getByTestId('pieces-lewis')).toHaveAttribute('title', 'Unlocks with the achievement «Champion»');
        fireEvent.click(screen.getByTestId('board-marble'));
        expect(localStorage.getItem('regence_board_theme')).toBeNull();
        act(() => setEarnedForTests(['wins_10', 'tournament_win']));
        expect(screen.getByTestId('board-marble')).not.toBeDisabled();
        expect(screen.getByTestId('pieces-lewis')).not.toBeDisabled();
        setEarnedForTests([]);
    });

    it('the sound set is chosen separately', () => {
        renderSettings();
        // The sound could have stayed off from the previous test (a shared mock) — sets are unavailable when the sound is off.
        if (screen.getByRole('switch').getAttribute('aria-checked') === 'false') fireEvent.click(screen.getByRole('switch'));
        fireEvent.click(screen.getByRole('button', {name: 'Bright'}));
        expect(soundEngine.setSoundSet).toHaveBeenCalledWith('bright');
        expect(screen.getByRole('button', {name: 'Bright'})).toHaveAttribute('aria-pressed', 'true');
    });
});

describe('Settings: password change', () => {
    it('a successful change replaces the token and disconnects the WebSocket in advance', async () => {
        const fetchMock = vi.fn(async () => response(200, {access_token: 'new-token', token_type: 'bearer'}));
        vi.stubGlobal('fetch', fetchMock);
        const {onTokenChange} = renderSettings();

        fillPasswords('old-password', 'new-password-1');

        await waitFor(() => expect(onTokenChange).toHaveBeenCalledWith('new-token'));
        expect(getToken()).toBe('new-token');
        expect(screen.getByRole('status')).toHaveTextContent('Password changed');

        const [url, init] = (fetchMock.mock.calls as unknown as [string, RequestInit][]).filter(([url]) => !/\/profile\/me|\/beta\/my-invite/.test(String(url)))[0] as unknown as [string, RequestInit];
        expect(url).toContain('/api/v1/auth/change-password');
        expect((init.headers as Record<string, string>).Authorization).toBe('Bearer old-token');
        expect(JSON.parse(init.body as string)).toEqual({
            current_password: 'old-password', new_password: 'new-password-1',
        });
        // Otherwise the server closing the socket (sessions revoked) would log the player out.
        expect(gameSocket.disconnect).toHaveBeenCalled();
    });

    it('a wrong current password shows the server text and does not touch the token', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => response(400, {detail: 'The current password is incorrect'})));
        const {onTokenChange} = renderSettings();

        fillPasswords('wrong', 'new-password-1');

        expect(await screen.findByRole('alert')).toHaveTextContent('The current password is incorrect');
        expect(onTokenChange).not.toHaveBeenCalled();
        expect(getToken()).toBe('old-token');
    });

    it.each([
        ['short', 'short', /at least 8 characters/],
        ['new-password-1', 'new-password-2', /do not match/],
    ])('password %s / %s is rejected before the request', (next, repeat, message) => {
        const fetchMock = vi.fn();
        vi.stubGlobal('fetch', fetchMock);
        renderSettings();

        fillPasswords('old-password', next, repeat);

        expect(screen.getByRole('alert')).toHaveTextContent(message);
        // Only the profile was requested (the e-mail for the section) — the password change did not go to the server.
        expect((fetchMock.mock.calls as unknown as [string][]).filter(([url]) => !/\/profile\/me|\/beta\/my-invite/.test(String(url)))).toEqual([]);
    });

    it('the "Log out on all devices" button calls logout', () => {
        const {onLogoutEverywhere} = renderSettings();
        fireEvent.click(screen.getByRole('button', {name: 'Log out on all devices'}));
        expect(onLogoutEverywhere).toHaveBeenCalled();
    });

    it('a guest has only the appearance available', () => {
        renderSettings({token: null, username: null});
        expect(screen.queryByRole('button', {name: 'Change password'})).not.toBeInTheDocument();
        expect(screen.getByText(/Log in to change your password/)).toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Graphite'})).toBeInTheDocument();
    });
});

describe('Settings: my data (task 17.5)', () => {
    it('account deletion: confirmation, the password goes to the server, then logout', async () => {
        const fetchMock = vi.fn(async () => response(204));
        vi.stubGlobal('fetch', fetchMock);
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        setToken('old-token');
        const onAccountDeleted = vi.fn();
        renderSettings({onAccountDeleted});
        fireEvent.change(screen.getByTestId('settings-delete-password'), {target: {value: 'secret-pass'}});
        fireEvent.click(screen.getByTestId('settings-delete'));
        await waitFor(() => expect(onAccountDeleted).toHaveBeenCalled());
        const [url, init] = (fetchMock.mock.calls as unknown as [string, RequestInit][]).filter(([url]) => !/\/profile\/me|\/beta\/my-invite/.test(String(url)))[0] as unknown as [string, RequestInit];
        expect(url).toContain('/api/v1/account/delete');
        expect(JSON.parse(String(init.body))).toEqual({password: 'secret-pass'});
        expect(getToken()).toBeNull();
        expect(gameSocket.disconnect).toHaveBeenCalled();
    });

    it('a game in progress — the server text, the account is not deleted', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => response(409, {detail: {code: 'account_in_game'}})));
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        const onAccountDeleted = vi.fn();
        renderSettings({onAccountDeleted});
        fireEvent.change(screen.getByTestId('settings-delete-password'), {target: {value: 'secret-pass'}});
        fireEvent.click(screen.getByTestId('settings-delete'));
        expect(await screen.findByRole('alert')).toHaveTextContent('Finish your current game');
        expect(onAccountDeleted).not.toHaveBeenCalled();
    });

    it('without a password the delete button is unavailable; the export requests one\'s own data', async () => {
        const fetchMock = vi.fn(async () => response(200, {format: 1}));
        vi.stubGlobal('fetch', fetchMock);
        URL.createObjectURL = vi.fn(() => 'blob:x');
        URL.revokeObjectURL = vi.fn();
        renderSettings();
        expect(screen.getByTestId('settings-delete')).toBeDisabled();
        fireEvent.click(screen.getByTestId('settings-export'));
        await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
        expect(String(((fetchMock.mock.calls as unknown as [string, RequestInit][]).filter(([url]) => !/\/profile\/me|\/beta\/my-invite/.test(String(url)))[0] as unknown as [string])[0])).toContain('/api/v1/account/export');
    });
});

describe('Settings: e-mail (task 17.5)', () => {
    it('linking: the address, the password and the language go to the server, a hint about the letter', async () => {
        const fetchMock = vi.fn(async (url: string) => (url.includes('/profile/me')
            ? response(200, {email: null}) : response(202)));
        vi.stubGlobal('fetch', fetchMock);
        renderSettings();
        expect(await screen.findByText('No e-mail linked.')).toBeInTheDocument();
        fireEvent.change(screen.getByTestId('settings-email-input'), {target: {value: 'alice@example.com'}});
        fireEvent.change(screen.getByTestId('settings-email-password'), {target: {value: 'secret-pass'}});
        fireEvent.click(screen.getByTestId('settings-email-send'));
        expect(await screen.findByText(/A letter has been sent to alice@example.com/)).toBeInTheDocument();
        const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/account/email')) as unknown as [string, RequestInit];
        expect(JSON.parse(String(call[1].body))).toEqual({email: 'alice@example.com', password: 'secret-pass', language: 'en'});
    });

    it('the linked address is shown, it can be unlinked with a password', async () => {
        const fetchMock = vi.fn(async (url: string) => (url.includes('/profile/me')
            ? response(200, {email: 'alice@example.com'}) : response(204)));
        vi.stubGlobal('fetch', fetchMock);
        renderSettings();
        expect(await screen.findByText('Linked: alice@example.com')).toBeInTheDocument();
        fireEvent.change(screen.getByTestId('settings-email-password'), {target: {value: 'secret-pass'}});
        fireEvent.click(screen.getByTestId('settings-email-remove'));
        expect(await screen.findByText('E-mail unlinked.')).toBeInTheDocument();
        expect(screen.getByTestId('settings-email-current').textContent).toBe('No e-mail linked.');
    });
});
