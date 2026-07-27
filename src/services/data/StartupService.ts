import type { AppStartupState, ProviderSetupRequest, ProviderSetupResult, StartupResult } from '../../types/startup';
import { providerRepository } from '../providers/ProviderRepository';
import { requireInt } from '../../config/env';

const BACKEND_BASE = process.env.VITE_BACKEND_URL || 'http://localhost:8765';
const VALIDATION_TIMEOUT = requireInt('ZENITH_VALIDATION_TIMEOUT') * 1000 + 5000;

function backendUrl(path: string): string {
  return `${BACKEND_BASE.replace(/\/+$/, '')}${path}`;
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    signal: AbortSignal.timeout(VALIDATION_TIMEOUT),
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Backend error ${res.status}: ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export class StartupService {
  private _state: AppStartupState = {
    phase: 'loading',
    result: null,
    error: null,
  };

  private _listeners: Set<(state: AppStartupState) => void> = new Set();

  get state(): AppStartupState {
    return this._state;
  }

  subscribe(fn: (state: AppStartupState) => void): () => void {
    this._listeners.add(fn);
    return () => this._listeners.delete(fn);
  }

  reset(): void {
    this._state = { phase: 'loading', result: null, error: null };
  }

  private _notify(): void {
    for (const fn of this._listeners) {
      try {
        fn(this._state);
      } catch {
        /* ignore */
      }
    }
  }

  async initialize(): Promise<AppStartupState> {
    this._state = { phase: 'loading', result: null, error: null };
    this._notify();

    try {
      const result = await fetchJson<StartupResult>(backendUrl('/startup/validate'));

      await providerRepository.refreshFromBackend();
      this._state = { phase: result.status === 'ready' ? 'ready' : 'setup', result, error: null };
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      this._state = {
        phase: 'error',
        result: null,
        error:
          message.includes('fetch') || message.includes('NetworkError')
            ? 'Cannot connect to backend. Run: zenith serve'
            : message,
      };
    }

    this._notify();
    return this._state;
  }

  async validateProvider(request: ProviderSetupRequest): Promise<ProviderSetupResult> {
    try {
      return await fetchJson<ProviderSetupResult>(backendUrl('/startup/validate-provider'), {
        method: 'POST',
        body: JSON.stringify(request),
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      return { valid: false, provider: request.provider, model: request.model, message };
    }
  }

  async saveProviderConfig(request: ProviderSetupRequest): Promise<ProviderSetupResult> {
    try {
      return await fetchJson<ProviderSetupResult>(backendUrl('/startup/save-config'), {
        method: 'POST',
        body: JSON.stringify(request),
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      return { valid: false, provider: request.provider, model: request.model, message };
    }
  }

  async revalidateAfterSetup(): Promise<AppStartupState> {
    return this.initialize();
  }
}

export const startupService = new StartupService();
