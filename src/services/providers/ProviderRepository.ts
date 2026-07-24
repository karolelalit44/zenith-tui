import { loadUserProfile, saveUserProfile } from '../data/userProfileService';
import type { ProviderConfig, ProviderId, ProviderMeta } from './types';

const BACKEND_BASE = process.env.VITE_BACKEND_URL || 'http://localhost:8765';

function backendUrl(path: string): string {
  return `${BACKEND_BASE.replace(/\/+$/, '')}${path}`;
}

export interface BackendProviderModel {
  id: string;
  name: string;
  context_window?: number;
  description?: string;
  is_default?: number;
}

export interface BackendProviderEntry {
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

export interface BackendProvidersResponse {
  active_provider: string;
  providers: Record<string, BackendProviderEntry>;
}

const DEFAULT_METAS: Record<ProviderId, ProviderMeta> = {
  openrouter: {
    id: 'openrouter',
    name: 'OpenRouter',
    description: 'Unified API gateway for 100+ LLMs',
    defaultModel: 'meta-llama/llama-3.3-70b-instruct',
    swatch: ['#7000FF', '#A033FF', '#6000DF'],
    availableModels: [
      { id: 'meta-llama/llama-3.3-70b-instruct', name: 'Meta Llama 3.3 70B' },
      { id: 'openai/gpt-4o', name: 'OpenAI GPT-4o' },
      { id: 'openai/gpt-4o-mini', name: 'OpenAI GPT-4o Mini' },
      { id: 'anthropic/claude-sonnet-4-20250514', name: 'Anthropic Claude Sonnet 4' },
      { id: 'google/gemini-2.0-flash-exp:free', name: 'Google Gemini 2.0 Flash (free)' },
    ],
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, placeholder: 'sk-or-v1-...' },
      { key: 'baseUrl', label: 'Base URL', type: 'text', defaultValue: 'https://openrouter.ai/api/v1' },
      { key: 'timeout', label: 'Timeout (ms)', type: 'number', defaultValue: 30000 },
    ],
  },
  openai: {
    id: 'openai',
    name: 'OpenAI',
    description: 'Official OpenAI GPT series models',
    defaultModel: 'gpt-4o-mini',
    swatch: ['#10A37F', '#1A7F64', '#0D8C6D'],
    availableModels: [
      { id: 'gpt-4o-mini', name: 'GPT-4o Mini' },
      { id: 'gpt-4o', name: 'GPT-4o' },
      { id: 'gpt-4-turbo', name: 'GPT-4 Turbo' },
    ],
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, placeholder: 'sk-...' },
      { key: 'baseUrl', label: 'Base URL', type: 'text', defaultValue: 'https://api.openai.com/v1' },
      { key: 'timeout', label: 'Timeout (ms)', type: 'number', defaultValue: 30000 },
    ],
  },
  nvidia: {
    id: 'nvidia',
    name: 'NVIDIA AI',
    description: 'NVIDIA NIM microservices & high-performance LLM catalog',
    defaultModel: 'deepseek-ai/deepseek-v4-pro',
    swatch: ['#76B900', '#5C9900', '#447700'],
    availableModels: [
      { id: 'deepseek-ai/deepseek-v4-pro', name: 'DeepSeek V4 Pro' },
      { id: 'minimaxai/minimax-m3', name: 'MiniMax M3' },
      { id: 'nvidia/nemotron-3-ultra-550b-a55b', name: 'NVIDIA Nemotron 3 Ultra' },
    ],
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, placeholder: 'nvapi-...' },
      { key: 'baseUrl', label: 'Base URL', type: 'text', defaultValue: 'https://integrate.api.nvidia.com/v1' },
      { key: 'timeout', label: 'Timeout (ms)', type: 'number', defaultValue: 30000 },
    ],
  },
  anthropic: {
    id: 'anthropic',
    name: 'Anthropic',
    description: 'Official Anthropic Claude family models',
    defaultModel: 'claude-sonnet-4-20250514',
    swatch: ['#D97706', '#B45309', '#92400E'],
    availableModels: [
      { id: 'claude-sonnet-4-20250514', name: 'Claude Sonnet 4' },
      { id: 'claude-3-5-haiku-20241022', name: 'Claude 3.5 Haiku' },
    ],
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, placeholder: 'sk-ant-...' },
      { key: 'baseUrl', label: 'Base URL', type: 'text', defaultValue: 'https://api.anthropic.com' },
      { key: 'timeout', label: 'Timeout (ms)', type: 'number', defaultValue: 30000 },
    ],
  },
  gemini: {
    id: 'gemini',
    name: 'Google Gemini',
    description: 'Google Gemini AI models',
    defaultModel: 'gemini-2.0-flash',
    swatch: ['#4285F4', '#34A853', '#FBBC05'],
    availableModels: [
      { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash' },
      { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro' },
    ],
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, placeholder: 'AIzaSy...' },
      { key: 'baseUrl', label: 'Base URL', type: 'text', defaultValue: 'https://generativelanguage.googleapis.com' },
      { key: 'timeout', label: 'Timeout (ms)', type: 'number', defaultValue: 30000 },
    ],
  },
  groq: {
    id: 'groq',
    name: 'Groq',
    description: 'Groq LPU ultra-fast inference API',
    defaultModel: 'llama-3.3-70b-versatile',
    swatch: ['#F55036', '#D43E26', '#B22F19'],
    availableModels: [
      { id: 'llama-3.3-70b-versatile', name: 'Llama 3.3 70B Versatile' },
      { id: 'mixtral-8x7b-32768', name: 'Mixtral 8x7B' },
    ],
    fields: [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true, placeholder: 'gsk_...' },
      { key: 'baseUrl', label: 'Base URL', type: 'text', defaultValue: 'https://api.groq.com/openai/v1' },
      { key: 'timeout', label: 'Timeout (ms)', type: 'number', defaultValue: 30000 },
    ],
  },
  custom: {
    id: 'custom',
    name: 'Custom OpenAI-Compatible',
    description: 'Self-hosted Ollama, vLLM, or custom server',
    defaultModel: 'llama3',
    swatch: ['#6B7280', '#4B5563', '#374151'],
    availableModels: [
      { id: 'llama3', name: 'Llama 3' },
      { id: 'codellama', name: 'CodeLlama' },
    ],
    fields: [
      { key: 'baseUrl', label: 'Base URL', type: 'text', required: true, placeholder: 'http://localhost:11434/v1' },
      { key: 'apiKey', label: 'API Key', type: 'password', placeholder: 'Optional' },
      { key: 'model', label: 'Model Name', type: 'text', required: true, placeholder: 'e.g. llama3' },
      { key: 'timeout', label: 'Timeout (ms)', type: 'number', defaultValue: 30000 },
    ],
  },
};

export class ProviderRepository {
  private _backendCache: BackendProvidersResponse | null = null;

  public getProviderMeta(id: ProviderId): ProviderMeta {
    const meta = DEFAULT_METAS[id] || DEFAULT_METAS.openai;
    if (this._backendCache?.providers?.[id]) {
      const backend = this._backendCache.providers[id];
      if (backend.models && backend.models.length > 0) {
        return {
          ...meta,
          availableModels: backend.models.map((m) => ({ id: m.id, name: m.name, description: m.description })),
        };
      }
    }
    return meta;
  }

  /** Fetch provider config from backend DB, caching it for the session. */
  public async refreshFromBackend(): Promise<BackendProvidersResponse | null> {
    try {
      const res = await fetch(backendUrl('/startup/provider-config'), {
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(5000),
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
    if (this._backendCache?.active_provider) {
      const id = this._backendCache.active_provider as ProviderId;
      if (DEFAULT_METAS[id]) return id;
    }
    const profile = loadUserProfile();
    const active = (profile.provider?.activeProvider || profile.activeProvider) as ProviderId;
    return active && DEFAULT_METAS[active] ? active : 'openrouter';
  }

  public setActiveProviderId(id: ProviderId): void {
    if (DEFAULT_METAS[id]) {
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
          max_tokens: currentConfig.timeout || 4096,
          temperature: currentConfig.temperature ?? 0.7,
        }),
        signal: AbortSignal.timeout(5000),
      })
        .then(() => this.refreshFromBackend())
        .catch(() => {});

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
    const meta = this.getProviderMeta(id);

    if (this._backendCache?.providers?.[id]) {
      const backend = this._backendCache.providers[id];
      return {
        model: backend.model || meta.defaultModel || '',
        apiKey: backend.api_key || '',
        baseUrl: backend.base_url || (meta.fields?.find((f) => f.key === 'baseUrl')?.defaultValue as string) || '',
        organizationId: '',
        timeout: backend.max_tokens ?? 30000,
        temperature: backend.temperature ?? 0.7,
      };
    }

    const profile = loadUserProfile();
    const settingsMap = (profile.providerSettings as Record<string, ProviderConfig>) || {};
    const stored = settingsMap[id] || {};

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
    const existing = this.getProviderConfig(id);
    const updatedConfig: ProviderConfig = { ...existing, ...updates };

    fetch(backendUrl('/startup/save-config'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        provider: id,
        api_key: updatedConfig.apiKey || existing.apiKey || '',
        model: updatedConfig.model || existing.model || '',
        base_url: updatedConfig.baseUrl || existing.baseUrl || '',
        max_tokens: updatedConfig.timeout || 30000,
        temperature: updatedConfig.temperature ?? 0.7,
      }),
      signal: AbortSignal.timeout(5000),
    })
      .then(() => this.refreshFromBackend())
      .catch(() => {});

    return updatedConfig;
  }
}

export const providerRepository = new ProviderRepository();
