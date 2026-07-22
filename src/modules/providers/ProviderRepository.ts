import { loadUserProfile, saveUserProfile } from '../../services/data/userProfileService';
import { PROVIDER_CATALOG } from './ProviderCatalog';
import type { ProviderConfig, ProviderId } from './types';

export class ProviderRepository {
  public getActiveProviderId(): ProviderId {
    const profile = loadUserProfile();
    const active = profile.activeProvider as ProviderId;
    return active && PROVIDER_CATALOG[active] ? active : 'openai';
  }

  public setActiveProviderId(id: ProviderId): void {
    if (PROVIDER_CATALOG[id]) {
      saveUserProfile({ activeProvider: id });
    }
  }

  public getProviderConfig(id: ProviderId): ProviderConfig {
    const profile = loadUserProfile();
    const settingsMap = (profile.providerSettings as Record<string, ProviderConfig>) || {};
    const stored = settingsMap[id] || {};
    const meta = PROVIDER_CATALOG[id];

    return {
      model: stored.model || meta?.defaultModel || '',
      apiKey: stored.apiKey || '',
      baseUrl: stored.baseUrl || (meta?.fields.find((f) => f.key === 'baseUrl')?.defaultValue as string) || '',
      organizationId: stored.organizationId || '',
      timeout: stored.timeout || (meta?.fields.find((f) => f.key === 'timeout')?.defaultValue as number) || 30000,
      temperature: stored.temperature ?? 0.7,
      ...stored,
    };
  }

  public updateProviderConfig(id: ProviderId, updates: Partial<ProviderConfig>): ProviderConfig {
    const profile = loadUserProfile();
    const settingsMap = (profile.providerSettings as Record<string, ProviderConfig>) || {};
    const existing = settingsMap[id] || {};

    const updatedConfig: ProviderConfig = {
      ...existing,
      ...updates,
    };

    const newSettingsMap = {
      ...settingsMap,
      [id]: updatedConfig,
    };

    saveUserProfile({ providerSettings: newSettingsMap });
    return updatedConfig;
  }

  public getAllProviderConfigs(): Record<ProviderId, ProviderConfig> {
    const keys: ProviderId[] = ['openrouter', 'openai', 'anthropic', 'gemini', 'groq', 'custom'];
    const result: Partial<Record<ProviderId, ProviderConfig>> = {};

    keys.forEach((key) => {
      result[key] = this.getProviderConfig(key);
    });

    return result as Record<ProviderId, ProviderConfig>;
  }
}

export const providerRepository = new ProviderRepository();
