// Login and registration: the request format, saving the token, error texts (a wrong password,
// the attempt limit, name validation errors) and switching modes.

import {fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import AuthModal from '../AuthModal';
import {DEFAULT_CONFIG, GUEST_STORAGE_KEY} from '../../services/personalities';
import {getToken} from '../../services/authToken';

const response = (status: number, body: unknown = {}) =>
    ({ok: status < 400, status, json: async () => body}) as Response;

function stubFetch(reply: Response) {
    const fetchMock = vi.fn(async () => reply);
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

function fillAndSubmit(username: string, password: string, submitLabel: RegExp) {
    fireEvent.change(screen.getByPlaceholderText('e.g. string1'), {target: {value: username}});
    fireEvent.change(screen.getByPlaceholderText('••••••••'), {target: {value: password}});
    // Consent to the rules and privacy (task 23.1) exists only in the registration mode.
    const terms = screen.queryByTestId('auth-terms');
    if (terms) fireEvent.click(terms);
    fireEvent.click(screen.getByRole('button', {name: submitLabel}));
}

beforeEach(() => {
    localStorage.clear();
});

describe('AuthModal: consent to the terms (task 23.1)', () => {
    it('registration has a required checkbox with links to the rules and privacy; login does not', () => {
        render(<AuthModal onSuccess={vi.fn()}/>);
        expect(screen.queryByTestId('auth-terms')).toBeNull();
        fireEvent.click(screen.getByRole('button', {name: 'No account? Sign up'}));
        const terms = screen.getByTestId('auth-terms');
        expect(terms).toBeRequired();
        expect(terms).not.toBeChecked();
        expect(screen.getByRole('link', {name: 'terms of use'})).toHaveAttribute('href', '/terms');
        expect(screen.getByRole('link', {name: 'community rules'})).toHaveAttribute('href', '/rules');
        expect(screen.getByRole('link', {name: 'privacy summary'})).toHaveAttribute('href', '/privacy');
    });
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('AuthModal: login', () => {
    it('sends the OAuth2 form and saves the token', async () => {
        const fetchMock = stubFetch(response(200, {access_token: 'jwt-123'}));
        const onSuccess = vi.fn();
        render(<AuthModal onSuccess={onSuccess}/>);

        fillAndSubmit('alice', 'secret-pass', /Log in/);

        await vi.waitFor(() => expect(onSuccess).toHaveBeenCalledWith('jwt-123'));
        expect(getToken()).toBe('jwt-123');
        const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(url).toMatch(/\/api\/v1\/auth\/login$/);
        expect(init.method).toBe('POST');
        expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/x-www-form-urlencoded');
        expect(String(init.body)).toBe('username=alice&password=secret-pass');
    });

    it('a wrong password — a clear error, the token is not saved', async () => {
        stubFetch(response(401, {detail: {code: 'login_failed', params: {}, message: 'Incorrect username or password'}}));
        const onSuccess = vi.fn();
        render(<AuthModal onSuccess={onSuccess}/>);

        fillAndSubmit('alice', 'wrong', /Log in/);

        expect(await screen.findByText('Wrong username or password')).toBeInTheDocument();
        expect(onSuccess).not.toHaveBeenCalled();
        expect(getToken()).toBeNull();
        expect(screen.getByRole('button', {name: /Log in/})).not.toBeDisabled();
    });

    it('the attempt limit — how long to wait, not "wrong password"', async () => {
        stubFetch(response(429, {detail: {code: 'too_many_login_attempts', params: {retry_after: 60}, message: '…'}}));
        render(<AuthModal onSuccess={vi.fn()}/>);

        fillAndSubmit('alice', 'secret-pass', /Log in/);

        expect(await screen.findByText('Too many login attempts — please try again in 60 s')).toBeInTheDocument();
    });

    it('a network failure is shown to the user', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => {
            throw new Error('Failed to fetch');
        }));
        render(<AuthModal onSuccess={vi.fn()}/>);

        fillAndSubmit('alice', 'secret-pass', /Log in/);

        // The browser exception text ("Failed to fetch") is not shown — it is not in the player's language.
        expect(await screen.findByText('No connection to the server, please try again')).toBeInTheDocument();
    });
});

describe('AuthModal: transferring guest opponents', () => {
    it('the refusal reason comes as a code and is shown in the player\'s language', async () => {
        localStorage.setItem(GUEST_STORAGE_KEY, JSON.stringify([
            {id: 'local-1', name: 'Overflow', config: DEFAULT_CONFIG, created_at: '', updated_at: ''},
        ]));
        vi.stubGlobal('confirm', vi.fn(() => true));
        const alertMock = vi.fn();
        vi.stubGlobal('alert', alertMock);
        vi.stubGlobal('fetch', vi.fn(async (url: string) => (String(url).endsWith('/auth/login')
            ? response(200, {access_token: 'jwt-1'})
            : response(200, {created: [], skipped: [{name: 'Overflow', reason: 'personality_limit', params: {max: 20}}]}))));
        render(<AuthModal onSuccess={vi.fn()}/>);

        fillAndSubmit('alice', 'secret-pass', /Log in/);

        await vi.waitFor(() => expect(alertMock).toHaveBeenCalledWith(
            'Not transferred: Overflow — No more than 20 opponents in the workshop — delete some',
        ));
    });
});

describe('AuthModal: registration', () => {
    function switchToRegistration() {
        fireEvent.click(screen.getByRole('button', {name: 'No account? Sign up'}));
        expect(screen.getByText('Create an account')).toBeInTheDocument();
    }

    function stubAuth(login: Response, created: Record<string, unknown> = {id: 1, username: 'alice', blitz_rating: 1200}) {
        const fetchMock = vi.fn(async (url: string) => (String(url).endsWith('/auth/login')
            ? login : response(201, created)));
        vi.stubGlobal('fetch', fetchMock);
        return fetchMock;
    }

    it('after registration it logs in at once and offers the first game (task 17.8)', async () => {
        const fetchMock = stubAuth(response(200, {access_token: 'jwt-new'}), {id: 1, username: 'alice', blitz_rating: 600});
        const onSuccess = vi.fn();
        const onFirstGame = vi.fn();
        render(<AuthModal onSuccess={onSuccess} onFirstGame={onFirstGame}/>);
        switchToRegistration();
        fireEvent.change(screen.getByLabelText('How long have you been playing? (optional)'), {target: {value: 'new'}});
        // "Just starting" — the strength is not asked.
        expect(screen.queryByLabelText('Roughly how strong are you? (optional)')).toBeNull();

        fillAndSubmit('alice', 'secret-pass', /Sign up/);

        expect(await screen.findByText('Welcome, alice!')).toBeInTheDocument();
        expect(screen.getByTestId('auth-welcome')).toHaveTextContent('Your starting rating is 600. It is provisional for the first 30 games');
        expect(getToken()).toBe('jwt-new');
        const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(url).toMatch(/\/api\/v1\/auth\/register$/);
        expect(JSON.parse(String(init.body))).toEqual({username: 'alice', password: 'secret-pass', accept_terms: true, experience: 'new'});

        fireEvent.click(screen.getByTestId('auth-first-game'));
        expect(onSuccess).toHaveBeenCalledWith('jwt-new');
        expect(onFirstGame).toHaveBeenCalledWith(600);
    });

    it('for a beginner ("just starting") — the basics first (17.8 → 14.5)', async () => {
        stubAuth(response(200, {access_token: 'jwt-new'}), {id: 1, username: 'alice', blitz_rating: 600});
        const onSuccess = vi.fn();
        const onBasics = vi.fn();
        render(<AuthModal onSuccess={onSuccess} onFirstGame={vi.fn()} onBasics={onBasics}/>);
        switchToRegistration();
        fireEvent.change(screen.getByLabelText('How long have you been playing? (optional)'), {target: {value: 'new'}});
        fillAndSubmit('alice', 'secret-pass', /Sign up/);
        fireEvent.click(await screen.findByTestId('auth-start-basics'));
        expect(onSuccess).toHaveBeenCalledWith('jwt-new');
        expect(onBasics).toHaveBeenCalled();
        expect(screen.getByTestId('auth-first-game')).toBeInTheDocument();  // a game — optional
    });

    it('an experienced player has no basics button', async () => {
        stubAuth(response(200, {access_token: 'jwt-new'}));
        render(<AuthModal onSuccess={vi.fn()} onFirstGame={vi.fn()} onBasics={vi.fn()}/>);
        switchToRegistration();
        fireEvent.change(screen.getByLabelText('How long have you been playing? (optional)'), {target: {value: 'regular'}});
        fillAndSubmit('alice', 'secret-pass', /Sign up/);
        expect(await screen.findByTestId('auth-welcome')).toBeInTheDocument();
        expect(screen.queryByTestId('auth-start-basics')).toBeNull();
    });

    it('without answers to the questions — registration as before; "Later" just logs in', async () => {
        const fetchMock = stubAuth(response(200, {access_token: 'jwt-new'}));
        const onSuccess = vi.fn();
        const onFirstGame = vi.fn();
        render(<AuthModal onSuccess={onSuccess} onFirstGame={onFirstGame}/>);
        switchToRegistration();

        fillAndSubmit('alice', 'secret-pass', /Sign up/);

        await screen.findByTestId('auth-welcome');
        const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(JSON.parse(String(init.body))).toEqual({username: 'alice', password: 'secret-pass', accept_terms: true});
        fireEvent.click(screen.getByRole('button', {name: 'Later'}));
        expect(onSuccess).toHaveBeenCalledWith('jwt-new');
        expect(onFirstGame).not.toHaveBeenCalled();
    });

    it('if the automatic login failed — it offers to log in manually', async () => {
        stubAuth(response(500));
        const onSuccess = vi.fn();
        render(<AuthModal onSuccess={onSuccess}/>);
        switchToRegistration();

        fillAndSubmit('alice', 'secret-pass', /Sign up/);

        expect(await screen.findByText('You are registered! Now log in.')).toBeInTheDocument();
        expect(screen.getByText('Log in to regence')).toBeInTheDocument();
        expect(onSuccess).not.toHaveBeenCalled();
    });

    it('field validation errors are shown by the check type, with the field name', async () => {
        stubFetch(response(422, {
            detail: [
                {loc: ['body', 'username'], msg: 'String should have at least 3 characters', type: 'string_too_short', params: {min_length: 3}},
                {loc: ['body', 'password'], msg: 'String should have at least 8 characters', type: 'string_too_short', params: {min_length: 8}},
            ],
        }));
        render(<AuthModal onSuccess={vi.fn()}/>);
        switchToRegistration();

        fillAndSubmit('me', '123', /Sign up/);

        // The first error is shown — in the player's language and with the field name.
        expect(await screen.findByText('Username: at least 3 characters')).toBeInTheDocument();
    });

    it('switching the mode clears the error', async () => {
        stubFetch(response(409, {detail: 'The name is already taken'}));
        render(<AuthModal onSuccess={vi.fn()}/>);
        switchToRegistration();
        fillAndSubmit('alice', 'secret-pass', /Sign up/);
        expect(await screen.findByText('The name is already taken')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', {name: 'Already have an account? Log in'}));

        expect(screen.queryByText('The name is already taken')).not.toBeInTheDocument();
        expect(screen.getByText('Log in to regence')).toBeInTheDocument();
    });
});

describe('AuthModal: closing', () => {
    it('closes by Esc, the cross and a click on the backdrop, but not by a click inside the window', () => {
        const onClose = vi.fn();
        const {container} = render(<AuthModal onSuccess={vi.fn()} onClose={onClose}/>);

        fireEvent.mouseDown(screen.getByPlaceholderText('e.g. string1'));
        expect(onClose).not.toHaveBeenCalled();

        fireEvent.keyDown(window, {key: 'Escape'});
        fireEvent.click(screen.getByRole('button', {name: 'Close'}));
        fireEvent.mouseDown(container.firstChild as Element);
        expect(onClose).toHaveBeenCalledTimes(3);
    });
});

describe('AuthModal: accessibility', () => {
    it('the window is a modal dialog with a title that changes by mode', () => {
        render(<AuthModal onSuccess={vi.fn()}/>);
        const dialog = screen.getByRole('dialog', {name: 'Log in to regence'});
        expect(dialog).toHaveAttribute('aria-modal', 'true');

        fireEvent.click(screen.getByRole('button', {name: 'No account? Sign up'}));
        expect(screen.getByRole('dialog', {name: 'Create an account'})).toBeInTheDocument();
    });
});

describe('AuthModal: forgot password (task 17.5)', () => {
    it('the reset link goes to the address with the interface language, the answer is the same', async () => {
        const fetchMock = vi.fn(async () => ({ok: true, status: 202, json: async () => ({})}) as Response);
        vi.stubGlobal('fetch', fetchMock);
        render(<AuthModal onSuccess={vi.fn()}/>);
        fireEvent.click(screen.getByTestId('auth-forgot'));
        expect(screen.getByRole('heading', {name: 'Reset password'})).toBeInTheDocument();
        fireEvent.change(screen.getByLabelText('E-mail'), {target: {value: 'alice@example.com'}});
        fireEvent.click(screen.getByRole('button', {name: 'Send the link'}));
        expect(await screen.findByRole('status')).toHaveTextContent('If this address is linked to an account');
        const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
        expect(url).toContain('/api/v1/account/password-reset');
        expect(JSON.parse(String(init.body))).toEqual({email: 'alice@example.com', language: 'en'});
        fireEvent.click(screen.getByTestId('auth-forgot'));
        expect(screen.getByRole('heading', {name: /Log in/})).toBeInTheDocument();
    });
});
