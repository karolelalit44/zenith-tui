import { providerRepository } from './ProviderRepository';
export class ProviderService {
    repo;
    listeners = new Set();
    constructor(repo = providerRepository) {
        this.repo = repo;
    }
    async refreshFromBackend() {
        await this.repo.refreshFromBackend();
        const active = this.getActiveProvider();
        this.notifyListeners(active);
        return active;
    }
    getActiveProviderId() {
        return this.repo.getActiveProviderId();
    }
    getActiveProvider() {
        const id = this.getActiveProviderId();
        return this.getProviderState(id);
    }
    getProviderState(id) {
        const meta = this.repo.getProviderMeta(id);
        const config = this.repo.getProviderConfig(id);
        const activeId = this.getActiveProviderId();
        return {
            id,
            meta,
            config,
            isActive: id === activeId,
            isConfigured: this.validateConfig(id, config).valid,
        };
    }
    getAllProviders() {
        const ids = ['nvidia', 'openrouter', 'openai', 'anthropic', 'google', 'groq', 'custom'];
        return ids.map((id) => this.getProviderState(id));
    }
    setActiveProvider(id) {
        const meta = this.repo.getProviderMeta(id);
        if (!meta) {
            throw new Error(`Unknown provider ID: ${id}`);
        }
        this.repo.setActiveProviderId(id);
        const updatedState = this.getProviderState(id);
        this.notifyListeners(updatedState);
        return updatedState;
    }
    updateConfig(id, updates) {
        const meta = this.repo.getProviderMeta(id);
        if (!meta) {
            throw new Error(`Unknown provider ID: ${id}`);
        }
        this.repo.updateProviderConfig(id, updates);
        const updatedState = this.getProviderState(id);
        this.notifyListeners(this.getActiveProvider());
        return updatedState;
    }
    validateConfig(id, configOverride) {
        const meta = this.repo.getProviderMeta(id);
        if (!meta)
            return { valid: false, error: 'Unknown provider' };
        const config = configOverride || this.repo.getProviderConfig(id);
        if (id === 'custom') {
            if (!config.baseUrl || typeof config.baseUrl !== 'string' || !config.baseUrl.trim()) {
                return { valid: false, error: 'Base endpoint URL is required' };
            }
            return { valid: true };
        }
        // Standard API key providers
        if (!config.apiKey || typeof config.apiKey !== 'string' || !config.apiKey.trim()) {
            return { valid: false, error: 'API Key is required' };
        }
        return { valid: true };
    }
    subscribe(listener) {
        this.listeners.add(listener);
        return () => {
            this.listeners.delete(listener);
        };
    }
    notifyListeners(state) {
        this.listeners.forEach((listener) => {
            try {
                listener(state);
            }
            catch (_err) {
                // Ignore listener exceptions
            }
        });
    }
}
export const providerService = new ProviderService();
