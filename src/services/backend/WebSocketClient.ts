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

type WsStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

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

  constructor(url?: string) {
    this.url = url || this.detectBackendUrl();
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

  createSession(title?: string): Promise<{ id: string; title: string }> {
    return this.send('session.create', { title });
  }

  sendPrompt(
    content: string,
    mode: string = 'build',
    sessionId?: string,
  ): Promise<{ session_id: string; status: string }> {
    return this.send('prompt.send', { content, mode, session_id: sessionId });
  }

  sendConfirmation(confirmationId: string, approved: boolean): Promise<void> {
    return this.send('confirmation.response', { confirmation_id: confirmationId, approved }) as Promise<void>;
  }

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

    const delay = this.reconnectDelay * 2 ** (this.reconnectAttempts - 1);
    setTimeout(() => {
      this.connect().catch(() => {});
    }, delay);
  }

  private detectBackendUrl(): string {
    if (typeof process !== 'undefined' && process.env?.ZENITH_BACKEND_URL) {
      return process.env.ZENITH_BACKEND_URL;
    }
    return 'ws://localhost:8765/ws';
  }
}

export const wsClient = new WebSocketClient();
