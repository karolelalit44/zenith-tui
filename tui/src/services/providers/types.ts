/** Backend-aligned provider types for the Provider Configuration flow. */

export type ProviderId = string;

/** Catalog `adapter` values (aligned to `provider_catalog.json`). */
export type ProviderAdapter = 'openrouter' | 'openai_compatible' | 'openai_compat' | 'nvidia' | 'groq' | 'gemini';

export type ProviderStatus = 'unconfigured' | 'configured' | 'validated' | 'failed';

export type ValidationStepStatus = 'pending' | 'running' | 'success' | 'failed';

export interface ProviderConfigField {
  key: string;
  label: string;
  type: 'text' | 'password' | 'select' | 'number';
  placeholder?: string;
  options?: { label: string; value: string }[];
  required?: boolean;
  defaultValue?: string | number;
  description?: string;
}

export interface ProviderConfig {
  apiKey?: string;
  model?: string;
  baseUrl?: string;
  organizationId?: string;
  timeout?: number;
  temperature?: number;
  [key: string]: unknown;
}

export interface ModelInfo {
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
  speed_tier?: 'fast' | 'moderate' | 'slow';
  best_for?: string[];
  is_default?: boolean;
  pricing?: Record<string, unknown>;
}

export interface ProviderMeta {
  id: ProviderId;
  name: string;
  description: string;
  defaultModel: string;
  swatch: string[];
  fields: ProviderConfigField[];
  availableModels?: ModelInfo[];
}

export interface ProviderState {
  id: ProviderId;
  meta: ProviderMeta;
  config: ProviderConfig;
  isActive: boolean;
  isConfigured: boolean;
  hasApiKey?: boolean;
  apiKeyMasked?: string;
  validationStatus?: ProviderStatus;
  lastValidationError?: string;
}

/** Mirrors `server/api/schemas.py: ProviderModelInfo`. */
export interface ProviderModelInfo {
  id: string;
  name: string;
  context_window: number;
  description: string;
  is_default: boolean;
  status?: string;
  parameters?: unknown;
  architecture?: unknown;
  input_modalities?: unknown;
  output_modalities?: unknown;
  tags?: string[];
  model_capabilities?: Record<string, unknown>;
  speed_tier?: string | null;
  best_for?: string[];
  pricing?: Record<string, unknown>;
}

/** Mirrors `server/api/schemas.py: ProviderInfo`. */
export interface ProviderInfo {
  id: string;
  name: string;
  description: string;
  adapter: ProviderAdapter | string;
  swatch: string[];
  capabilities: Record<string, unknown>;
  api_key_prefix: string | null;
  requires_api_key: boolean;
  config_fields: ProviderConfigField[];
  options: Record<string, unknown>;
  has_api_key: boolean;
  api_key_masked: string;
  validation_status: ProviderStatus;
  last_validation_error: string;
  is_active: boolean;
  model: string;
  models: Record<string, ProviderModelInfo>;
}

/** Mirrors `server/api/schemas.py: ProviderListResponse`. */
export interface ProviderListResponse {
  all: ProviderInfo[];
  default: Record<string, string>;
  connected: string[];
}

/** Mirrors `server/api/schemas.py: ValidationStep`. */
export interface ValidationStep {
  key: string;
  label: string;
  status: ValidationStepStatus;
  message: string;
}

/** Mirrors `server/api/schemas.py: ValidationError`. */
export interface ValidationError {
  code: string;
  message: string;
}

/** Mirrors `server/api/schemas.py: ValidationResult`. */
export interface ValidationResult {
  valid: boolean;
  provider: string;
  steps: ValidationStep[];
  models: ProviderModelInfo[];
  error: ValidationError | null;
}

/** NDJSON events emitted by `POST /startup/providers/{id}/validate?stream=1`. */
export interface ValidationStreamEvent {
  type: 'step' | 'model' | 'result';
  key?: string;
  label?: string;
  status?: ValidationStepStatus;
  message?: string;
  model?: ProviderModelInfo;
  valid?: boolean;
  provider?: string;
  steps?: ValidationStep[];
  models?: ProviderModelInfo[];
  error?: ValidationError | null;
}

export interface ValidateProviderOptions {
  apiKey?: string;
  baseUrl?: string;
  model?: string;
}

export interface ModelSelection {
  providerID: string;
  modelID: string;
}
