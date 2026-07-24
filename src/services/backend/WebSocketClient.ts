import { EventEmitter } from 'node:events';
import { createRequire } from 'node:module';

if (typeof WebSocket === 'undefined') {
  try {
    const _require = createRequire(import.meta.url);
    (globalThis as any).WebSocket = _require('ws');
  } catch {
    throw new Error('WebSocket not available. Install ws package or use Node.js 21+.');
  }
}

export type WsStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting';

export interface JsonRpcRequest {
  jsonrpc: '2.0';
  id: string;
  method: string;
  params?: Record<string, unknown>;
}

export interface JsonRpcResponse {
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
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private pendingRequests = new Map<string, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
  private requestIdCounter = 0;
  private emitter = new EventEmitter();
  private _status: WsStatus = 'disconnected';
  private _sessionId: string | null = null;
  private artificialLatency = 800;

  constructor(url?: string) {
    this.url = url || this.detectBackendUrl();
  }

  get status(): WsStatus {
    return this._status;
  }

  get sessionId(): string | null {
    return this._sessionId;
  }

  get latency(): number {
    return this.artificialLatency;
  }

  setLatency(ms: number): void {
    this.artificialLatency = ms;
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
          const msg = (evt as any).message || (evt as any).error?.message || `Failed to connect to ${this.url}`;
          reject(new Error(msg));
        };
      } catch (err) {
        this.setStatus('disconnected');
        reject(err);
      }
    });
  }

  disconnect(): void {
    this.reconnectAttempts = this.maxReconnectAttempts;
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.setStatus('disconnected');
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
      }, 60000);

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

  listSessions(): Promise<Array<{ id: string; title: string; created_at: string }>> {
    return this.send('session.list');
  }

  resumeSession(sessionId: string): Promise<{ session: Record<string, unknown>; messages: unknown[] }> {
    return this.send('session.resume', { session_id: sessionId });
  }

  sendPrompt(
    content: string,
    mode: string = 'build',
    sessionId?: string,
  ): Promise<{ session_id: string; status: string }> {
    return this.send('prompt.send', { content, mode, session_id: sessionId });
  }

  validateProvider(provider?: string): Promise<{ valid: boolean; error?: string }> {
    return this.send('provider.validate', { provider });
  }

  listModels(provider?: string): Promise<{ models: string[] }> {
    return this.send('provider.models', { provider });
  }

  listTools(mode?: string): Promise<{ tools: unknown[] }> {
    return this.send('tools.list', { mode });
  }

  workspaceStatus(): Promise<Record<string, unknown>> {
    return this.send('workspace.status');
  }

  health(): Promise<{ status: string }> {
    return this.send('health');
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
