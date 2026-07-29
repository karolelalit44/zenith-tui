import { EventEmitter } from 'node:events';
import { createRequire } from 'node:module';
import { requireInt } from '../../config/env';
if (typeof WebSocket === 'undefined') {
    try {
        const _require = createRequire(import.meta.url);
        globalThis.WebSocket = _require('ws');
    }
    catch {
        throw new Error('WebSocket not available. Install ws package or use Node.js 21+.');
    }
}
export class WebSocketClient {
    ws = null;
    url;
    reconnectAttempts = 0;
    maxReconnectAttempts = requireInt('ZENITH_WS_MAX_RECONNECT');
    reconnectDelay = requireInt('ZENITH_WS_RECONNECT_DELAY');
    pendingRequests = new Map();
    requestIdCounter = 0;
    emitter = new EventEmitter();
    _status = 'disconnected';
    rpcTimeout = requireInt('ZENITH_WS_RPC_TIMEOUT');
    _connectedAt = 0;
    constructor(url) {
        this.url = url || WebSocketClient.detectBackendUrl();
    }
    static detectBackendUrl() {
        if (typeof process !== 'undefined' && process.env?.ZENITH_BACKEND_URL) {
            return process.env.ZENITH_BACKEND_URL;
        }
        return 'ws://localhost:8765/ws';
    }
    get status() {
        return this._status;
    }
    onEvent(callback) {
        this.emitter.on('event', callback);
        return () => {
            this.emitter.off('event', callback);
        };
    }
    onStatusChange(callback) {
        this.emitter.on('status', callback);
        return () => {
            this.emitter.off('status', callback);
        };
    }
    async connect() {
        if (this.ws?.readyState === WebSocket.OPEN)
            return;
        this.setStatus('connecting');
        return new Promise((resolve, reject) => {
            try {
                this.ws = new WebSocket(this.url);
                this.ws.onopen = () => {
                    this.reconnectAttempts = 0;
                    this._connectedAt = Date.now();
                    this.setStatus('connected');
                    resolve();
                };
                this.ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        this.handleMessage(data);
                    }
                    catch {
                        // Ignore malformed messages
                    }
                };
                this.ws.onclose = () => {
                    this.setStatus('disconnected');
                    const wasStable = Date.now() - this._connectedAt > 5000;
                    if (wasStable) {
                        this.reconnectAttempts = 0;
                    }
                    this.reconnect();
                };
                this.ws.onerror = (evt) => {
                    this.setStatus('disconnected');
                    const errEvt = evt;
                    const msg = errEvt.message || errEvt.error?.message || `Failed to connect to ${this.url}`;
                    reject(new Error(msg));
                };
            }
            catch (err) {
                this.setStatus('disconnected');
                reject(err);
            }
        });
    }
    async send(method, params) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            await this.connect();
        }
        const id = `rpc_${++this.requestIdCounter}`;
        const request = {
            jsonrpc: '2.0',
            id,
            method,
            params,
        };
        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                this.pendingRequests.delete(id);
                reject(new Error(`RPC timeout: ${method}`));
            }, this.rpcTimeout);
            this.pendingRequests.set(id, {
                resolve: (v) => {
                    clearTimeout(timeout);
                    resolve(v);
                },
                reject: (e) => {
                    clearTimeout(timeout);
                    reject(e);
                },
            });
            this.ws.send(JSON.stringify(request));
        });
    }
    // ── Session RPC methods ──────────────────────────────────────────
    createSession(title) {
        return this.send('session.create', { title });
    }
    listActiveSessions() {
        return this.send('session.list');
    }
    listAllSessions(params) {
        return this.send('session.list_all', params || {});
    }
    listSessionSummaries(params) {
        return this.send('session.summaries', params || {});
    }
    resumeSession(sessionId, sinceSequence) {
        return this.send('session.resume', { session_id: sessionId, since_sequence: sinceSequence ?? 0 });
    }
    updateSession(params) {
        return this.send('session.update', params);
    }
    pauseSession(sessionId) {
        return this.send('session.pause', { session_id: sessionId });
    }
    archiveSession(sessionId) {
        return this.send('session.archive', { session_id: sessionId });
    }
    deleteSession(sessionId) {
        return this.send('session.delete', { session_id: sessionId });
    }
    checkpointSession(sessionId) {
        return this.send('session.checkpoint', { session_id: sessionId });
    }
    duplicateSession(sessionId, title) {
        return this.send('session.duplicate', { session_id: sessionId, title });
    }
    restoreSession(sessionId) {
        return this.send('session.restore', { session_id: sessionId });
    }
    getSyncEvents(sessionId, sinceSequence) {
        return this.send('session.sync', { session_id: sessionId, since_sequence: sinceSequence ?? 0 });
    }
    // ── Prompt RPC methods ──────────────────────────────────────────
    sendPrompt(content, mode = 'build', sessionId, provider) {
        return this.send('prompt.send', { content, mode, session_id: sessionId, provider });
    }
    sendConfirmation(confirmationId, approved) {
        return this.send('confirmation.response', { confirmation_id: confirmationId, approved });
    }
    // ── Internal ────────────────────────────────────────────────────
    handleMessage(data) {
        if ('method' in data && data.method === 'event') {
            this.emitter.emit('event', data);
            return;
        }
        if ('id' in data && data.id) {
            const pending = this.pendingRequests.get(String(data.id));
            if (pending) {
                this.pendingRequests.delete(String(data.id));
                if (data.error) {
                    pending.reject(new Error(data.error.message));
                }
                else {
                    pending.resolve(data.result);
                }
            }
        }
    }
    setStatus(status) {
        this._status = status;
        this.emitter.emit('status', status);
    }
    reconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts)
            return;
        this.reconnectAttempts++;
        this.setStatus('reconnecting');
        const base = this.reconnectDelay * 2 ** (this.reconnectAttempts - 1);
        const jitter = Math.random() * this.reconnectDelay;
        const delay = Math.min(base + jitter, 30_000);
        this.url = WebSocketClient.detectBackendUrl();
        setTimeout(() => {
            this.connect().catch(() => { });
        }, delay);
    }
}
export const wsClient = new WebSocketClient();
