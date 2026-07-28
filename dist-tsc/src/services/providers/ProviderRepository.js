import catalogData from '../../../config/provider_catalog.json';
import { requireEnv, requireFloat, requireInt } from '../../config/env';
const catalog = catalogData;
const BACKEND_BASE = requireEnv('VITE_BACKEND_URL');
const BACKEND_FETCH_TIMEOUT = requireInt('VITE_BACKEND_FETCH_TIMEOUT');
const DEFAULT_MAX_TOKENS = requireInt('VITE_DEFAULT_MAX_TOKENS');
const DEFAULT_TEMPERATURE = requireFloat('VITE_DEFAULT_TEMPERATURE');
const FALLBACK_MAX_TOKENS = requireInt('VITE_FALLBACK_MAX_TOKENS');
function backendUrl(path) {
    return `${BACKEND_BASE.replace(/\/+$/, '')}${path}`;
}
const DEFAULT_METAS = Object.fromEntries(Object.entries(catalog.providers).map(([pid, p]) => [
    pid,
    {
        id: pid,
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
            speed_tier: m.speed_tier,
            best_for: m.best_for,
        })),
        fields: (p.config_fields || []).map((f) => ({
            key: f.key,
            label: f.label,
            type: f.type,
            required: f.required,
            placeholder: f.placeholder,
            defaultValue: f.defaultValue,
        })),
    },
]));
export class ProviderRepository {
    _backendCache = null;
    _localActiveProviderId = null;
    _localConfigOverrides = null;
    getProviderMeta(id) {
        const meta = DEFAULT_METAS[id];
        if (!meta)
            throw new Error(`Unknown provider: ${id}`);
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
                        speed_tier: m.speed_tier,
                        best_for: m.best_for,
                    })),
                };
            }
        }
        return meta;
    }
    async refreshFromBackend() {
        try {
            const res = await fetch(backendUrl('/startup/provider-config'), {
                headers: { Accept: 'application/json' },
                signal: AbortSignal.timeout(BACKEND_FETCH_TIMEOUT),
            });
            if (res.ok) {
                const data = (await res.json());
                this._backendCache = data;
                return data;
            }
        }
        catch {
            // Backend unreachable
        }
        return null;
    }
    getActiveProviderId() {
        if (this._localActiveProviderId && DEFAULT_METAS[this._localActiveProviderId]) {
            return this._localActiveProviderId;
        }
        if (this._backendCache?.active_provider) {
            const id = this._backendCache.active_provider;
            if (DEFAULT_METAS[id])
                return id;
        }
        return catalog.default_active_provider;
    }
    setActiveProviderId(id) {
        if (!DEFAULT_METAS[id])
            throw new Error(`Unknown provider: ${id}`);
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
            .catch(() => { });
    }
    getProviderConfig(id) {
        const meta = this.getProviderMeta(id);
        const base = this._backendCache?.providers?.[id]
            ? {
                model: this._backendCache.providers[id].model || meta.defaultModel,
                apiKey: this._backendCache.providers[id].api_key || '',
                baseUrl: this._backendCache.providers[id].base_url ||
                    meta.fields?.find((f) => f.key === 'baseUrl')?.defaultValue ||
                    '',
                organizationId: '',
                timeout: this._backendCache.providers[id].max_tokens ?? FALLBACK_MAX_TOKENS,
                temperature: this._backendCache.providers[id].temperature ?? DEFAULT_TEMPERATURE,
            }
            : {
                model: meta.defaultModel,
                apiKey: '',
                baseUrl: meta.fields?.find((f) => f.key === 'baseUrl')?.defaultValue || '',
                organizationId: '',
                timeout: FALLBACK_MAX_TOKENS,
                temperature: DEFAULT_TEMPERATURE,
            };
        return this._localConfigOverrides ? { ...base, ...this._localConfigOverrides } : base;
    }
    updateProviderConfig(id, updates) {
        const existing = this.getProviderConfig(id);
        const updatedConfig = { ...existing, ...updates };
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
            .catch(() => { });
        return updatedConfig;
    }
}
export const providerRepository = new ProviderRepository();
