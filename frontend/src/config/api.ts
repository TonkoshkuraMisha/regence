// --- FILE: frontend/src/config/api.ts ---

/**
 * API and WebSocket addresses.
 *
 * Development: Vite (port 3000) and uvicorn (port 8000) are different origins, default 127.0.0.1:8000.
 * Production (build behind nginx): frontend and API share one domain, so the API default is
 * a relative path, and the WebSocket is the same host with ws/wss by the page protocol.
 * VITE_API_URL / VITE_WS_URL override both variants.
 */

const DEV_API_URL = 'http://127.0.0.1:8000';
const DEV_WS_URL = 'ws://127.0.0.1:8000';

function sameOriginWsUrl(): string {
    if (typeof window === 'undefined' || !window.location) return DEV_WS_URL;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}`;
}

export const API_BASE_URL: string =
    import.meta.env.VITE_API_URL ?? (import.meta.env.PROD ? '' : DEV_API_URL);

export const WS_BASE_URL: string =
    import.meta.env.VITE_WS_URL || (import.meta.env.PROD ? sameOriginWsUrl() : DEV_WS_URL);
