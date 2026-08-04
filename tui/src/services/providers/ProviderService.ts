import { ProviderRepository, providerRepository } from './ProviderRepository';
import type { ProviderConfig, ProviderId, ProviderMeta, ProviderState } from './types';

type ProviderListener = (activeProvider: ProviderState) => void;

function emptyMeta(id: ProviderId): ProviderMeta {
  return { id, name: '', description: '', defaultModel: '', fields: [], availableModels: [] };
}

export class ProviderService {
  private repo: ProviderRepository;
  private listeners: Set<ProviderListener> = new Set();

  constructor(repo: ProviderRepository = providerRepository) {
    this.repo = repo;
  }

  public async refreshFromBackend(): Promise<ProviderState> {
    await this.repo.refreshFromBackend();
    const active = this.getActiveProvider();
    this.notifyListeners(active);
    return active;
  }

  public getActiveProviderId(): ProviderId {
    return this.repo.getActiveProviderId();
  }

  public getActiveProvider(): ProviderState {
    const id = this.getActiveProviderId();
    return this.getProviderState(id);
  }

  public getProviderState(id: ProviderId): ProviderState {
    const meta = this.repo.getProviderMeta(id);
    const config = this.repo.getProviderConfig(id);
    const details = this.repo.getProviderStateDetails(id);
    const activeId = this.getActiveProviderId();

    return {
      id,
      meta: meta ?? emptyMeta(id),
      config,
      isActive: id === activeId,
      isConfigured: this.validateConfig(id, config).valid,
      hasApiKey: details.hasApiKey,
      apiKeyMasked: details.apiKeyMasked,
      validationStatus: details.validationStatus,
      lastValidationError: details.lastValidationError,
      isPopular: details.isPopular,
      isCustomFlow: details.isCustomFlow,
      baseUrlStyle: details.baseUrlStyle,
      supportsPromptCaching: details.supportsPromptCaching,
      supportsThinkingHeaders: details.supportsThinkingHeaders,
    };
  }

  public getAllProviders(): ProviderState[] {
    const list = this.repo.getProviderInfoList();
    return list.map((item) => this.getProviderState(item.id));
  }

  public getConnectedIds(): string[] {
    return this.repo.getConnectedIds();
  }

  public notifyChange(): ProviderState {
    const active = this.getActiveProvider();
    this.notifyListeners(active);
    return active;
  }

  public validateConfig(id: ProviderId, configOverride?: ProviderConfig): { valid: boolean; error?: string } {
    const meta = this.repo.getProviderMeta(id);
    if (!meta) return { valid: false, error: 'Unknown provider' };

    const config = configOverride || this.repo.getProviderConfig(id);
    const details = this.repo.getProviderStateDetails(id);

    if (details.isCustomFlow) {
      if (!config.baseUrl || typeof config.baseUrl !== 'string' || !config.baseUrl.trim()) {
        return { valid: false, error: 'Base endpoint URL is required' };
      }
      return { valid: true };
    }

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
      } catch (_err) {}
    });
  }
}

export const providerService = new ProviderService();
