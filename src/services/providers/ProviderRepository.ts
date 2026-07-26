import catalogData from '../../../zenith/config/provider_catalog.json';
import { requireEnv, requireFloat, requireInt } from '../../config/env';
import type { ProviderConfig, ProviderId, ProviderMeta } from './types';

const catalog = catalogData as {
  default_active_provider: string;
  providers: Record<
    string,
    {
      id: string;
      name: string;
      description?: string;
      default_model: string;
      swatch?: string[];
      models?: Array<{
        id: string;
        name: string;
        description?: string;
        context_window?: number;
        parameters?: string;
        architecture?: string;
        input_modalities?: string[];
        output_modalities?: string[];
        tags?: string[];
        model_capabilities?: {
          function_calling?: boolean;
          structured_output?: boolean;
          reasoning?: boolean;
          thinking?: boolean;
        };
        speed_tier?: string;
        best_for?: string[];
        is_default?: number;
      }>;
      config_fields?: Array<{
        key: string;
        label: string;
        type: string;
        required?: boolean;
        placeholder?: string;
        defaultValue?: string | number;
      }>;
    }
  >;
};

const BACKEND_BASE = requireEnv('VITE_BACKEND_URL');
const BACKEND_FETCH_TIMEOUT = requireInt('VITE_BACKEND_FETCH_TIMEOUT');
const DEFAULT_MAX_TOKENS = requireInt('VITE_DEFAULT_MAX_TOKENS');
const DEFAULT_TEMPERATURE = requireFloat('VITE_DEFAULT_TEMPERATURE');
const FALLBACK_MAX_TOKENS = requireInt('VITE_FALLBACK_MAX_TOKENS');

function backendUrl(path: string): string {
  return `${BACKEND_BASE.replace(/\/+$/, '')}${path}`;
}

interface BackendProviderModel {
  id: string;
  name: string;
  description?: string;
  context_window?: number;
  parameters?: string;
  architecture?: string;
  input_modalities?: string[];
  output_modalities?: string[];
  tags?: string[];
  model_capabilities?: {
    function_calling?: boolean;
    structured_output?: boolean;
    reasoning?: boolean;
    thinking?: boolean;
  };
  speed_tier?: string;
  best_for?: string[];
  is_default?: number;
}

interface BackendProviderEntry {
  id?: string;
  name?: string;
  description?: string;
  api_key?: string;
  model?: string;
  base_url?: string;
  max_tokens?: number;
  temperature?: number;
  is_active?: boolean;
  swatch?: string[];
  models?: BackendProviderModel[];
}

interface BackendProvidersResponse {
  active_provider: string;
  providers: Record<string, BackendProviderEntry>;
}

const DEFAULT_METAS: Record<ProviderId, ProviderMeta> = Object.fromEntries(
  Object.entries(catalog.providers).map(([pid, p]) => [
    pid,
    {
      id: pid as ProviderId,
      name: p.name,
      description: p.description || '',
      defaultModel: p.default_model,
      swatch: p.swatch || [],
      availableModels: (p.models || []).map((m) => ({
        id: m.id,
        name: m.name,
        description: m.description,
        context_window: m.context_window,
        parameters: m.parameters,
        architecture: m.architecture,
        input_modalities: m.input_modalities,
        output_modalities: m.output_modalities,
        tags: m.tags,
        model_capabilities: m.model_capabilities,
        speed_tier: m.speed_tier as 'fast' | 'moderate' | 'slow' | undefined,
        best_for: m.best_for,
      })),
      fields: (p.config_fields || []).map((f) => ({
        key: f.key,
        label: f.label,
        type: f.type as 'password' | 'text' | 'number',
        required: f.required,
        placeholder: f.placeholder,
        defaultValue: f.defaultValue,
      })),
    },
  ]),
) as Record<ProviderId, ProviderMeta>;

export class ProviderRepository {
  private _backendCache: BackendProvidersResponse | null = null;
  private _localActiveProviderId: ProviderId | null = null;
  private _localConfigOverrides: Partial<ProviderConfig> | null = null;

  public getProviderMeta(id: ProviderId): ProviderMeta {
    const meta = DEFAULT_METAS[id];
    if (!meta) throw new Error(`Unknown provider: ${id}`);
    if (this._backendCache?.providers?.[id]) {
      const backend = this._backendCache.providers[id];
      if (backend.models && backend.models.length > 0) {
        return {
          ...meta,
          availableModels: backend.models.map((m) => ({
            id: m.id,
            name: m.name,
            description: m.description,
            context_window: m.context_window,
            parameters: m.parameters,
            architecture: m.architecture,
            input_modalities: m.input_modalities,
            output_modalities: m.output_modalities,
            tags: m.tags,
            model_capabilities: m.model_capabilities,
            speed_tier: m.speed_tier as 'fast' | 'moderate' | 'slow' | undefined,
            best_for: m.best_for,
          })),
        };
      }
    }
    return meta;
  }

  public async refreshFromBackend(): Promise<BackendProvidersResponse | null> {
    try {
      const res = await fetch(backendUrl('/startup/provider-config'), {
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(BACKEND_FETCH_TIMEOUT),
      });
      if (res.ok) {
        const data = (await res.json()) as BackendProvidersResponse;
        this._backendCache = data;
        return data;
      }
    } catch {
      // Backend unreachable
    }
    return null;
  }

  public getActiveProviderId(): ProviderId {
    if (this._localActiveProviderId && DEFAULT_METAS[this._localActiveProviderId]) {
      return this._localActiveProviderId;
    }
    if (this._backendCache?.active_provider) {
      const id = this._backendCache.active_provider as ProviderId;
      if (DEFAULT_METAS[id]) return id;
    }
    return catalog.default_active_provider as ProviderId;
  }

  public setActiveProviderId(id: ProviderId): void {
    if (!DEFAULT_METAS[id]) throw new Error(`Unknown provider: ${id}`);

    this._localActiveProviderId = id;
    const meta = this.getProviderMeta(id);
    const currentConfig = this.getProviderConfig(id);
    const activeModel = currentConfig.model || meta.defaultModel;

    fetch(backendUrl('/startup/save-config'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        provider: id,
        api_key: currentConfig.apiKey || '',
        model: activeModel,
        base_url: currentConfig.baseUrl || '',
        max_tokens: currentConfig.timeout || DEFAULT_MAX_TOKENS,
        temperature: currentConfig.temperature ?? DEFAULT_TEMPERATURE,
      }),
      signal: AbortSignal.timeout(BACKEND_FETCH_TIMEOUT),
    })
      .then(() => this.refreshFromBackend())
      .catch(() => {});
  }

  public getProviderConfig(id: ProviderId): ProviderConfig {
    const meta = this.getProviderMeta(id);

    const base: ProviderConfig = this._backendCache?.providers?.[id]
      ? {
          model: this._backendCache.providers[id].model || meta.defaultModel,
          apiKey: this._backendCache.providers[id].api_key || '',
          baseUrl:
            this._backendCache.providers[id].base_url ||
            (meta.fields?.find((f) => f.key === 'baseUrl')?.defaultValue as string) ||
            '',
          organizationId: '',
          timeout: this._backendCache.providers[id].max_tokens ?? FALLBACK_MAX_TOKENS,
          temperature: this._backendCache.providers[id].temperature ?? DEFAULT_TEMPERATURE,
        }
      : {
          model: meta.defaultModel,
          apiKey: '',
          baseUrl: (meta.fields?.find((f) => f.key === 'baseUrl')?.defaultValue as string) || '',
          organizationId: '',
          timeout: FALLBACK_MAX_TOKENS,
          temperature: DEFAULT_TEMPERATURE,
        };

    return this._localConfigOverrides ? { ...base, ...this._localConfigOverrides } : base;
  }

  public updateProviderConfig(id: ProviderId, updates: Partial<ProviderConfig>): ProviderConfig {
    const existing = this.getProviderConfig(id);
    const updatedConfig: ProviderConfig = { ...existing, ...updates };

    this._localConfigOverrides = { ...this._localConfigOverrides, ...updates };

    fetch(backendUrl('/startup/save-config'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        provider: id,
        api_key: updatedConfig.apiKey || '',
        model: updatedConfig.model || '',
        base_url: updatedConfig.baseUrl || '',
        max_tokens: updatedConfig.timeout || FALLBACK_MAX_TOKENS,
        temperature: updatedConfig.temperature ?? DEFAULT_TEMPERATURE,
      }),
      signal: AbortSignal.timeout(BACKEND_FETCH_TIMEOUT),
    })
      .then(() => this.refreshFromBackend())
      .catch(() => {});

    return updatedConfig;
  }
}

export const providerRepository = new ProviderRepository();
