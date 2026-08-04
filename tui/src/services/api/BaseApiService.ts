import { appConfig } from '../../config/appConfig';

export interface ApiErrorOptions {
  status?: number;

  code?: string;
}

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
  timeout?: number;
}

const DEFAULT_JSON_HEADERS: Record<string, string> = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

export abstract class BaseApiService {
  constructor(protected readonly base?: string) {}

  protected resolveUrl(path: string): string {
    const base = (this.base ?? appConfig.backendUrl).replace(/\/+$/, '');
    return `${base}${path.startsWith('/') ? path : `/${path}`}`;
  }

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
