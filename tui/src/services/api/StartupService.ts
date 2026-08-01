import { requireInt } from '../../config/env';
import type { AppStartupState, ProviderSetupRequest, ProviderSetupResult, StartupResult } from '../../types/startup';
import { providerRepository } from '../providers/ProviderRepository';
import { fetchJson } from './fetchJson';

const VALIDATION_TIMEOUT = requireInt('ZENITH_VALIDATION_TIMEOUT') * 1000 + 5000;

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

  private isConnectionError(err: unknown): boolean {
    if (err instanceof TypeError && err.message === 'Failed to fetch') return true;
    if (err instanceof Error) {
      const m = err.message;
      return (
        m.includes('NetworkError') || m.includes('network') || m.includes('ECONNREFUSED') || m.includes('fetch failed')
      );
    }
    return false;
  }

  async initialize(): Promise<AppStartupState> {
    this._state = { phase: 'loading', result: null, error: null };
    this._notify();

    try {
      const result = await fetchJson<StartupResult>('/startup/validate');

      await providerRepository.refreshFromBackend();
      this._state = { phase: result.status === 'ready' ? 'ready' : 'setup', result, error: null };
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      this._state = {
        phase: 'error',
        result: null,
        error: this.isConnectionError(err) ? 'Cannot connect to backend. Run: zenith serve' : message,
      };
    }

    this._notify();
    return this._state;
  }

  async validateProvider(request: ProviderSetupRequest): Promise<ProviderSetupResult> {
    try {
      return await fetchJson<ProviderSetupResult>('/startup/validate-provider', {
        method: 'POST',
        body: JSON.stringify(request),
        timeout: VALIDATION_TIMEOUT,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      return { valid: false, provider: request.provider, model: request.model, message };
    }
  }

  async saveProviderConfig(request: ProviderSetupRequest): Promise<ProviderSetupResult> {
    try {
      return await fetchJson<ProviderSetupResult>('/startup/save-config', {
        method: 'POST',
        body: JSON.stringify(request),
        timeout: VALIDATION_TIMEOUT,
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
