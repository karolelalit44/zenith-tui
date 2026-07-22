import { PROVIDER_CATALOG } from './ProviderCatalog';
import { ProviderRepository, providerRepository } from './ProviderRepository';
import type { ProviderConfig, ProviderId, ProviderState } from './types';

export type ProviderListener = (activeProvider: ProviderState) => void;

export class ProviderService {
  private repo: ProviderRepository;
  private listeners: Set<ProviderListener> = new Set();

  constructor(repo: ProviderRepository = providerRepository) {
    this.repo = repo;
  }

  public getActiveProviderId(): ProviderId {
    return this.repo.getActiveProviderId();
  }

  public getActiveProvider(): ProviderState {
    const id = this.getActiveProviderId();
    return this.getProviderState(id);
  }

  public getProviderState(id: ProviderId): ProviderState {
    const meta = PROVIDER_CATALOG[id];
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

  public getAllProviders(): ProviderState[] {
    const ids: ProviderId[] = ['openrouter', 'openai', 'anthropic', 'gemini', 'groq', 'custom'];
    return ids.map((id) => this.getProviderState(id));
  }

  public setActiveProvider(id: ProviderId): ProviderState {
    if (!PROVIDER_CATALOG[id]) {
      throw new Error(`Unknown provider ID: ${id}`);
    }

    this.repo.setActiveProviderId(id);
    const updatedState = this.getProviderState(id);
    this.notifyListeners(updatedState);
    return updatedState;
  }

  public updateConfig(id: ProviderId, updates: Partial<ProviderConfig>): ProviderState {
    if (!PROVIDER_CATALOG[id]) {
      throw new Error(`Unknown provider ID: ${id}`);
    }

    this.repo.updateProviderConfig(id, updates);
    const updatedState = this.getProviderState(id);
    this.notifyListeners(this.getActiveProvider());
    return updatedState;
  }

  public validateConfig(id: ProviderId, configOverride?: ProviderConfig): { valid: boolean; error?: string } {
    const meta = PROVIDER_CATALOG[id];
    if (!meta) return { valid: false, error: 'Unknown provider' };

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

  public subscribe(listener: ProviderListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notifyListeners(state: ProviderState): void {
    this.listeners.forEach((listener) => {
      try {
        listener(state);
      } catch (_err) {
        // Ignore listener exceptions
      }
    });
  }
}

export const providerService = new ProviderService();
