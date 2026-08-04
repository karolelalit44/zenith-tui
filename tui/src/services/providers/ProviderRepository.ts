import { appConfig } from '../../config/appConfig';
import { BaseApiService } from '../api/BaseApiService';
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

function modelFromInfo(info: ProviderModelInfo): ModelInfo {
  return {
    id: info.id,
    name: info.name,
    description: info.description || undefined,
    context_window: info.context_window,
    is_default: info.is_default,
  };
}

export class ProviderRepository extends BaseApiService {
  private _listCache: ProviderListResponse | null = null;
  private _localActiveProviderId: ProviderId | null = null;

  public async fetchProviderList(): Promise<ProviderListResponse | null> {
    try {
      const data = await this.get<ProviderListResponse>('/startup/providers', {
        timeout: appConfig.timeout.fetchMs,
      });
      if (data && Array.isArray(data.all)) {
        this._listCache = data;
        return data;
      }
    } catch {}
    return null;
  }

  public getProviderInfoList(): ProviderInfo[] {
    return this._listCache?.all ?? [];
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

  public async setModel(id: ProviderId, model: string): Promise<ProviderInfo | null> {
    try {
      const info = await this.post<ProviderInfo>(
        `/startup/providers/${encodeURIComponent(id)}/model`,
        { model },
        { timeout: appConfig.timeout.fetchMs },
      );
      this._localActiveProviderId = id;
      await this.mergeInfo(info);
      return info;
    } catch {}
    return null;
  }

  public async *validateProviderStream(
    id: ProviderId,
    cfg: ValidateProviderOptions,
  ): AsyncGenerator<ValidationStreamEvent> {
    const res = await fetch(this.resolveUrl(`/startup/providers/${encodeURIComponent(id)}/validate?stream=1`), {
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
    const current: ProviderListResponse = this._listCache ?? {
      all: [],
      active: '',
      connected: [],
    };
    const existing = current.all;
    const idx = existing.findIndex((item) => item.id === info.id);
    const active = info.is_active ? info.id : current.active;
    const connected = info.has_api_key
      ? Array.from(new Set([...current.connected, info.id]))
      : current.connected.filter((c) => c !== info.id);
    const all = idx >= 0 ? existing.map((item, i) => (i === idx ? info : item)) : [...existing, info];
    this._listCache = { all, active, connected };
  }

  public getProviderMeta(id: ProviderId): ProviderMeta | undefined {
    const info = this.getProviderInfo(id);
    if (!info) return undefined;

    const models = Object.values(info.models ?? {}).map(modelFromInfo);
    const defaultModel = info.model || models.find((m) => m.is_default)?.id || models[0]?.id || '';

    return {
      id: info.id,
      name: info.name,
      description: info.description,
      defaultModel,
      availableModels: models,
      fields: info.config_fields ?? [],
    };
  }

  public getProviderStateDetails(
    id: ProviderId,
  ): Pick<
    ProviderState,
    | 'hasApiKey'
    | 'apiKeyMasked'
    | 'validationStatus'
    | 'lastValidationError'
    | 'isPopular'
    | 'isCustomFlow'
    | 'baseUrlStyle'
    | 'supportsPromptCaching'
    | 'supportsThinkingHeaders'
  > {
    const info = this.getProviderInfo(id);
    return {
      hasApiKey: info?.has_api_key ?? Boolean(this.getProviderConfig(id).apiKey),
      apiKeyMasked: info?.api_key_masked ?? '',
      validationStatus: info?.validation_status ?? 'unconfigured',
      lastValidationError: info?.last_validation_error ?? '',
      isPopular: info?.is_popular ?? false,
      isCustomFlow: info?.custom_flow ?? false,
      baseUrlStyle: info?.base_url_style ?? '',
      supportsPromptCaching: info?.supports_prompt_caching ?? false,
      supportsThinkingHeaders: info?.supports_thinking_headers ?? false,
    };
  }

  public getActiveProviderId(): ProviderId {
    const known = new Set(this.getProviderInfoList().map((item) => item.id));
    if (this._localActiveProviderId && known.has(this._localActiveProviderId)) {
      return this._localActiveProviderId;
    }
    const backendActive = this._listCache?.active;
    if (backendActive && known.has(backendActive)) {
      return backendActive as ProviderId;
    }
    return '';
  }

  public getProviderConfig(id: ProviderId): ProviderConfig {
    const meta = this.getProviderMeta(id);
    const info = this.getProviderInfo(id);
    const fields = meta?.fields ?? [];
    const defaultModel = meta?.defaultModel ?? '';

    const base: ProviderConfig = info
      ? {
          model: info.model || defaultModel,
          apiKey: info.has_api_key ? info.api_key_masked : '',
          baseUrl:
            (info.options?.base_url as string | undefined) ||
            (fields.find((f) => f.key === 'baseUrl')?.defaultValue as string) ||
            '',
          organizationId: '',
          timeout:
            (info.options?.max_tokens as number | undefined) ??
            (fields.find((f) => f.key === 'timeout')?.defaultValue as number) ??
            appConfig.defaults.fallbackMaxTokens,
          temperature:
            (info.options?.temperature as number | undefined) ??
            (fields.find((f) => f.key === 'temperature')?.defaultValue as number) ??
            appConfig.defaults.temperature,
        }
      : {
          model: defaultModel,
          apiKey: '',
          baseUrl: (fields.find((f) => f.key === 'baseUrl')?.defaultValue as string) || '',
          organizationId: '',
          timeout: appConfig.defaults.fallbackMaxTokens,
          temperature: appConfig.defaults.temperature,
        };

    return base;
  }
}

export const providerRepository = new ProviderRepository();
