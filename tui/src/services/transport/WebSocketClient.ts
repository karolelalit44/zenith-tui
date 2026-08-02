import { EventEmitter } from 'node:events';
import { createRequire } from 'node:module';
import { requireInt } from '../../config/env';

if (typeof WebSocket === 'undefined') {
  try {
    const _require = createRequire(import.meta.url);
    (globalThis as any).WebSocket = _require('ws');
  } catch {
    throw new Error('WebSocket not available. Install ws package or use Node.js 21+.');
  }
}

export type WsStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

interface JsonRpcRequest {
  jsonrpc: '2.0';
  id: string;
  method: string;
  params?: Record<string, unknown>;
}

interface JsonRpcResponse {
  jsonrpc: '2.0';
  id: string;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

export interface JsonRpcEvent {
  jsonrpc: '2.0';
  method: 'event';
  params: {
    kind: string;
    id: string;
    session_id?: string;
    timestamp?: number;
    data: Record<string, unknown>;
  };
}

export interface SessionSummary {
  id: string;
  title: string;
  state: string;
  mode: string;
  message_count: number;
  total_tokens: number;
  created_at: string;
  updated_at: string;
}

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = requireInt('ZENITH_WS_MAX_RECONNECT');
  private reconnectDelay = requireInt('ZENITH_WS_RECONNECT_DELAY');
  private pendingRequests = new Map<string, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
  private requestIdCounter = 0;
  private emitter = new EventEmitter();
  private _status: WsStatus = 'disconnected';
  private rpcTimeout = requireInt('ZENITH_WS_RPC_TIMEOUT');
  private _connectedAt: number = 0;

  constructor(url?: string) {
    this.url = url || WebSocketClient.detectBackendUrl();
  }

  private static detectBackendUrl(): string {
    const base = typeof process !== 'undefined' ? process.env?.ZENITH_BACKEND_URL : undefined;
    if (!base) return 'ws://127.0.0.1:8765/ws';
    // ZENITH_BACKEND_URL is an HTTP base (shared with the REST client), so map
    // the scheme to ws/wss and append the /ws path unless it is already there.
    const ws = base
      .replace(/^http:/i, 'ws:')
      .replace(/^https:/i, 'wss:')
      .replace(/\/+$/, '');
    return /\/ws$/.test(ws) ? ws : `${ws}/ws`;
  }

  get status(): WsStatus {
    return this._status;
  }

  onEvent(callback: (event: JsonRpcEvent) => void): () => void {
    this.emitter.on('event', callback);
    return () => {
      this.emitter.off('event', callback);
    };
  }

  onStatusChange(callback: (status: WsStatus) => void): () => void {
    this.emitter.on('status', callback);
    return () => {
      this.emitter.off('status', callback);
    };
  }

  async connect(): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN) return;

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
            const data = JSON.parse(event.data as string);
            this.handleMessage(data);
          } catch {
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
          const errEvt = evt as { message?: string; error?: { message?: string } };
          const msg = errEvt.message || errEvt.error?.message || `Failed to connect to ${this.url}`;
          reject(new Error(msg));
        };
      } catch (err) {
        this.setStatus('disconnected');
        reject(err);
      }
    });
  }

  async send<T = unknown>(method: string, params?: Record<string, unknown>): Promise<T> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      await this.connect();
    }

    const id = `rpc_${++this.requestIdCounter}`;
    const request: JsonRpcRequest = {
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
        resolve: (v: unknown) => {
          clearTimeout(timeout);
          resolve(v as T);
        },
        reject: (e: Error) => {
          clearTimeout(timeout);
          reject(e);
        },
      });

      this.ws!.send(JSON.stringify(request));
    });
  }

  // ── Session RPC methods ──────────────────────────────────────────

  createSession(title?: string): Promise<{ id: string; title: string }> {
    return this.send('session.create', { title });
  }

  listActiveSessions(): Promise<SessionSummary[]> {
    return this.send('session.list');
  }

  listAllSessions(params?: {
    limit?: number;
    offset?: number;
    include_archived?: boolean;
    search?: string;
    state_filter?: string;
  }): Promise<SessionSummary[]> {
    return this.send('session.list_all', params || {});
  }

  listSessionSummaries(params?: { limit?: number; include_archived?: boolean }): Promise<SessionSummary[]> {
    return this.send('session.summaries', params || {});
  }

  resumeSession(
    sessionId: string,
    sinceSequence?: number,
  ): Promise<{
    session: Record<string, unknown>;
    messages: Record<string, unknown>[];
    events_replayed: number;
    sync_events: Record<string, unknown>[];
    latest_sequence: number;
  }> {
    return this.send('session.resume', { session_id: sessionId, since_sequence: sinceSequence ?? 0 });
  }

  updateSession(params: {
    session_id?: string;
    title?: string;
    context_used?: number;
    context_window?: number;
    tokens?: number;
    cost?: number;
  }): Promise<Record<string, unknown>> {
    return this.send('session.update', params);
  }

  pauseSession(sessionId: string): Promise<Record<string, unknown>> {
    return this.send('session.pause', { session_id: sessionId });
  }

  archiveSession(sessionId: string): Promise<Record<string, unknown>> {
    return this.send('session.archive', { session_id: sessionId });
  }

  deleteSession(sessionId: string): Promise<{ status: string }> {
    return this.send('session.delete', { session_id: sessionId });
  }

  checkpointSession(sessionId: string): Promise<{ checkpoint_id: string }> {
    return this.send('session.checkpoint', { session_id: sessionId });
  }

  duplicateSession(sessionId: string, title?: string): Promise<Record<string, unknown>> {
    return this.send('session.duplicate', { session_id: sessionId, title });
  }

  restoreSession(sessionId: string): Promise<Record<string, unknown>> {
    return this.send('session.restore', { session_id: sessionId });
  }

  getSyncEvents(
    sessionId: string,
    sinceSequence?: number,
  ): Promise<{
    events: Record<string, unknown>[];
    latest_sequence: number;
  }> {
    return this.send('session.sync', { session_id: sessionId, since_sequence: sinceSequence ?? 0 });
  }

  // ── Prompt RPC methods ──────────────────────────────────────────

  sendPrompt(
    content: string,
    mode: string = 'build',
    sessionId?: string,
    provider?: string,
  ): Promise<{ session_id: string; status: string }> {
    return this.send('prompt.send', { content, mode, session_id: sessionId, provider });
  }

  sendConfirmation(confirmationId: string, approved: boolean): Promise<void> {
    return this.send('confirmation.response', { confirmation_id: confirmationId, approved }) as Promise<void>;
  }

  contextCompact(sessionId: string): Promise<{ summary: string; cleared: number }> {
    return this.send('context.compact', { session_id: sessionId });
  }

  contextClearTools(sessionId: string): Promise<{ removed: number; rows: number; stripped: number }> {
    return this.send('context.clear_tools', { session_id: sessionId });
  }

  // ── Internal ────────────────────────────────────────────────────

  private handleMessage(data: JsonRpcResponse | JsonRpcEvent): void {
    if ('method' in data && data.method === 'event') {
      this.emitter.emit('event', data as JsonRpcEvent);
      return;
    }

    if ('id' in data && data.id) {
      const pending = this.pendingRequests.get(String(data.id));
      if (pending) {
        this.pendingRequests.delete(String(data.id));
        if (data.error) {
          pending.reject(new Error(data.error.message));
        } else {
          pending.resolve(data.result);
        }
      }
    }
  }

  private setStatus(status: WsStatus): void {
    this._status = status;
    this.emitter.emit('status', status);
  }

  private reconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;

    this.reconnectAttempts++;
    this.setStatus('reconnecting');

    const base = this.reconnectDelay * 2 ** (this.reconnectAttempts - 1);
    const jitter = Math.random() * this.reconnectDelay;
    const delay = Math.min(base + jitter, 30_000);
    this.url = WebSocketClient.detectBackendUrl();
    setTimeout(() => {
      this.connect().catch(() => {});
    }, delay);
  }
}

export const wsClient = new WebSocketClient();
