/**
 * Base API service — the shared abstraction for every REST-backed service in
 * the frontend.
 *
 * Provides a consistent request methodology (URL building against the
 * centralized `appConfig`, JSON headers, optional timeout, JSON serialization,
 * and normalized error handling) so derived services only declare their
 * endpoints and payload types.
 *
 * ```ts
 * class TodoApi extends BaseApiService {
 *   list() { return this.get<Todo[]>('/todos'); }
 *   create(todo: Todo) { return this.post<Todo>('/todos', todo); }
 * }
 * ```
 *
 * WebSocket/JSON-RPC traffic is intentionally out of scope — it uses the
 * dedicated `WebSocketClient` transport.
 */

import { appConfig } from '../../config/appConfig';

export interface ApiErrorOptions {
  /** HTTP status code, when the backend responded. */
  status?: number;
  /** Machine-readable code for network / protocol failures. */
  code?: string;
}

/** Normalized error thrown by every `BaseApiService` request. */
export class ApiError extends Error {
  readonly status?: number;
  readonly code?: string;

  constructor(message: string, options: ApiErrorOptions = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = options.status;
    this.code = options.code;
  }
}

export interface RequestOptions extends RequestInit {
  /** Per-request timeout in milliseconds. Overrides the app default. */
  timeout?: number;
}

const DEFAULT_JSON_HEADERS: Record<string, string> = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

export abstract class BaseApiService {
  /** Optional per-instance base override; defaults to `appConfig.backendUrl`. */
  constructor(protected readonly base?: string) {}

  /** Resolve an API path against this service's base URL. */
  protected resolveUrl(path: string): string {
    const base = (this.base ?? appConfig.backendUrl).replace(/\/+$/, '');
    return `${base}${path.startsWith('/') ? path : `/${path}`}`;
  }

  /** Core request pipeline: URL resolution, headers, timeout, error handling. */
  protected async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { timeout, headers, ...init } = options;
    const signal = timeout ? AbortSignal.timeout(timeout) : undefined;

    let res: Response;
    try {
      res = await fetch(this.resolveUrl(path), {
        ...init,
        headers: { ...DEFAULT_JSON_HEADERS, ...(headers as Record<string, string> | undefined) },
        signal,
      });
    } catch (err) {
      throw new ApiError(err instanceof Error ? err.message : 'Network error', { code: 'network' });
    }

    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new ApiError(`Backend error ${res.status}: ${text || res.statusText}`, { status: res.status });
    }

    if (res.status === 204) return undefined as T;
    return res.json() as Promise<T>;
  }

  protected get<T>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, { ...options, method: 'GET' });
  }

  protected post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  protected put<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: 'PUT',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  protected patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: 'PATCH',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  protected delete<T>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, { ...options, method: 'DELETE' });
  }
}
