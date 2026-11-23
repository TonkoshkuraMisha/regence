// --- FILE: frontend/public/sw.js ---
// Service worker of the app (task 24.2). The task is modest: installation to the home screen and an honest offline page, not
// play without a network: games, puzzles and review live on the server.
//
// * Page navigations: network first; without a network, /offline.html (in three languages, its own script: CSP forbids
//   inline ones).
// * Build files and images (/assets/, /icons/): from the cache if already loaded: Vite build names with a hash do not
//   change, and pieces and textures are cached as they are shown.
// * /api/ and everything foreign are not touched: server responses must not go stale in a cache.
// A new file version (VERSION) deletes the old caches on the next open.

const VERSION = 'v1';
const SHELL_CACHE = `regence-shell-${VERSION}`;
const ASSET_CACHE = `regence-assets-${VERSION}`;
const OFFLINE_URL = '/offline.html';
const SHELL = [OFFLINE_URL, '/offline.js', '/favicon.svg', '/icons/icon-192.png', '/manifest.webmanifest'];
// How many files to keep in the image and build cache: old build versions and rare pieces are evicted.
const ASSET_LIMIT = 300;

self.addEventListener('install', (event) => {
    event.waitUntil(caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(keys
                // Caches of the former platform name (michess-..., before 18.11.2026) are deleted too.
                .filter((key) => (key.startsWith('regence-') || key.startsWith('michess-')) && key !== SHELL_CACHE && key !== ASSET_CACHE)
                .map((key) => caches.delete(key))))
            .then(() => self.clients.claim()),
    );
});

async function trim(cache) {
    const keys = await cache.keys();
    await Promise.all(keys.slice(0, Math.max(0, keys.length - ASSET_LIMIT)).map((key) => cache.delete(key)));
}

async function fromCacheOrNetwork(request) {
    // First in all caches: the offline page files are in the shell cache.
    const cached = await caches.match(request);
    if (cached) return cached;
    const cache = await caches.open(ASSET_CACHE);
    const response = await fetch(request);
    if (response.ok && response.type === 'basic') {
        await cache.put(request, response.clone());
        trim(cache).catch(() => undefined);
    }
    return response;
}

async function pageOrOffline(request) {
    try {
        return await fetch(request);
    } catch {
        const offline = await caches.match(OFFLINE_URL);
        return offline ?? Response.error();
    }
}

self.addEventListener('fetch', (event) => {
    const {request} = event;
    if (request.method !== 'GET') return;
    const url = new URL(request.url);
    if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
    if (request.mode === 'navigate') {
        event.respondWith(pageOrOffline(request));
        return;
    }
    if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icons/') || SHELL.includes(url.pathname)) {
        event.respondWith(fromCacheOrNetwork(request));
    }
});
