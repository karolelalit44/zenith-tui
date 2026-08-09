export type ProviderId = string;

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
  is_default?: boolean;
}

export interface ProviderMeta {
  id: ProviderId;
  name: string;
  description: string;
  defaultModel: string;
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
  isPopular: boolean;
  isCustomFlow: boolean;
  baseUrlStyle: string;
  supportsPromptCaching: boolean;
  supportsThinkingHeaders: boolean;
}

export interface ProviderModelInfo {
  id: string;
  name: string;
  context_window: number;
  description: string;
  is_default: boolean;
  status?: string;
}

export interface ProviderInfo {
  id: string;
  name: string;
  description: string;
  config_fields: ProviderConfigField[];
  options: Record<string, unknown>;
  has_api_key: boolean;
  api_key_masked: string;
  validation_status: ProviderStatus;
  last_validation_error: string;
  is_active: boolean;
  model: string;
  models: Record<string, ProviderModelInfo>;
  is_popular: boolean;
  base_url_style: string;
  supports_prompt_caching: boolean;
  supports_thinking_headers: boolean;
  custom_flow: boolean;
  env_keys: string[];
  max_context_tokens?: number;
}

export interface ProviderListResponse {
  all: ProviderInfo[];
  active: string;
  connected: string[];
  max_context_tokens?: number;
}

/** Lightweight provider catalog item — the `/providers` list carries no models. */
export interface ProviderCatalogItem {
  id: string;
  name: string;
  type: 'default' | 'custom';
}

/** Paginated models returned by `GET /providers/{id}/models`. */
export interface ProviderModelListResponse {
  models: ProviderModelInfo[];
  total: number;
  offset: number;
  limit: number;
}

/** Number of models rendered per page in the shared model selector. */
export const MODELS_PER_PAGE = 5;

export interface ValidationStep {
  key: string;
  label: string;
  status: ValidationStepStatus;
  message: string;
}

export interface ValidationError {
  code: string;
  message: string;
}

export interface ValidationResult {
  valid: boolean;
  provider: string;
  steps: ValidationStep[];
  models: ProviderModelInfo[];
  error: ValidationError | null;
}

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
  name?: string;
  apiKey?: string;
  baseUrl?: string;
  model?: string;
}

export interface ModelSelection {
  providerID: string;
  modelID: string;
}
