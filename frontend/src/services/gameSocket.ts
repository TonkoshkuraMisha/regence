// --- FILE: frontend/src/services/gameSocket.ts ---
// WebSocket connection to the server (/api/v1/ws/matchmaking) — one per tab: games, lobby, notifications. Login is by a
// one-time ticket (POST /auth/ws-ticket); the token never appears in the URL. On a drop the connection is restored
// automatically (pause RECONNECT_DELAY_MS; longer after a "too often" refusal); messages sent while offline are flushed
// once connected. Components subscribe to events by name (on / off) and send actions via send(name,
// data). Server — src/api/websockets.py: the action name is looked up in ACTION_HANDLERS, replies and broadcasts arrive
// as messages {event: name, ...data}; a subscription to '*' receives all events.

import {API_BASE_URL, WS_BASE_URL} from '../config/api';
import {clearToken, getToken} from './authToken';
import {addBreadcrumb} from './breadcrumbs';

type EventCallback = (data: any) => void;

/** Pause before reconnecting after a drop or a failed ticket issue. */
const RECONNECT_DELAY_MS = 1500;
/** Pause after a 429 refusal on ticket issue: frequent attempts only extend the block. */
const RATE_LIMITED_RECONNECT_DELAY_MS = 15000;

/** The server answered 401 to the ticket request: the token expired or was revoked. */
class AuthExpiredError extends Error {}

/** The server answered 429 to the ticket request: too many connections. */
class RateLimitedError extends Error {}

/**
 * One-time ticket for WebSocket. The JWT is not put into the WebSocket URL: URLs end up in the logs of the
 * server and proxies. The ticket is obtained over HTTP with the token in a header; it is valid ~30 s and only once.
 */
async function fetchWsTicket(token: string): Promise<string> {
    const res = await fetch(`${API_BASE_URL}/api/v1/auth/ws-ticket`, {
        method: 'POST',
        headers: {Authorization: `Bearer ${token}`},
    });
    if (res.status === 401) throw new AuthExpiredError('Session expired');
    if (res.status === 429) throw new RateLimitedError('Too many reconnects');
    if (!res.ok) throw new Error(`ws-ticket: HTTP ${res.status}`);
    const data = await res.json();
    return data.ticket;
}

class GameWebSocketService {
    private ws: WebSocket | null = null;
    private currentToken: string | null = null;
    private listeners: { [event: string]: EventCallback[] } = {};
    private pendingMessages: string[] = [];
    private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    // A ticket request is in flight; the attempt number discards stale ones (after disconnect or a token change).
    private connecting = false;
    private attempt = 0;

    /** Open a connection (or keep the already open one); on a token change the previous connection is closed. */
    connect(token: string) {
        if (!token) return;

        // If the token changed (logout and login as another player), reopen the connection
        if (this.currentToken && this.currentToken !== token) {
            this.closeSocket();
            this.attempt += 1;
            this.connecting = false;
        }

        this.currentToken = token;

        if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
            return;
        }
        if (this.connecting) return;

        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }

        void this.openSocket(token);
    }

    /** Get a ticket and open the socket; a ticket error means logout (401) or a retry after a pause (429 and others). */
    private async openSocket(token: string) {
        this.connecting = true;
        const attempt = ++this.attempt;

        let ticket: string;
        try {
            ticket = await fetchWsTicket(token);
        } catch (err) {
            if (attempt !== this.attempt) return;
            this.connecting = false;
            if (err instanceof AuthExpiredError) {
                this.handleAuthExpired();
            } else {
                console.warn('Failed to get a WebSocket ticket:', err);
                this.scheduleReconnect(err instanceof RateLimitedError ? RATE_LIMITED_RECONNECT_DELAY_MS : RECONNECT_DELAY_MS);
            }
            return;
        }

        if (attempt !== this.attempt || this.currentToken !== token) return;  // disconnected while waiting
        this.connecting = false;

        const wsUrl = `${WS_BASE_URL}/api/v1/ws/matchmaking?ticket=${encodeURIComponent(ticket)}`;
        // Handlers are bound to their own socket: a previously closed socket (token change, reconnect)
        // reports the close with a delay, and without a check its onclose would reset
        // the reference to the already new socket — that one would stay alive, and the next send() would open
        // a second connection, and every event would arrive twice.
        const socket = new WebSocket(wsUrl);
        this.ws = socket;

        socket.onopen = () => {
            if (this.ws !== socket) return;
            addBreadcrumb('socket', 'open');
            while (this.pendingMessages.length > 0 && socket.readyState === WebSocket.OPEN) {
                const msg = this.pendingMessages.shift();
                if (msg) {
                    socket.send(msg);
                }
            }
        };

        socket.onmessage = (event) => {
            if (this.ws !== socket) return;
            try {
                const data = JSON.parse(event.data);
                const eventType = data.event;
                if (eventType !== 'clock_update') addBreadcrumb('socket', `event ${String(eventType)}`);

                if (this.listeners[eventType]) {
                    this.listeners[eventType].forEach(cb => cb(data));
                }
                if (this.listeners['*']) {
                    this.listeners['*'].forEach(cb => cb(data));
                }
            } catch (e) {
                console.error('Failed to parse WebSocket JSON:', e);
            }
        };

        socket.onclose = (event) => {
            if (this.ws !== socket) return;
            addBreadcrumb('socket', `close ${event.code}`);
            this.ws = null;
            if (event.code === 1008) {
                // The ticket is invalid or tokens were revoked (password change, logout on all devices)
                this.handleAuthExpired();
                return;
            }
            // 1000 — normal close (the client itself closes the socket this way in closeSocket): no need to reconnect.
            if (this.currentToken && event.code !== 1000) {
                this.scheduleReconnect(RECONNECT_DELAY_MS);
            }
        };

        socket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    private scheduleReconnect(delayMs: number) {
        if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            if (this.currentToken) {
                this.connect(this.currentToken);
            }
        }, delayMs);
    }

    private handleAuthExpired() {
        // The token expired or was revoked — clear it and notify the app. The UI logs out via clearToken()
        // (onTokenChange subscription in App.tsx); the regence-auth-expired event is listened to only by tests.
        this.currentToken = null;
        this.pendingMessages = [];
        clearToken();
        window.dispatchEvent(new Event('regence-auth-expired'));
    }

    private closeSocket() {
        if (this.ws) {
            try {
                this.ws.close(1000);
            } catch {
                // ignore
            }
            this.ws = null;
        }
    }

    /** Subscribe to a server event by name ('*' — to all); subscribing again with the same function is not duplicated. */
    on(event: string, callback: EventCallback) {
        if (!this.listeners[event]) {
            this.listeners[event] = [];
        }
        if (!this.listeners[event].includes(callback)) {
            this.listeners[event].push(callback);
        }
    }

    off(event: string, callback: EventCallback) {
        if (!this.listeners[event]) return;
        this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    }

    /**
     * Send an action {action, ...payload}. Without an open connection the message waits in the queue and is sent after
     * connecting (the connection is started right here); if the player is not logged in, the message is lost with a console entry.
     */
    send(action: string, payload: any = {}) {
        const serialized = JSON.stringify({action, ...payload});

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(serialized);
            return;
        }

        const fallbackToken = this.currentToken || getToken();
        if (fallbackToken) {
            this.pendingMessages.push(serialized);
            this.connect(fallbackToken);
        } else {
            console.error('Cannot send a message: the user is not logged in');
        }
    }

    /** Close the connection for good (player logout): the message queue and the scheduled reconnect are dropped. */
    disconnect() {
        this.currentToken = null;
        this.pendingMessages = [];
        this.attempt += 1;  // cancels the ticket request if it is still in flight
        this.connecting = false;
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        this.closeSocket();
    }
}

/** The single instance per tab: used by the board and its hooks, the header and direct messages, Fischer chess. */
export const gameSocket = new GameWebSocketService();
