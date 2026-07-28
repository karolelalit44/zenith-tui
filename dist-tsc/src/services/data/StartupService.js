import { requireInt } from '../../config/env';
import { providerRepository } from '../providers/ProviderRepository';
const BACKEND_BASE = process.env.VITE_BACKEND_URL || 'http://localhost:8765';
const VALIDATION_TIMEOUT = requireInt('ZENITH_VALIDATION_TIMEOUT') * 1000 + 5000;
function backendUrl(path) {
    return `${BACKEND_BASE.replace(/\/+$/, '')}${path}`;
}
async function fetchJson(url, options) {
    const res = await fetch(url, {
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(VALIDATION_TIMEOUT),
        ...options,
    });
    if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(`Backend error ${res.status}: ${text || res.statusText}`);
    }
    return res.json();
}
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
    async initialize() {
        this._state = { phase: 'loading', result: null, error: null };
        this._notify();
        try {
            const result = await fetchJson(backendUrl('/startup/validate'));
            await providerRepository.refreshFromBackend();
            this._state = { phase: result.status === 'ready' ? 'ready' : 'setup', result, error: null };
        }
        catch (err) {
            const message = err instanceof Error ? err.message : 'Unknown error';
            this._state = {
                phase: 'error',
                result: null,
                error: message.includes('fetch') || message.includes('NetworkError')
                    ? 'Cannot connect to backend. Run: zenith serve'
                    : message,
            };
        }
        this._notify();
        return this._state;
    }
    async validateProvider(request) {
        try {
            return await fetchJson(backendUrl('/startup/validate-provider'), {
                method: 'POST',
                body: JSON.stringify(request),
            });
        }
        catch (err) {
            const message = err instanceof Error ? err.message : 'Unknown error';
            return { valid: false, provider: request.provider, model: request.model, message };
        }
    }
    async saveProviderConfig(request) {
        try {
            return await fetchJson(backendUrl('/startup/save-config'), {
                method: 'POST',
                body: JSON.stringify(request),
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
