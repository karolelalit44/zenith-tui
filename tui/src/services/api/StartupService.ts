import { appConfig } from '../../config/appConfig';
import type { AppStartupState, StartupResult } from '../../types/startup';
import { providerRepository } from '../providers/ProviderRepository';
import { ApiError, BaseApiService } from './BaseApiService';

const {
  connectRetries: CONNECT_RETRIES,
  initialDelayMs: CONNECT_INITIAL_DELAY_MS,
  maxDelayMs: CONNECT_MAX_DELAY_MS,
} = appConfig.startup;

export class StartupService extends BaseApiService {
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
      } catch {}
    }
  }

  private isConnectionError(err: unknown): boolean {
    if (err instanceof ApiError && err.code === 'network') return true;
    if (err instanceof TypeError && err.message === 'Failed to fetch') return true;
    if (err instanceof Error) {
      const m = err.message;
      return (
        m.includes('NetworkError') || m.includes('network') || m.includes('ECONNREFUSED') || m.includes('fetch failed')
      );
    }
    return false;
  }

  private isBackendNotReady(err: unknown): boolean {
    return err instanceof Error && err.message.startsWith('Backend error 426');
  }

  private async probe(): Promise<StartupResult | null> {
    for (let attempt = 0; attempt <= CONNECT_RETRIES; attempt++) {
      try {
        return await this.get<StartupResult>('/startup/validate');
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Unknown error';
        if ((this.isConnectionError(err) || this.isBackendNotReady(err)) && attempt < CONNECT_RETRIES) {
          const delay = Math.min(CONNECT_INITIAL_DELAY_MS * (attempt + 1), CONNECT_MAX_DELAY_MS);
          await new Promise((resolve) => setTimeout(resolve, delay));
          continue;
        }
        this._state = {
          phase: 'error',
          result: null,
          error: this.isConnectionError(err) ? 'Cannot connect to backend. Run: zenith serve' : message,
        };
        this._notify();
        return null;
      }
    }
    return null;
  }

  async initialize(): Promise<AppStartupState> {
    this._state = { phase: 'loading', result: null, error: null };
    this._notify();

    const result = await this.probe();
    if (!result) return this._state;

    try {
      await providerRepository.refreshFromBackend();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      this._state = { phase: 'error', result: null, error: message };
      this._notify();
      return this._state;
    }

    this._state = { phase: result.status === 'ready' ? 'ready' : 'setup', result, error: null };
    this._notify();
    return this._state;
  }
}

export const startupService = new StartupService();
