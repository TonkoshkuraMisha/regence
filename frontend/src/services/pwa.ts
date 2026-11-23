// --- FILE: frontend/src/services/pwa.ts ---
// Mobile app (task 24.2): service worker registration (public/sw.js) and installation to the home screen.
//
// The service worker runs only in the build: in development it would cache Vite files and break hot reload.
// Installation: Chrome and Edge send beforeinstallprompt — the event is saved, and the button in settings shows
// the system dialog; their own install offer is not disabled. Safari on iPhone does not send the event
// — there a hint is shown: "Share → Add to Home Screen".

import {useSyncExternalStore} from 'react';

/** The Chrome and Edge "app can be installed" event; it is absent from the standard DOM types. */
interface BeforeInstallPromptEvent extends Event {
    prompt(): Promise<void>;
    userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

/**
 * What to show in settings: installed — already installed (or opened as an app); available — a
 * saved event exists, the button will show the system dialog; ios — a hint for Safari; unsupported — nothing.
 */
export type InstallState = 'installed' | 'available' | 'ios' | 'unsupported';

let deferredPrompt: BeforeInstallPromptEvent | null = null;
let installedNow = false;
const listeners = new Set<() => void>();

function notify(): void {
    listeners.forEach((listener) => listener());
}

/** The page is opened as an installed app (display-mode: standalone; in Safari — navigator.standalone). */
export function isStandalone(win: Window = window): boolean {
    const nav = win.navigator as Navigator & { standalone?: boolean };
    return Boolean(win.matchMedia?.('(display-mode: standalone)').matches || nav.standalone);
}

/** iPhone, iPad or iPod — by the User-Agent string. */
export function isIos(win: Window = window): boolean {
    const nav = win.navigator;
    // iPad with iPadOS 13+ presents itself as a Mac, but with a touch screen.
    return /iphone|ipad|ipod/i.test(nav.userAgent) || (/Macintosh/.test(nav.userAgent) && nav.maxTouchPoints > 1);
}

/** Current installation state — see InstallState; the order of checks matters: installed takes precedence over available. */
export function installState(win: Window = window): InstallState {
    if (installedNow || isStandalone(win)) return 'installed';
    if (deferredPrompt) return 'available';
    if (isIos(win)) return 'ios';
    return 'unsupported';
}

/** System install dialog; true — the player accepted. */
export async function promptInstall(): Promise<boolean> {
    const event = deferredPrompt;
    if (!event) return false;
    deferredPrompt = null;
    await event.prompt();
    const choice = await event.userChoice;
    if (choice.outcome === 'accepted') installedNow = true;
    notify();
    return choice.outcome === 'accepted';
}

/**
 * Called once at app start (main.tsx): subscribes to install events and — in the build only —
 * registers /sw.js after the page loads. A registration error is swallowed: the site works without a service worker.
 */
export function initPwa(win: Window = window, production: boolean = import.meta.env.PROD): void {
    win.addEventListener('beforeinstallprompt', (event) => {
        deferredPrompt = event as BeforeInstallPromptEvent;
        notify();
    });
    win.addEventListener('appinstalled', () => {
        deferredPrompt = null;
        installedNow = true;
        notify();
    });
    const serviceWorker = win.navigator.serviceWorker;
    if (production && serviceWorker) {
        const register = () => {
            serviceWorker.register('/sw.js').catch(() => undefined);
        };
        if (win.document.readyState === 'complete') register();
        else win.addEventListener('load', register, {once: true});
    }
}

function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

/** Hook: installation state, updated on browser events (settings/InstallAppSection.tsx). */
export function useInstallState(): InstallState {
    return useSyncExternalStore(subscribe, () => installState());
}

/** For tests: forget the saved event and the installation. */
export function resetPwaForTests(): void {
    deferredPrompt = null;
    installedNow = false;
    notify();
}
