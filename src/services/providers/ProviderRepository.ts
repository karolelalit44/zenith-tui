import { loadUserProfile, saveUserProfile } from '../data/userProfileService';
import anthropicConfig from './anthropic/config.json';
import customConfig from './custom/config.json';
import geminiConfig from './gemini/config.json';
import groqConfig from './groq/config.json';
import openaiConfig from './openai/config.json';
import openrouterConfig from './openrouter/config.json';
import type { ProviderConfig, ProviderId, ProviderMeta } from './types';

const PROVIDER_CONFIG_MAP: Record<ProviderId, ProviderMeta> = {
  openrouter: openrouterConfig as unknown as ProviderMeta,
  openai: openaiConfig as unknown as ProviderMeta,
  anthropic: anthropicConfig as unknown as ProviderMeta,
  gemini: geminiConfig as unknown as ProviderMeta,
  groq: groqConfig as unknown as ProviderMeta,
  custom: customConfig as unknown as ProviderMeta,
};

export class ProviderRepository {
  public getProviderMeta(id: ProviderId): ProviderMeta {
    return PROVIDER_CONFIG_MAP[id] || PROVIDER_CONFIG_MAP.openai;
  }

  public getActiveProviderId(): ProviderId {
    const profile = loadUserProfile();
    const active = (profile.provider?.activeProvider || profile.activeProvider) as ProviderId;
    return active && PROVIDER_CONFIG_MAP[active] ? active : 'openai';
  }

  public setActiveProviderId(id: ProviderId): void {
    if (PROVIDER_CONFIG_MAP[id]) {
      const meta = this.getProviderMeta(id);
      const currentConfig = this.getProviderConfig(id);
      const activeModel = currentConfig.model || meta.defaultModel;

      saveUserProfile({
        activeProvider: id,
        activeModel,
        provider: {
          activeProvider: id,
          activeModel,
        },
      });
    }
  }

  public getProviderConfig(id: ProviderId): ProviderConfig {
    const profile = loadUserProfile();
    const settingsMap = (profile.providerSettings as Record<string, ProviderConfig>) || {};
    const stored = settingsMap[id] || {};
    const meta = this.getProviderMeta(id);

    return {
      model: stored.model || meta.defaultModel || '',
      apiKey: stored.apiKey || '',
      baseUrl: stored.baseUrl || (meta.fields?.find((f) => f.key === 'baseUrl')?.defaultValue as string) || '',
      organizationId: stored.organizationId || '',
      timeout: stored.timeout || (meta.fields?.find((f) => f.key === 'timeout')?.defaultValue as number) || 30000,
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

    const activeId = this.getActiveProviderId();
    const activeModel = id === activeId && updatedConfig.model ? updatedConfig.model : profile.activeModel || 'gpt-4o';

    saveUserProfile({
      activeModel,
      provider: {
        activeProvider: activeId,
        activeModel,
      },
      providerSettings: newSettingsMap,
    });
    return updatedConfig;
  }
}

export const providerRepository = new ProviderRepository();
