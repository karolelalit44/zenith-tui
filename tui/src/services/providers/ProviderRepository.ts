import catalogData from '../../../../server/config/provider_catalog.json';

import type {
  ModelInfo,
  ProviderConfig,
  ProviderId,
  ProviderInfo,
  ProviderListResponse,
  ProviderMeta,
  ProviderModelInfo,
  ProviderState,
  ValidateProviderOptions,
  ValidationStreamEvent,
} from './types';

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
        is_default?: boolean | number;
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

const BACKEND_BASE = process.env.ZENITH_BACKEND_URL || process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8765';
const rawTimeout = parseInt(process.env.VITE_BACKEND_FETCH_TIMEOUT ?? '10000', 10);
const BACKEND_FETCH_TIMEOUT = isNaN(rawTimeout) || rawTimeout <= 0 ? 10000 : rawTimeout;
const DEFAULT_MAX_TOKENS = parseInt(process.env.VITE_DEFAULT_MAX_TOKENS ?? '4096', 10);
const DEFAULT_TEMPERATURE = parseFloat(process.env.VITE_DEFAULT_TEMPERATURE ?? '0.7');
const FALLBACK_MAX_TOKENS = parseInt(process.env.VITE_FALLBACK_MAX_TOKENS ?? '4096', 10);

function backendUrl(path: string): string {
  return `${BACKEND_BASE.replace(/\/+$/, '')}${path}`;
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
        is_default: Boolean(m.is_default),
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

function modelFromInfo(info: ProviderModelInfo): ModelInfo {
  return {
    id: info.id,
    name: info.name,
    description: info.description || undefined,
    context_window: info.context_window,
    parameters: info.parameters as string | undefined,
    architecture: info.architecture as string | undefined,
    input_modalities: info.input_modalities as string[] | undefined,
    output_modalities: info.output_modalities as string[] | undefined,
    tags: info.tags,
    model_capabilities: info.model_capabilities as
      | {
          function_calling?: boolean;
          structured_output?: boolean;
          reasoning?: boolean;
          thinking?: boolean;
        }
      | undefined,
    speed_tier: (info.speed_tier as 'fast' | 'moderate' | 'slow') || undefined,
    best_for: info.best_for,
    is_default: info.is_default,
    pricing: info.pricing,
  };
}

export class ProviderRepository {
  private _listCache: ProviderListResponse | null = null;
  private _localActiveProviderId: ProviderId | null = null;
  private _localConfigOverrides: Partial<ProviderConfig> | null = null;

  /** GET /startup/providers — masked list payload (catalog + DB + session state). */
  public async fetchProviderList(): Promise<ProviderListResponse | null> {
    try {
      const res = await fetch(backendUrl('/startup/providers'), {
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(BACKEND_FETCH_TIMEOUT),
      });
      if (res.ok) {
        const data = (await res.json()) as ProviderListResponse;
        if (data && Array.isArray(data.all)) {
          this._listCache = data;
          return data;
        }
      }
    } catch {
      // Backend unreachable
    }
    return null;
  }

  public getProviderInfoList(): ProviderInfo[] {
    if (this._listCache?.all && this._listCache.all.length > 0) {
      return this._listCache.all;
    }
    return Object.values(DEFAULT_METAS).map((meta) => ({
      id: meta.id,
      name: meta.name,
      description: meta.description,
      adapter: meta.id,
      swatch: meta.swatch,
      capabilities: {},
      api_key_prefix: null,
      requires_api_key: true,
      model: meta.defaultModel,
      has_api_key: false,
      api_key_masked: '',
      validation_status: 'unconfigured',
      last_validation_error: '',
      is_active: false,
      models: Object.fromEntries(
        (meta.availableModels ?? []).map((m) => [
          m.id,
          {
            id: m.id,
            name: m.name,
            description: m.description || '',
            context_window: m.context_window || 128000,
            parameters: m.parameters || '',
            architecture: m.architecture || '',
            input_modalities: m.input_modalities || ['text'],
            output_modalities: m.output_modalities || ['text'],
            tags: m.tags || [],
            model_capabilities: m.model_capabilities || {},
            speed_tier: m.speed_tier || 'fast',
            best_for: m.best_for || [],
            is_default: Boolean(m.is_default),
          },
        ]),
      ),
      config_fields: meta.fields,
      options: {},
    }));
  }

  public getConnectedIds(): string[] {
    return this._listCache?.connected ?? [];
  }

  public getProviderInfo(id: ProviderId): ProviderInfo | undefined {
    return this.getProviderInfoList().find((item) => item.id === id);
  }

  public async refreshFromBackend(): Promise<ProviderListResponse | null> {
    return this.fetchProviderList();
  }

  public async setAuth(id: ProviderId, apiKey: string): Promise<ProviderInfo | null> {
    try {
      const res = await fetch(backendUrl(`/startup/providers/${encodeURIComponent(id)}/auth`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ api_key: apiKey }),
        signal: AbortSignal.timeout(BACKEND_FETCH_TIMEOUT),
      });
      if (res.ok) {
        const info = (await res.json()) as ProviderInfo;
        await this.mergeInfo(info);
        return info;
      }
    } catch {
      // Backend unreachable
    }
    return null;
  }

  public async setModel(id: ProviderId, model: string): Promise<ProviderInfo | null> {
    try {
      const res = await fetch(backendUrl(`/startup/providers/${encodeURIComponent(id)}/model`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ model }),
        signal: AbortSignal.timeout(BACKEND_FETCH_TIMEOUT),
      });
      if (res.ok) {
        const info = (await res.json()) as ProviderInfo;
        this._localActiveProviderId = id;
        await this.mergeInfo(info);
        return info;
      }
    } catch {
      // Backend unreachable
    }
    return null;
  }

  /**
   * POST /startup/providers/{id}/validate?stream=1 — consume the NDJSON pipeline
   * as an async iterator of events, ending with a `result` event.
   */
  public async *validateProviderStream(
    id: ProviderId,
    cfg: ValidateProviderOptions,
  ): AsyncGenerator<ValidationStreamEvent> {
    const res = await fetch(backendUrl(`/startup/providers/${encodeURIComponent(id)}/validate?stream=1`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' },
      body: JSON.stringify({
        api_key: cfg.apiKey ?? '',
        base_url: cfg.baseUrl ?? '',
        model: cfg.model ?? '',
      }),
    });
    if (!res.ok || !res.body) {
      throw new Error(`Validation request failed: HTTP ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx = buffer.indexOf('\n');
      while (idx >= 0) {
        const line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 1);
        if (line) {
          yield JSON.parse(line) as ValidationStreamEvent;
        }
        idx = buffer.indexOf('\n');
      }
    }
    if (buffer.trim()) {
      yield JSON.parse(buffer.trim()) as ValidationStreamEvent;
    }
  }

  private async mergeInfo(info: ProviderInfo): Promise<void> {
    if (!this._listCache) {
      this._listCache = { all: [], default: {}, connected: [] };
    }
    const existing = this._listCache.all;
    const idx = existing.findIndex((item) => item.id === info.id);
    if (idx >= 0) {
      this._listCache = {
        ...this._listCache,
        all: existing.map((item, i) => (i === idx ? info : item)),
        connected: info.has_api_key
          ? Array.from(new Set([...(this._listCache?.connected ?? []), info.id]))
          : (this._listCache?.connected ?? []).filter((c) => c !== info.id),
      };
    } else {
      this._listCache = {
        ...this._listCache,
        all: [...existing, info],
        connected: info.has_api_key
          ? Array.from(new Set([...(this._listCache?.connected ?? []), info.id]))
          : (this._listCache?.connected ?? []),
      };
    }
  }

  public getProviderMeta(id: ProviderId): ProviderMeta {
    const meta = DEFAULT_METAS[id];
    if (!meta) throw new Error(`Unknown provider: ${id}`);

    const info = this.getProviderInfo(id);
    if (info) {
      const infoModels = Object.values(info.models).map(modelFromInfo);
      return {
        ...meta,
        name: info.name || meta.name,
        description: info.description || meta.description,
        swatch: info.swatch?.length ? info.swatch : meta.swatch,
        defaultModel: info.model || meta.defaultModel,
        availableModels: infoModels.length ? infoModels : meta.availableModels,
        fields: info.config_fields?.length ? info.config_fields : meta.fields,
      };
    }
    return meta;
  }

  public getProviderStateDetails(
    id: ProviderId,
  ): Pick<ProviderState, 'hasApiKey' | 'apiKeyMasked' | 'validationStatus' | 'lastValidationError'> {
    const info = this.getProviderInfo(id);
    return {
      hasApiKey: info?.has_api_key ?? Boolean(this.getProviderConfig(id).apiKey),
      apiKeyMasked: info?.api_key_masked ?? '',
      validationStatus: info?.validation_status ?? 'unconfigured',
      lastValidationError: info?.last_validation_error ?? '',
    };
  }

  public getActiveProviderId(): ProviderId {
    if (this._localActiveProviderId && DEFAULT_METAS[this._localActiveProviderId]) {
      return this._localActiveProviderId;
    }
    if (this._listCache?.default?.active && DEFAULT_METAS[this._listCache.default.active]) {
      return this._listCache.default.active as ProviderId;
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
    const info = this.getProviderInfo(id);

    const base: ProviderConfig = info
      ? {
          model: info.model || meta.defaultModel,
          apiKey: info.has_api_key ? info.api_key_masked : '',
          baseUrl:
            (info.options?.base_url as string | undefined) ||
            (meta.fields?.find((f) => f.key === 'baseUrl')?.defaultValue as string) ||
            '',
          organizationId: '',
          timeout:
            (info.options?.max_tokens as number | undefined) ??
            (meta.fields?.find((f) => f.key === 'timeout')?.defaultValue as number) ??
            FALLBACK_MAX_TOKENS,
          temperature:
            (info.options?.temperature as number | undefined) ??
            (meta.fields?.find((f) => f.key === 'temperature')?.defaultValue as number) ??
            DEFAULT_TEMPERATURE,
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
