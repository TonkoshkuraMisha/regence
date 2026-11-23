// The app on a phone (task 24.2): registering the service worker only in a build, installing on a browser event,
// a hint for iPhone, "already installed".

import {act, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {initPwa, installState, isIos, promptInstall, resetPwaForTests} from '../pwa';
import {InstallAppSection} from '../../components/settings/InstallAppSection';

function fakeWindow({userAgent = 'Mozilla/5.0 (X11; Linux x86_64)', standalone = false, touch = 0, sw = true} = {}) {
    const target = new EventTarget();
    const register = vi.fn(async () => ({}));
    const win = {
        addEventListener: target.addEventListener.bind(target),
        dispatchEvent: target.dispatchEvent.bind(target),
        document: {readyState: 'complete'},
        matchMedia: () => ({matches: standalone}),
        navigator: {userAgent, maxTouchPoints: touch, ...(sw ? {serviceWorker: {register}} : {})},
    } as unknown as Window;
    return {win, register};
}

function installEvent(outcome: 'accepted' | 'dismissed') {
    const event = new Event('beforeinstallprompt') as Event & { prompt: () => Promise<void>; userChoice: Promise<unknown> };
    event.prompt = vi.fn(async () => undefined);
    event.userChoice = Promise.resolve({outcome});
    return event;
}

beforeEach(() => resetPwaForTests());
afterEach(() => resetPwaForTests());

describe('PWA', () => {
    it('the service worker is registered only in a build', () => {
        const dev = fakeWindow();
        initPwa(dev.win, false);
        expect(dev.register).not.toHaveBeenCalled();
        const prod = fakeWindow();
        initPwa(prod.win, true);
        expect(prod.register).toHaveBeenCalledWith('/sw.js');
    });

    it('without service worker support nothing breaks', () => {
        const {win} = fakeWindow({sw: false});
        expect(() => initPwa(win, true)).not.toThrow();
    });

    it('the browser event enables installation; consent — "installed"', async () => {
        const {win} = fakeWindow();
        initPwa(win, false);
        expect(installState(win)).toBe('unsupported');
        const event = installEvent('accepted');
        win.dispatchEvent(event);
        expect(installState(win)).toBe('available');
        expect(await promptInstall()).toBe(true);
        expect(event.prompt).toHaveBeenCalled();
        expect(installState(win)).toBe('installed');
    });

    it('refusal — the button disappears until the next browser event', async () => {
        const {win} = fakeWindow();
        initPwa(win, false);
        win.dispatchEvent(installEvent('dismissed'));
        expect(await promptInstall()).toBe(false);
        expect(installState(win)).toBe('unsupported');
        expect(await promptInstall()).toBe(false);
    });

    it('iPhone and iPad (iPadOS poses as a Mac) — a hint; opened from the home screen — installed', () => {
        expect(isIos(fakeWindow({userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)'}).win)).toBe(true);
        expect(isIos(fakeWindow({userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', touch: 5}).win)).toBe(true);
        expect(isIos(fakeWindow({userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}).win)).toBe(false);
        expect(installState(fakeWindow({userAgent: 'iPhone'}).win)).toBe('ios');
        expect(installState(fakeWindow({standalone: true}).win)).toBe('installed');
    });

    it('settings section: the button appears on the browser event and opens the system dialog', async () => {
        initPwa(window, false);
        render(<InstallAppSection sectionClass="" headingClass=""/>);
        expect(screen.queryByTestId('settings-app-install')).toBeNull();
        expect(screen.getByTestId('settings-app-state')).toHaveTextContent('browser menu');
        const event = installEvent('accepted');
        act(() => {
            window.dispatchEvent(event);
        });
        fireEvent.click(await screen.findByTestId('settings-app-install'));
        expect(event.prompt).toHaveBeenCalled();
        expect(await screen.findByText(/The app is installed/)).toBeInTheDocument();
    });
});
