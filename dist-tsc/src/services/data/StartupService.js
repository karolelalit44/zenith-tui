import { requireInt } from '../../config/env';
import { providerRepository } from '../providers/ProviderRepository';
import { fetchJson } from './fetchJson';
const VALIDATION_TIMEOUT = requireInt('ZENITH_VALIDATION_TIMEOUT') * 1000 + 5000;
export class StartupService {
    _state = {
        phase: 'loading',
        result: null,
        error: null,
    };
    _listeners = new Set();
    get state() {
        return this._state;
    }
    subscribe(fn) {
        this._listeners.add(fn);
        return () => this._listeners.delete(fn);
    }
    reset() {
        this._state = { phase: 'loading', result: null, error: null };
    }
    _notify() {
        for (const fn of this._listeners) {
            try {
                fn(this._state);
            }
            catch {
                /* ignore */
            }
        }
    }
    isConnectionError(err) {
        if (err instanceof TypeError && err.message === 'Failed to fetch')
            return true;
        if (err instanceof Error) {
            const m = err.message;
            return (m.includes('NetworkError') || m.includes('network') || m.includes('ECONNREFUSED') || m.includes('fetch failed'));
        }
        return false;
    }
    async initialize() {
        this._state = { phase: 'loading', result: null, error: null };
        this._notify();
        try {
            const result = await fetchJson('/startup/validate');
            await providerRepository.refreshFromBackend();
            this._state = { phase: result.status === 'ready' ? 'ready' : 'setup', result, error: null };
        }
        catch (err) {
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
    async validateProvider(request) {
        try {
            return await fetchJson('/startup/validate-provider', {
                method: 'POST',
                body: JSON.stringify(request),
                timeout: VALIDATION_TIMEOUT,
            });
        }
        catch (err) {
            const message = err instanceof Error ? err.message : 'Unknown error';
            return { valid: false, provider: request.provider, model: request.model, message };
        }
    }
    async saveProviderConfig(request) {
        try {
            return await fetchJson('/startup/save-config', {
                method: 'POST',
                body: JSON.stringify(request),
                timeout: VALIDATION_TIMEOUT,
            });
        }
        catch (err) {
            const message = err instanceof Error ? err.message : 'Unknown error';
            return { valid: false, provider: request.provider, model: request.model, message };
        }
    }
    async revalidateAfterSetup() {
        return this.initialize();
    }
}
export const startupService = new StartupService();
