// Pages of links from e-mails (task 17.5): e-mail confirmation and a new password.

import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {ResetPasswordPage, VerifyEmailPage} from '../EmailLinkPages';
import {getToken, setToken} from '../../services/authToken';

const response = (status: number, body: unknown = {}) => ({ok: status < 400, status, json: async () => body}) as Response;

afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
});

describe('links from e-mails', () => {
    it('confirmation: the token from the address is sent once, the address is shown', async () => {
        const fetchMock = vi.fn(async () => response(200, {email: 'alice@example.com'}));
        vi.stubGlobal('fetch', fetchMock);
        render(<MemoryRouter initialEntries={['/verify-email?token=abcdefghijkl']}><VerifyEmailPage/></MemoryRouter>);
        expect(await screen.findByRole('status')).toHaveTextContent('The address alice@example.com is confirmed');
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body)))
            .toEqual({token: 'abcdefghijkl'});
    });

    it('an outdated link — the server text', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => response(400, {detail: {code: 'email_link_invalid'}})));
        render(<MemoryRouter initialEntries={['/verify-email?token=abcdefghijkl']}><VerifyEmailPage/></MemoryRouter>);
        expect(await screen.findByRole('alert')).toHaveTextContent('The link is invalid');
    });

    it('new password: a check of length and match, then saving and logout', async () => {
        const fetchMock = vi.fn(async () => response(204));
        vi.stubGlobal('fetch', fetchMock);
        setToken('old');
        render(<MemoryRouter initialEntries={['/reset-password?token=abcdefghijkl']}><ResetPasswordPage/></MemoryRouter>);
        fireEvent.change(screen.getByLabelText(/New password \(at least/), {target: {value: 'short'}});
        fireEvent.click(screen.getByRole('button', {name: 'Save password'}));
        expect(screen.getByRole('alert')).toHaveTextContent('at least 8');
        fireEvent.change(screen.getByLabelText(/New password \(at least/), {target: {value: 'brand-new-pass'}});
        fireEvent.change(screen.getByLabelText('New password again'), {target: {value: 'brand-new-pass'}});
        fireEvent.click(screen.getByRole('button', {name: 'Save password'}));
        expect(await screen.findByRole('status')).toHaveTextContent('Password changed');
        expect(JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body)))
            .toEqual({token: 'abcdefghijkl', new_password: 'brand-new-pass'});
        expect(getToken()).toBeNull();
    });
});
